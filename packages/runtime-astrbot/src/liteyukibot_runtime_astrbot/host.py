"""Headless AstrBot host that maps Pipeline output back to Liteyuki actions."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from importlib import import_module
from pathlib import Path
from typing import Any

from liteyukibot.events import EventEnvelope
from liteyukibot.logging import configure_runtime_child_logging, get_logger
from liteyukibot.runtime import RuntimeClient
from liteyukibot.runtime.protocol import (
    ActionRequest,
    ActionResponse,
    EventAccepted,
    EventCompleted,
    EventMessage,
    EventTrace,
    Shutdown,
)

from .translate import AstrEventInput, to_astr_event_input, to_send_action

type TextSink = Callable[[str], Awaitable[None]]


class AstrBotLogBridge:
    """Forward AstrBot's public LogBroker records into child Yukilog output."""

    def __init__(self, broker: Any, logger: Any) -> None:
        self._broker = broker
        self._logger = logger
        self._queue: Any | None = None
        self._task: asyncio.Task[None] | None = None

    def start(self, log_manager: Any, source_logger: Any) -> None:
        log_manager.set_queue_handler(source_logger, self._broker)
        self._queue = self._broker.register()
        self._task = asyncio.create_task(self._forward(), name="astrbot-log-bridge")

    async def close(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if self._queue is not None:
            with suppress(ValueError):
                self._broker.unregister(self._queue)
            self._queue = None

    async def _forward(self) -> None:
        assert self._queue is not None
        while True:
            entry = await self._queue.get()
            if not isinstance(entry, Mapping):
                continue
            level = str(entry.get("level", "INFO")).lower()
            message = str(entry.get("data", ""))
            category = str(entry.get("category", "system"))
            logger = self._logger.bind(upstream="astrbot", upstream_category=category)
            getattr(logger, level, logger.info)("{}", message)


class AstrBotHeadlessEngine:
    """Own an isolated AstrBot lifecycle without any AstrBot platform adapter."""

    def __init__(self, state_directory: Path, options: Mapping[str, object], logger: Any) -> None:
        self.state_directory = state_directory
        self.options = options
        self._lifecycle: Any | None = None
        self._schedulers: Mapping[str, Any] = {}
        self._logger = logger
        self._log_bridge: AstrBotLogBridge | None = None

    async def start(self) -> None:
        root = self.state_directory / "astrbot"
        root.mkdir(parents=True, exist_ok=True)
        os.environ["ASTRBOT_ROOT"] = str(root)
        astrbot_core = import_module("astrbot.core")
        log_broker_type = astrbot_core.LogBroker
        lifecycle_type = import_module("astrbot.core.core_lifecycle").AstrBotCoreLifecycle
        database_type = import_module("astrbot.core.db.sqlite").SQLiteDatabase

        broker = log_broker_type()
        bridge = AstrBotLogBridge(broker, self._logger)
        bridge.start(astrbot_core.LogManager, astrbot_core.logger)
        lifecycle = lifecycle_type(broker, database_type(str(root / "astrbot.db")))
        try:
            await lifecycle.initialize()
        except BaseException:
            await bridge.close()
            raise
        self._lifecycle = lifecycle
        self._schedulers = lifecycle.pipeline_scheduler_mapping
        self._log_bridge = bridge
        if not self._schedulers:
            raise RuntimeError("AstrBot headless lifecycle did not create a PipelineScheduler")

    async def process(self, event: EventEnvelope, sink: TextSink) -> None:
        if self._lifecycle is None:
            raise RuntimeError("AstrBot headless lifecycle is not started")
        translated = to_astr_event_input(event)
        scheduler = self._scheduler()
        await scheduler.execute(_create_astr_event(translated, sink))

    async def close(self) -> None:
        lifecycle, self._lifecycle = self._lifecycle, None
        bridge, self._log_bridge = self._log_bridge, None
        self._schedulers = {}
        try:
            if lifecycle is not None:
                await lifecycle.stop()
        finally:
            if bridge is not None:
                await bridge.close()

    def _scheduler(self) -> Any:
        requested = self.options.get("scheduler_id")
        if requested is None and len(self._schedulers) == 1:
            return next(iter(self._schedulers.values()))
        if not isinstance(requested, str) or not requested:
            raise RuntimeError("AstrBot headless runtime requires options.scheduler_id when multiple schedulers exist")
        try:
            return self._schedulers[requested]
        except KeyError as error:
            raise RuntimeError(f"AstrBot scheduler {requested!r} is not available") from error


class AstrBotRuntimeHost:
    def __init__(
        self,
        client: RuntimeClient,
        engine: AstrBotHeadlessEngine,
        *,
        max_concurrent_events: int,
    ) -> None:
        self.client = client
        self.engine = engine
        self.max_concurrent_events = max_concurrent_events
        self.logger = get_logger(component="astrbot", runtime=os.environ.get("LITEYUKI_RUNTIME_ID", "astrbot"))
        self._tasks: set[asyncio.Task[None]] = set()

    async def serve(self) -> None:
        while True:
            message = await self.client.receive()
            if isinstance(message, Shutdown):
                return
            if isinstance(message, ActionRequest):
                await self.client.send(
                    ActionResponse(
                        correlation_id=message.correlation_id,
                        ok=False,
                        error="AstrBot agent runtime does not own a platform action adapter",
                    )
                )
            elif isinstance(message, EventMessage):
                await self._accept_event(message)

    async def close(self) -> None:
        tasks = tuple(self._tasks)
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self.engine.close()

    async def _accept_event(self, message: EventMessage) -> None:
        try:
            event = EventEnvelope.model_validate(message.payload)
            to_astr_event_input(event)
        except ValueError:
            await self.client.send(
                EventAccepted(
                    correlation_id=message.correlation_id,
                    status="invalid",
                    detail="AstrBot agent runtime requires a valid message EventEnvelope",
                )
            )
            return
        if len(self._tasks) >= self.max_concurrent_events:
            await self.client.send(
                EventAccepted(
                    correlation_id=message.correlation_id,
                    status="overloaded",
                    detail="AstrBot agent runtime event capacity is exhausted",
                )
            )
            return
        await self.client.send(EventAccepted(correlation_id=message.correlation_id, status="accepted"))
        task = asyncio.create_task(
            self._process_event(message.correlation_id, event, message.trace),
            name=f"astrbot-event:{message.correlation_id}",
        )
        self._tasks.add(task)
        task.add_done_callback(self._event_finished)

    def _event_finished(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            self.logger.error("AstrBot event task failed: {}", error)

    async def _process_event(
        self,
        correlation_id: str,
        event: EventEnvelope,
        trace: EventTrace | None,
    ) -> None:
        async def emit(text: str) -> None:
            action = to_send_action(event, text)
            result = await self.client.execute_action(action.action_id, action.model_dump(mode="json"))
            if not result.ok:
                raise RuntimeError(result.error or "source runtime rejected AstrBot output")

        try:
            await self.engine.process(event, emit)
        except Exception as error:
            self.logger.bind(
                correlation_id=correlation_id,
                trace_id=trace.trace_id if trace is not None else None,
            ).error("AstrBot event failed: {}", error)
            await self.client.send(
                EventCompleted(
                    correlation_id=correlation_id,
                    status="failed",
                    detail=f"{type(error).__name__}: {error}",
                )
            )
            raise
        await self.client.send(EventCompleted(correlation_id=correlation_id, status="completed"))


async def run() -> None:
    configure_runtime_child_logging()
    logger = get_logger(component="astrbot", runtime=os.environ.get("LITEYUKI_RUNTIME_ID", "astrbot"))
    client = RuntimeClient.from_environment("astrbot")
    host: AstrBotRuntimeHost | None = None
    try:
        logger.info("starting AstrBot headless runtime")
        options = await client.connect()
        state_directory = Path(os.environ["LITEYUKI_RUNTIME_STATE_DIR"])
        engine = AstrBotHeadlessEngine(state_directory, options, logger)
        await engine.start()
        host = AstrBotRuntimeHost(
            client,
            engine,
            max_concurrent_events=_positive_int(options, "max_concurrent_events", 8),
        )
        await client.ready(
            ("runtime.events.receive", "runtime.events.complete", "runtime.actions.send", "astrbot.pipeline")
        )
        logger.info("AstrBot headless runtime is ready")
        await host.serve()
    except Exception as error:
        logger.error("AstrBot headless runtime failed: {}", error)
        raise
    finally:
        if host is not None:
            await host.close()
        elif "engine" in locals():
            await engine.close()
        await client.close()
        logger.info("AstrBot headless runtime stopped")


def _create_astr_event(value: AstrEventInput, sink: TextSink) -> Any:
    plain_type = import_module("astrbot.core.message.components").Plain
    event_type = import_module("astrbot.core.platform.astr_message_event").AstrMessageEvent
    message_module = import_module("astrbot.core.platform.astrbot_message")
    message_type = message_module.AstrBotMessage
    group_type = message_module.Group
    member_type = message_module.MessageMember
    platform_message_type = import_module("astrbot.core.platform.message_type").MessageType
    metadata_type = import_module("astrbot.core.platform.platform_metadata").PlatformMetadata

    message = message_type()
    message.type = (
        platform_message_type.GROUP_MESSAGE
        if value.conversation_type == "group"
        else platform_message_type.FRIEND_MESSAGE
    )
    message.self_id = value.bot_id
    message.session_id = value.conversation_id
    message.message_id = value.event_id
    message.sender = member_type(value.actor_id or "unknown", value.actor_name)
    message.message = [plain_type(value.text)]
    message.message_str = value.text
    message.raw_message = {"liteyuki_runtime": value.runtime_id, "adapter": value.adapter}
    if value.conversation_type == "group":
        message.group = group_type(value.conversation_id)
    metadata = metadata_type(
        name=f"liteyuki-{value.adapter}",
        description="LiteyukiBot headless AstrBot runtime",
        id=f"liteyuki:{value.runtime_id}:{value.bot_id}",
        support_streaming_message=False,
        support_proactive_message=False,
    )

    class HeadlessAstrEvent(event_type):  # type: ignore[misc,valid-type]
        async def send(self, chain: Any) -> None:
            self._has_send_oper = True
            text = "".join(str(getattr(item, "text", "")) for item in chain.chain)
            if text:
                await sink(text)

        async def send_streaming(self, generator: Any, use_fallback: bool = False) -> None:
            del use_fallback
            async for chain in generator:
                await self.send(chain)

    return HeadlessAstrEvent(value.text, message, metadata, value.conversation_id)


def _positive_int(options: Mapping[str, object], key: str, default: int) -> int:
    value = options.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"AstrBot runtime option {key!r} must be a positive integer")
    return value
