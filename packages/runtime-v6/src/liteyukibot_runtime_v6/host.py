"""LiteyukiBot v6 plugin compatibility child runtime."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping, Sequence
from typing import Any

from liteyuki.bot import _emit_lifecycle, _install_runtime, _reset_runtime
from liteyuki.plugin import load_plugin, load_plugins
from liteyuki.session.on import _dispatch_matchers

from liteyukibot.events import EventEnvelope
from liteyukibot.logging import configure_runtime_child_logging, get_logger
from liteyukibot.runtime import RuntimeClient
from liteyukibot.runtime.protocol import (
    ActionRequest,
    ActionResponse,
    EventAccepted,
    EventMessage,
    Shutdown,
)

from .events import reply_to_action, to_legacy_message_event


class _V6RuntimeHost:
    def __init__(
        self,
        client: RuntimeClient,
        logger: Any,
        *,
        max_concurrent_events: int,
        action_timeout_seconds: float,
    ) -> None:
        self.client = client
        self.logger = logger
        self.max_concurrent_events = max_concurrent_events
        self.action_timeout_seconds = action_timeout_seconds
        self._event_tasks: set[asyncio.Task[None]] = set()

    async def serve(self, restart_requested: asyncio.Event) -> str:
        while True:
            incoming = asyncio.create_task(self.client.receive(), name="v6-runtime-receive")
            restart = asyncio.create_task(
                restart_requested.wait(),
                name="v6-runtime-restart",
            )
            done, pending = await asyncio.wait(
                (incoming, restart),
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            if restart in done and restart.result():
                return "restart"

            message = incoming.result()
            if isinstance(message, Shutdown):
                return "shutdown"
            if isinstance(message, ActionRequest):
                await self.client.send(
                    ActionResponse(
                        correlation_id=message.correlation_id,
                        ok=False,
                        error="v6 compatibility plugins do not expose a protocol adapter",
                    )
                )
            elif isinstance(message, EventMessage):
                await self._accept_event(message)
            elif isinstance(message, ActionResponse):
                self.logger.warning(
                    "ignored unmatched v6 Action response {}",
                    message.correlation_id,
                )

    async def close(self) -> None:
        tasks = tuple(self._event_tasks)
        self._event_tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _accept_event(self, message: EventMessage) -> None:
        if len(self._event_tasks) >= self.max_concurrent_events:
            await self.client.send(
                EventAccepted(
                    correlation_id=message.correlation_id,
                    status="overloaded",
                    detail="v6 runtime event capacity is exhausted",
                )
            )
            return
        task = asyncio.create_task(
            self._process_event(message),
            name=f"v6-event:{message.correlation_id}",
        )
        self._event_tasks.add(task)
        task.add_done_callback(self._event_finished)

    def _event_finished(self, task: asyncio.Task[None]) -> None:
        self._event_tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            self.logger.error("v6 event task failed: {}", error)

    async def _process_event(self, message: EventMessage) -> None:
        try:
            envelope = EventEnvelope.model_validate(message.payload)
        except ValueError as error:
            self.logger.warning("v6 runtime rejected invalid EventEnvelope: {}", error)
            await self.client.send(
                EventAccepted(
                    correlation_id=message.correlation_id,
                    status="invalid",
                    detail="invalid EventEnvelope",
                )
            )
            return

        event = to_legacy_message_event(envelope)
        if event is not None:
            try:
                result = await _dispatch_matchers(event)
                if result.failures:
                    self.logger.warning(
                        "v6 event {} completed with {} matcher failure(s)",
                        envelope.id,
                        len(result.failures),
                    )
            except Exception as error:
                self.logger.exception("v6 matcher dispatch failed for {}: {}", envelope.id, error)
            for reply in event._drain_replies():
                try:
                    action = reply_to_action(reply, envelope)
                    response = await self.client.execute_action(
                        action.action_id,
                        action.model_dump(mode="json"),
                        timeout_seconds=self.action_timeout_seconds,
                    )
                    if not response.ok:
                        self.logger.warning(
                            "v6 reply Action {} failed: {}",
                            action.action_id,
                            response.error or "runtime rejected the Action",
                        )
                except Exception as error:
                    self.logger.exception("v6 reply failed for event {}: {}", envelope.id, error)

        await self.client.send(
            EventAccepted(
                correlation_id=message.correlation_id,
                status="accepted",
            )
        )


async def run() -> None:
    configure_runtime_child_logging()
    logger = get_logger(component="legacy", runtime=os.environ.get("LITEYUKI_RUNTIME_ID", "v6"))
    runtime_id = os.environ["LITEYUKI_RUNTIME_ID"]
    client = RuntimeClient.from_environment("v6")
    runtime_installed = False
    restarting = False
    host: _V6RuntimeHost | None = None
    try:
        logger.info("starting v6 compatibility runtime")
        options = await client.connect()
        legacy_config = _mapping_option(options, "config")
        restart_requested = asyncio.Event()
        loop = asyncio.get_running_loop()

        def request_restart(_name: str | None) -> None:
            loop.call_soon_threadsafe(restart_requested.set)

        _install_runtime(legacy_config, request_restart)
        runtime_installed = True
        _load_configured_plugins(options)
        await _emit_lifecycle("before_start")
        await _emit_lifecycle("after_start")
        if int(os.environ.get("LITEYUKI_RUNTIME_RESTART_COUNT", "0")) > 0:
            await _emit_lifecycle("after_restart")
        host = _V6RuntimeHost(
            client,
            logger,
            max_concurrent_events=_positive_int_option(options, "max_concurrent_events", 32),
            action_timeout_seconds=_positive_float_option(
                options,
                "action_timeout_seconds",
                10.0,
            ),
        )
        await client.ready(
            (
                "v6.plugins",
                "v6.lifecycle",
                "runtime.events.receive",
                "runtime.actions.send",
            )
        )
        logger.info("v6 compatibility runtime is ready")
        outcome = await host.serve(restart_requested)
        await host.close()
        if outcome == "restart":
            restarting = True
            await _emit_lifecycle("before_process_restart", runtime_id)
        else:
            await _emit_lifecycle("before_process_shutdown", runtime_id)
        await _emit_lifecycle("after_shutdown")
    finally:
        if host is not None:
            await host.close()
        if runtime_installed:
            _reset_runtime()
        await client.close()
        logger.info("v6 compatibility runtime stopped")
    if restarting:
        logger.info("v6 compatibility runtime requested restart")
        raise RuntimeError("v6 compatibility runtime requested restart")


def _mapping_option(options: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = options.get(key, {})
    if not isinstance(value, Mapping):
        raise ValueError(f"v6 runtime option {key!r} must be an object")
    return value


def _string_list_option(options: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = options.get(key, [])
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"v6 runtime option {key!r} must be an array of strings")
    if any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"v6 runtime option {key!r} must contain non-empty strings")
    return tuple(value)


def _load_configured_plugins(options: Mapping[str, Any]) -> None:
    failed = [name for name in _string_list_option(options, "plugins") if load_plugin(name) is None]
    directories = _string_list_option(options, "plugin_dirs")
    loaded_from_directories = load_plugins(*directories, ignore_warning=False)
    if failed:
        raise RuntimeError(f"failed to load v6 plugins: {', '.join(failed)}")
    if directories and not loaded_from_directories:
        raise RuntimeError("configured v6 plugin directories did not load any plugins")


def _positive_int_option(options: Mapping[str, Any], key: str, default: int) -> int:
    value = options.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"v6 runtime option {key!r} must be a positive integer")
    return value


def _positive_float_option(options: Mapping[str, Any], key: str, default: float) -> float:
    value = options.get(key, default)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"v6 runtime option {key!r} must be a positive number")
    return float(value)


__all__ = ["run"]
