"""Supervised host for entry-point discovered Python platform adapters."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Mapping, Sequence
from importlib import metadata
from pathlib import Path
from typing import Any

from liteyukibot.events import ActionEnvelope, EventEnvelope
from liteyukibot.logging import configure_runtime_child_logging, get_logger
from liteyukibot.runtime import RuntimeClient
from liteyukibot.runtime.protocol import ActionRequest, ActionResponse, EventIngress, Shutdown, json_value

from .contracts import AdapterConnection, AdapterContext, AdapterPlugin

logger = get_logger(component="adapter", runtime=os.environ.get("LITEYUKI_RUNTIME_ID"))


class AdapterHost:
    """Load configured adapter instances and mediate their IPC-only kernel access."""

    def __init__(self, client: RuntimeClient, plugins: Mapping[str, AdapterPlugin]) -> None:
        self.client = client
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
                runtime_id=self.client.runtime_id,
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
        """Forward only events whose identity is owned by the emitting connection."""

        if event.runtime_id != self.client.runtime_id:
            raise ValueError("adapter event runtime_id does not match this runtime")
        if event.bot_id != bot_id:
            raise ValueError("adapter event bot_id does not match its connection")
        async with self._emit_lock:
            await self.client.send(EventIngress(source_event_id=event.id, payload=event.model_dump(mode="json")))

    async def execute(self, request: ActionRequest) -> ActionResponse:
        try:
            envelope = ActionEnvelope.model_validate(request.payload)
            if envelope.runtime_id != self.client.runtime_id:
                raise ValueError("action runtime_id does not match this runtime")
            connection = self.connections[envelope.bot_id]
            return ActionResponse(
                correlation_id=request.correlation_id,
                ok=True,
                data=json_value(await connection.execute(envelope)),
            )
        except Exception as error:
            return ActionResponse(
                correlation_id=request.correlation_id,
                ok=False,
                error=f"{type(error).__name__}: {error}",
            )

    async def close(self) -> None:
        connections, self.connections = tuple(self.connections.values()), {}
        results = await asyncio.gather(*(connection.close() for connection in connections), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                logger.error("adapter connection cleanup failed: {}", result)

    async def run(self, options: Mapping[str, Any]) -> None:
        await self.start(options)
        await self.client.ready(("adapter.events", "adapter.actions"))
        while True:
            message = await self.client.receive()
            if isinstance(message, Shutdown):
                return
            if isinstance(message, ActionRequest):
                await self.client.send(await self.execute(message))


def discover_adapter_plugins(allowed: Sequence[str] | None = None) -> dict[str, AdapterPlugin]:
    """Discover adapter packages without importing unselected managed-generation code."""

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


def managed_adapter_names() -> tuple[str, ...] | None:
    raw_generation = os.environ.get("LITEYUKI_RUNTIME_GENERATION_DIR")
    if raw_generation is None:
        return None
    generation = Path(raw_generation).resolve(strict=True)
    plan_path = generation / "load-plan.json"
    try:
        document = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError("managed adapter generation has an invalid load plan") from error
    if not isinstance(document, Mapping):
        raise RuntimeError("managed adapter generation load plan must be an object")
    value = document.get("adapters", [])
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise RuntimeError("managed adapter generation load plan adapters must be an array")
    adapters = tuple(value)
    if any(not isinstance(item, str) or not item or item != item.strip() for item in adapters):
        raise RuntimeError("managed adapter generation load plan contains an invalid adapter name")
    if len(set(adapters)) != len(adapters):
        raise RuntimeError("managed adapter generation load plan repeats adapter names")
    return adapters


def _adapter_instances(options: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    value = options.get("adapters", {})
    if not isinstance(value, Mapping):
        raise ValueError("adapter runtime option 'adapters' must be an object")
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


async def _run() -> None:
    configure_runtime_child_logging()
    client = RuntimeClient.from_environment("adapter")
    options = await client.connect()
    host = AdapterHost(client, discover_adapter_plugins(managed_adapter_names()))
    try:
        await host.run(options)
    finally:
        await host.close()
        await client.close()


def run() -> None:
    asyncio.run(_run())


__all__ = ["AdapterHost", "discover_adapter_plugins", "managed_adapter_names", "run"]
