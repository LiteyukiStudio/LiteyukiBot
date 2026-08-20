"""Broker bridge host for the retained LiteyukiBot v6 compatibility surface."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping, Sequence
from importlib import metadata
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import zmq.asyncio
from liteyuki.bot import _emit_lifecycle, _install_runtime, _reset_runtime
from liteyuki.session.on import _dispatch_matchers

from liteyukibot.broker import (
    MESSAGE_SEND_KIND,
    BridgeAccess,
    BridgeClient,
    BridgeManifest,
    BrokerBridgeRunner,
    BrokerDelivery,
    MessageSendPayload,
    message_send_resource_key,
)
from liteyukibot.config import AppSettings
from liteyukibot.events import EventEnvelope
from liteyukibot.logging import get_logger
from liteyukibot.lyip import LyipLane

from .events import reply_to_message, to_legacy_message_event

V6_PLUGIN_ENTRY_POINT_GROUP = "liteyukibot.v6_plugins"
_LEGACY_OPTION_KEYS = frozenset({"plugins", "plugin_dirs", "config", "action_timeout_seconds"})
_ALLOWED_BRIDGE_OPTION_KEYS = frozenset({"v6_plugins", "max_concurrent_events"})


class _V6BridgeHost:
    def __init__(
        self,
        runner: BrokerBridgeRunner,
        bridge_id: str,
        logger: Any,
        *,
        max_concurrent_events: int,
        restart_requested: asyncio.Event,
    ) -> None:
        self.runner = runner
        self.bridge_id = bridge_id
        self.logger = logger
        self._capacity = asyncio.Semaphore(max_concurrent_events)
        self._restart_requested = restart_requested

    async def serve(self) -> str:
        serving = asyncio.create_task(self.runner.serve_forever(), name=f"v6-bridge:{self.bridge_id}")
        restart = asyncio.create_task(self._restart_requested.wait(), name=f"v6-restart:{self.bridge_id}")
        done, pending = await asyncio.wait((serving, restart), return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        if restart in done and restart.result():
            return "restart"
        serving.result()
        return "shutdown"

    async def handle_delivery(self, delivery: BrokerDelivery) -> None:
        async with self._capacity:
            broker_event = delivery.message.event
            event = EventEnvelope.model_validate(broker_event.payload)
            if event.runtime_id != broker_event.source_bridge_id:
                raise ValueError("v6 event runtime_id does not match its broker source bridge")
            legacy_event = to_legacy_message_event(event)
            if legacy_event is None:
                return
            try:
                result = await _dispatch_matchers(legacy_event)
                if result.failures:
                    self.logger.warning(
                        "v6 event {} completed with {} matcher failure(s)",
                        event.id,
                        len(result.failures),
                    )
            except Exception as error:
                self.logger.exception("v6 matcher dispatch failed for {}: {}", event.id, error)

            for index, reply in enumerate(legacy_event._drain_replies()):
                try:
                    message = reply_to_message(reply)
                    payload = MessageSendPayload(
                        bot_id=event.bot_id,
                        message=message,
                        conversation=event.conversation,
                        reply_token=event.reply_token,
                    )
                    action = await delivery.request_action(
                        correlation_id=f"v6:{event.id}:{index}:{uuid4()}",
                        kind=MESSAGE_SEND_KIND,
                        resource_key=message_send_resource_key(event.runtime_id, event.bot_id),
                        payload=payload.model_dump(mode="json", exclude_none=True),
                    )
                    if not action.success:
                        self.logger.warning(
                            "v6 reply action failed for event {}: {}",
                            event.id,
                            action.payload,
                        )
                except Exception as error:
                    self.logger.exception("v6 reply failed for event {}: {}", event.id, error)


def load_configured_v6_plugins(names: Sequence[str]) -> tuple[str, ...]:
    """Import only the selected v6 plugin entry points."""

    configured = _normalized_plugin_names(names)
    entries: dict[str, Any] = {}
    for entry in metadata.entry_points(group=V6_PLUGIN_ENTRY_POINT_GROUP):
        if entry.name not in configured:
            continue
        if entry.name in entries:
            raise RuntimeError(f"v6 plugin entry point {entry.name!r} is duplicated")
        entries[entry.name] = entry
    missing = tuple(name for name in configured if name not in entries)
    if missing:
        raise RuntimeError("configured v6 plugin entry point(s) are not installed: " + ", ".join(missing))
    for name in configured:
        try:
            entries[name].load()
        except Exception as error:
            raise RuntimeError(f"failed to load v6 plugin entry point {name!r}") from error
    return configured


async def launch(settings: AppSettings, bridge_id: str, token: str) -> None:
    """Launch one limited v6 bridge through the standalone Broker."""

    bridge = settings.broker.bridges.get(bridge_id)
    if bridge is None:
        raise RuntimeError(f"broker bridge {bridge_id!r} is not configured")
    if bridge.kind != "v6":
        raise RuntimeError(f"broker bridge {bridge_id!r} is not a v6 bridge")
    _validate_bridge_settings(bridge.access, bridge.subscriptions, bridge.action_resources, bridge.options)
    _load_configured_plugins(bridge.options)

    manifest = BridgeManifest(
        bridge_id=bridge_id,
        access=BridgeAccess.LIMITED,
        subscriptions=bridge.subscriptions,
    )
    client = BridgeClient(
        context=zmq.asyncio.Context.instance(),
        endpoints=_broker_endpoints(settings.broker.endpoint),
        generation=settings.broker.generation,
        identity=f"v6:{bridge_id}:{uuid4()}".encode("ascii"),
        manifest=manifest,
        instance_token=token,
    )
    restart_requested = asyncio.Event()
    loop = asyncio.get_running_loop()

    def request_restart(_name: str | None) -> None:
        loop.call_soon_threadsafe(restart_requested.set)

    _install_runtime({}, request_restart)
    runtime_installed = True
    runner = BrokerBridgeRunner(client)
    logger = get_logger(component="v6", runtime=bridge_id)
    host = _V6BridgeHost(
        runner,
        bridge_id,
        logger,
        max_concurrent_events=_positive_int_option(bridge.options, "max_concurrent_events", 32),
        restart_requested=restart_requested,
    )
    restarting = False
    try:
        await runner.start()
        await _emit_lifecycle("before_start")
        await _emit_lifecycle("after_start")
        if restart_requested.is_set():
            outcome = "restart"
        else:
            outcome = await host.serve()
        if outcome == "restart":
            restarting = True
            await _emit_lifecycle("before_process_restart", bridge_id)
        else:
            await _emit_lifecycle("before_process_shutdown", bridge_id)
        await _emit_lifecycle("after_shutdown")
    finally:
        try:
            await runner.stop()
        finally:
            runner.close()
            if runtime_installed:
                _reset_runtime()
    if restarting:
        raise RuntimeError("v6 compatibility bridge requested restart")


def _load_configured_plugins(options: Mapping[str, Any]) -> tuple[str, ...]:
    _reject_legacy_options(options)
    return load_configured_v6_plugins(_string_list_option(options, "v6_plugins"))


def _reject_legacy_options(options: Mapping[str, Any]) -> None:
    legacy = sorted(_LEGACY_OPTION_KEYS.intersection(options))
    if legacy:
        raise RuntimeError("migration_required: v6 bridge does not accept legacy options: " + ", ".join(legacy))
    unsupported = sorted(set(options).difference(_ALLOWED_BRIDGE_OPTION_KEYS))
    if unsupported:
        raise RuntimeError("migration_required: unsupported v6 bridge options: " + ", ".join(unsupported))
    if os.environ.get("LITEYUKI_RUNTIME_GENERATION_DIR"):
        raise RuntimeError("migration_required: managed v6 generations are not supported by the bridge")


def _validate_bridge_settings(
    access: str,
    subscriptions: Sequence[str],
    action_resources: Sequence[Any],
    options: Mapping[str, Any],
) -> None:
    if access != BridgeAccess.LIMITED.value:
        raise RuntimeError("v6 compatibility bridge must use limited access")
    if not subscriptions:
        raise RuntimeError("v6 compatibility bridge must declare at least one subscription")
    if action_resources:
        raise RuntimeError("v6 compatibility bridge must not own platform actions")
    _reject_legacy_options(options)


def _normalized_plugin_names(value: Sequence[str]) -> tuple[str, ...]:
    names = tuple(value)
    if any(not isinstance(name, str) or not name or name != name.strip() for name in names):
        raise ValueError("v6_plugins must contain non-empty trimmed entry point names")
    if len(names) != len(set(names)):
        raise ValueError("v6_plugins must not contain duplicates")
    return names


def _string_list_option(options: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = options.get(key, ())
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"v6 bridge option {key!r} must be an array of strings")
    return _normalized_plugin_names(value)


def _positive_int_option(options: Mapping[str, Any], key: str, default: int) -> int:
    value = options.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"v6 bridge option {key!r} must be a positive integer")
    return value


def _broker_endpoints(endpoint: str) -> dict[LyipLane, str]:
    parsed = urlparse(endpoint)
    if parsed.scheme != "tcp" or parsed.hostname is None or parsed.port is None:
        raise ValueError("broker endpoint must be a valid tcp URL")
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    return {
        LyipLane.CONTROL: f"tcp://{host}:{parsed.port}",
        LyipLane.BUSINESS: f"tcp://{host}:{parsed.port + 1}",
    }


__all__ = ["V6_PLUGIN_ENTRY_POINT_GROUP", "launch", "load_configured_v6_plugins"]
