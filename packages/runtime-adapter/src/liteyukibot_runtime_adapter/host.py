"""Configuration-authoritative Broker bridge for Python platform adapters."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping, Sequence
from importlib import metadata
from typing import Any, cast
from urllib.parse import urlparse
from uuid import uuid4

import zmq.asyncio

from liteyukibot.broker import (
    MESSAGE_SEND_KIND,
    ActionOutcome,
    ActionRequest,
    ActionResourceDeclaration,
    BridgeAccess,
    BridgeClient,
    BridgeManifest,
    BrokerBridgeRunner,
    EventIngress,
    parse_message_send_request,
)
from liteyukibot.config import AppSettings
from liteyukibot.events import EventEnvelope
from liteyukibot.events import JsonValue as EventJsonValue
from liteyukibot.lyip import LyipLane
from liteyukibot.runtime.protocol import json_value

from .contracts import AdapterConnection, AdapterContext, AdapterPlugin

_TOPICS = {
    ("onebot-v11", "private"): "onebot.v11.message.private",
    ("onebot-v11", "group"): "onebot.v11.message.group",
    ("onebot-v12", "private"): "onebot.v12.message.private",
    ("onebot-v12", "group"): "onebot.v12.message.group",
    ("onebot-v12", "channel"): "onebot.v12.message.channel",
    ("satori", "private"): "satori.message.private",
    ("satori", "channel"): "satori.message.channel",
}


class AdapterHost:
    """Load configured adapter instances and expose only Broker-safe traffic."""

    def __init__(self, runner: BrokerBridgeRunner, bridge_id: str, plugins: Mapping[str, AdapterPlugin]) -> None:
        self.runner = runner
        self.bridge_id = bridge_id
        self.plugins = dict(plugins)
        self.connections: dict[str, AdapterConnection] = {}
        self._emit_lock = asyncio.Lock()

    async def start(self, options: Mapping[str, Any]) -> None:
        adapters = _adapter_instances(options)
        for instance_id, instance in adapters.items():
            kind = _required_string(instance, "kind")
            bot_id = _required_string(instance, "bot_id")
            config = _json_object(instance.get("config", {}), "adapter config")
            try:
                plugin = self.plugins[kind]
            except KeyError as error:
                raise RuntimeError(f"adapter kind {kind!r} is not installed") from error
            context = AdapterContext(
                bridge_id=self.bridge_id,
                instance_id=instance_id,
                kind=kind,
                bot_id=bot_id,
                config=config,
            )
            connection = await plugin.create(context)
            if bot_id in self.connections:
                await connection.close()
                raise RuntimeError(f"adapter bot ID {bot_id!r} is configured more than once")
            self.connections[bot_id] = connection

            async def emit(event: EventEnvelope, *, owned_bot_id: str = bot_id) -> None:
                await self.emit(owned_bot_id, event)

            try:
                await connection.start(emit)
            except BaseException:
                self.connections.pop(bot_id, None)
                await connection.close()
                raise

    async def emit(self, bot_id: str, event: EventEnvelope) -> None:
        """Convert one driver event into the fixed Alpha 4 ingress contract."""

        if event.runtime_id != self.bridge_id:
            raise ValueError("adapter event bridge_id does not match this bridge")
        if event.bot_id != bot_id:
            raise ValueError("adapter event bot_id does not match its connection")
        try:
            topic = _TOPICS[(event.adapter, event.conversation.type)]
        except KeyError as error:
            raise ValueError("adapter event uses an unsupported platform topic") from error
        async with self._emit_lock:
            await self.runner.client.send_event_ingress(
                EventIngress(
                    source_event_id=event.id,
                    topic=topic,
                    ordering_key=f"{event.bot_id}:{event.conversation.ordering_key}",
                    payload=event.model_dump(mode="json"),
                )
            )

    async def execute(self, request: ActionRequest) -> ActionOutcome:
        """Handle the only action accepted by an Alpha 4 adapter bridge."""

        try:
            payload = parse_message_send_request(request, owner_bridge_id=self.bridge_id)
            connection = self.connections[payload.bot_id]
            result = await connection.send_message(payload)
        except KeyError:
            return ActionOutcome(success=False, payload={"error": "unknown_bot"})
        except ValueError:
            return ActionOutcome(success=False, payload={"error": "invalid_message_send"})
        except Exception:
            return ActionOutcome(success=False, payload={"error": "adapter_action_failed"})
        return ActionOutcome(success=True, payload=cast(EventJsonValue, result))

    async def close(self) -> None:
        connections, self.connections = tuple(self.connections.values()), {}
        await asyncio.gather(*(connection.close() for connection in connections), return_exceptions=True)

    async def run(self, options: Mapping[str, Any]) -> None:
        await self.start(options)
        serving = asyncio.create_task(self.runner.serve_forever(), name=f"adapter-bridge:{self.bridge_id}")
        failures = tuple(
            asyncio.create_task(connection.wait_failure(), name=f"adapter-failure:{bot_id}")
            for bot_id, connection in self.connections.items()
        )
        try:
            done, _pending = await asyncio.wait(
                {serving, *failures}, return_when=asyncio.FIRST_COMPLETED
            )
            if serving in done:
                serving.result()
                return
            for failure in failures:
                if failure in done:
                    failure.result()
            raise RuntimeError("adapter bridge stopped after an unknown connection failure")
        finally:
            if not serving.done():
                serving.cancel()
            await asyncio.gather(serving, *failures, return_exceptions=True)


def discover_adapter_plugins(allowed: Sequence[str] | None = None) -> dict[str, AdapterPlugin]:
    """Discover and validate selected driver entry points."""

    permitted = None if allowed is None else frozenset(allowed)
    plugins: dict[str, AdapterPlugin] = {}
    diagnostics: list[str] = []
    for entry in metadata.entry_points(group="liteyukibot.adapters"):
        if permitted is not None and entry.name not in permitted:
            continue
        try:
            loaded = entry.load()
            if not callable(loaded):
                raise TypeError("entry point is not callable")
            plugin = loaded()
            if not isinstance(plugin, AdapterPlugin):
                raise TypeError("entry point did not return AdapterPlugin")
            if plugin.kind != entry.name:
                raise ValueError(f"returned mismatched kind {plugin.kind!r}")
            installed_distribution = _entry_distribution_name(entry)
            distributions_match = (
                installed_distribution is None
                or _canonical_distribution_name(plugin.distribution)
                == _canonical_distribution_name(installed_distribution)
            )
            if not distributions_match:
                raise ValueError(
                    f"declared distribution {plugin.distribution!r} does not match installed distribution"
                )
            if plugin.kind in plugins:
                raise ValueError("duplicates an installed adapter kind")
            plugins[plugin.kind] = plugin
        except Exception as error:
            diagnostics.append(f"adapter {entry.name!r} is unavailable: {type(error).__name__}: {error}")
    if permitted is not None:
        missing = permitted - plugins.keys()
        diagnostics.extend(f"adapter {name!r} is not installed" for name in sorted(missing))
    if diagnostics:
        raise RuntimeError("; ".join(diagnostics))
    return plugins


async def launch(settings: AppSettings, bridge_id: str, token: str) -> None:
    """Launch one configured adapter bridge through the standalone Broker."""

    bridge = settings.broker.bridges.get(bridge_id)
    if bridge is None:
        raise RuntimeError(f"broker bridge {bridge_id!r} is not configured")
    if bridge.kind != "adapter":
        raise RuntimeError(f"broker bridge {bridge_id!r} is not an adapter bridge")
    adapters = _adapter_instances(bridge.options)
    kinds = tuple(dict.fromkeys(_required_string(instance, "kind") for instance in adapters.values()))
    plugins = discover_adapter_plugins(kinds)
    manifest = _adapter_manifest(
        bridge_id,
        bridge.access,
        bridge.subscriptions,
        bridge.action_resources,
        adapters,
    )
    client = BridgeClient(
        context=zmq.asyncio.Context.instance(),
        endpoints=_broker_endpoints(settings.broker.endpoint),
        generation=settings.broker.generation,
        identity=f"adapter:{bridge_id}:{uuid4()}".encode("ascii"),
        manifest=manifest,
        instance_token=token,
    )
    host: AdapterHost | None = None

    async def execute_action(request: ActionRequest) -> ActionOutcome:
        if host is None:
            return ActionOutcome(success=False, payload={"error": "adapter_not_ready"})
        return await host.execute(request)

    runner = BrokerBridgeRunner(client, action_handlers={MESSAGE_SEND_KIND: execute_action})
    host = AdapterHost(runner, bridge_id, plugins)
    try:
        await runner.start()
        await host.run(bridge.options)
    finally:
        await host.close()
        try:
            await runner.stop()
        finally:
            runner.close()


def _adapter_manifest(
    bridge_id: str,
    access: str,
    subscriptions: Sequence[str],
    configured_resources: Sequence[Any],
    adapters: Mapping[str, Mapping[str, Any]],
) -> BridgeManifest:
    if access != BridgeAccess.LIMITED.value:
        raise RuntimeError("adapter bridge must use limited access")
    if subscriptions:
        raise RuntimeError("adapter bridge must not subscribe to broker events")
    bot_ids = tuple(_required_string(instance, "bot_id") for instance in adapters.values())
    if len(set(bot_ids)) != len(bot_ids):
        raise RuntimeError("adapter bot IDs must be unique")
    expected = tuple(
        ActionResourceDeclaration(
            kind=MESSAGE_SEND_KIND,
            resource=f"bot:{bridge_id}:{bot_id}",
        )
        for bot_id in bot_ids
    )
    actual = tuple(
        ActionResourceDeclaration(
            kind=item.kind,
            resource=item.resource,
            resource_prefix=item.resource_prefix,
        )
        for item in configured_resources
    )
    if set(actual) != set(expected) or any(item.resource_prefix is not None for item in actual):
        raise RuntimeError("adapter bridge action resources must exactly match configured bot IDs")
    return BridgeManifest(
        bridge_id=bridge_id,
        access=BridgeAccess.LIMITED,
        action_resources=expected,
    )


def _broker_endpoints(endpoint: str) -> dict[LyipLane, str]:
    parsed = urlparse(endpoint)
    if parsed.scheme != "tcp" or parsed.hostname is None or parsed.port is None:
        raise ValueError("broker endpoint must be a valid tcp URL")
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    return {
        LyipLane.CONTROL: f"tcp://{host}:{parsed.port}",
        LyipLane.BUSINESS: f"tcp://{host}:{parsed.port + 1}",
    }


def _adapter_instances(options: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    value = options.get("adapters", {})
    if not isinstance(value, Mapping):
        raise ValueError("adapter bridge option 'adapters' must be an object")
    result: dict[str, Mapping[str, Any]] = {}
    for instance_id, raw in value.items():
        if not isinstance(instance_id, str) or not instance_id or instance_id != instance_id.strip():
            raise ValueError("adapter instance IDs must be non-empty trimmed strings")
        if not isinstance(raw, Mapping):
            raise ValueError(f"adapter instance {instance_id!r} must be an object")
        result[instance_id] = raw
    return result


def _required_string(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item or item != item.strip():
        raise ValueError(f"adapter instance {key!r} must be a non-empty trimmed string")
    return item


def _json_object(value: object, subject: str) -> dict[str, Any]:
    try:
        normalized = json_value(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{subject} must be JSON-safe") from error
    if not isinstance(normalized, dict):
        raise ValueError(f"{subject} must be an object")
    return normalized


def _entry_distribution_name(entry: metadata.EntryPoint) -> str | None:
    distribution = getattr(entry, "dist", None)
    if distribution is None:
        return None
    name = distribution.metadata.get("Name")
    return name if isinstance(name, str) and name else None


def _canonical_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


__all__ = ["AdapterHost", "discover_adapter_plugins", "launch"]
