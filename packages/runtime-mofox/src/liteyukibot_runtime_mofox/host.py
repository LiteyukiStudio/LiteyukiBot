"""Headless Neo-MoFox host that bridges its input and output boundaries."""

from __future__ import annotations

import asyncio
import importlib.metadata
import os
import re
import sys
from collections.abc import Awaitable, Callable, Mapping
from contextvars import ContextVar, Token
from importlib import import_module
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType
from typing import Any

from liteyukibot.events import EventEnvelope
from liteyukibot.logging import configure_runtime_child_logging, get_logger
from liteyukibot.runtime import RuntimeClient
from liteyukibot.runtime.projection import project_managed_plugins
from liteyukibot.runtime.protocol import (
    ActionRequest,
    ActionResponse,
    EventAccepted,
    EventCompleted,
    EventMessage,
    EventTrace,
    Shutdown,
)

from .translate import to_mofox_envelope, to_mofox_event_input, to_send_action

type TextSink = Callable[[str], Awaitable[None]]

NEO_MOFOX_REQUIREMENT = (
    "neo-mofox @ git+https://github.com/MoFox-Studio/Neo-MoFox.git@"
    "e2ee2ff73b494428bbdfd983c7569c6f074a9c76"
)


class _HeadlessMessageSender:
    """MoFox sender replacement that forwards output to the active Liteyuki event."""

    def __init__(self, sink: ContextVar[TextSink | None]) -> None:
        self._sink = sink

    async def send_message(self, message: Any, adapter_signature: str | None = None) -> bool:
        del adapter_signature
        sink = self._sink.get()
        if sink is None:
            raise RuntimeError("MoFox attempted to send outside an active Liteyuki event")
        text = getattr(message, "processed_plain_text", None)
        if not isinstance(text, str) or not text:
            content = getattr(message, "content", "")
            text = content if isinstance(content, str) else str(content)
        if not text:
            return True
        await sink(text)
        return True


class MoFoxHeadlessEngine:
    """Own a private Neo-MoFox lifecycle without any source platform adapter."""

    def __init__(self, state_directory: Path, options: Mapping[str, object]) -> None:
        self.state_directory = state_directory
        self.options = options
        self._bot: Any | None = None
        self._previous_cwd: Path | None = None
        self._sink: ContextVar[TextSink | None] = ContextVar("liteyuki_mofox_sink", default=None)

    async def start(self) -> None:
        root = self.state_directory / "mofox"
        root.mkdir(parents=True, exist_ok=True)
        self._previous_cwd = Path.cwd()
        try:
            os.chdir(root)
            _enforce_headless_config(root / "config" / "core.toml")
            _prepare_managed_plugins(root, self.options)
            _install_upstream_namespace()
            bot_type = import_module("src.app.runtime.bot").Bot
            bot = bot_type(config_path="config/core.toml", plugins_dir="plugins", log_dir="logs")
            await bot.initialize()
            if bot.scheduler is None:
                raise RuntimeError("Neo-MoFox headless lifecycle did not create a scheduler")
            await bot.scheduler.start()
            bot._running = True
            sender_module = import_module("src.core.transport.message_send")
            sender_module.set_message_sender(_HeadlessMessageSender(self._sink))
            self._bot = bot
        except BaseException:
            self._restore_working_directory()
            raise

    async def process(self, event: EventEnvelope, sink: TextSink) -> None:
        bot = self._bot
        if bot is None or bot.message_receiver is None:
            raise RuntimeError("MoFox headless lifecycle is not started")
        translated = to_mofox_event_input(event)
        token: Token[TextSink | None] = self._sink.set(sink)
        try:
            await bot.message_receiver.receive_envelope(
                to_mofox_envelope(translated),
                adapter_signature="liteyuki:adapter:injected",
            )
        finally:
            self._sink.reset(token)

    async def close(self) -> None:
        bot, self._bot = self._bot, None
        try:
            if bot is not None:
                await bot.shutdown()
        finally:
            self._restore_working_directory()

    def _restore_working_directory(self) -> None:
        previous, self._previous_cwd = self._previous_cwd, None
        if previous is not None:
            os.chdir(previous)


class MoFoxRuntimeHost:
    def __init__(self, client: RuntimeClient, engine: MoFoxHeadlessEngine, *, max_concurrent_events: int) -> None:
        self.client = client
        self.engine = engine
        self.max_concurrent_events = max_concurrent_events
        self.logger = get_logger(component="mofox", runtime=os.environ.get("LITEYUKI_RUNTIME_ID", "mofox"))
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
                        error="MoFox agent runtime does not own a platform action adapter",
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
            to_mofox_event_input(event)
        except ValueError:
            await self.client.send(
                EventAccepted(
                    correlation_id=message.correlation_id,
                    status="invalid",
                    detail="MoFox agent runtime requires a valid message EventEnvelope",
                )
            )
            return
        if len(self._tasks) >= self.max_concurrent_events:
            await self.client.send(
                EventAccepted(
                    correlation_id=message.correlation_id,
                    status="overloaded",
                    detail="MoFox agent runtime event capacity is exhausted",
                )
            )
            return
        await self.client.send(EventAccepted(correlation_id=message.correlation_id, status="accepted"))
        task = asyncio.create_task(
            self._process_event(message.correlation_id, event, message.trace),
            name=f"mofox-event:{message.correlation_id}",
        )
        self._tasks.add(task)
        task.add_done_callback(self._event_finished)

    def _event_finished(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            self.logger.error("MoFox event task failed: {}", error)

    async def _process_event(
        self,
        correlation_id: str,
        event: EventEnvelope,
        trace: EventTrace | None,
    ) -> None:
        async def emit(text: str) -> None:
            action = to_send_action(event, text)
            result = await self.client.execute_action(
                action.action_id,
                action.model_dump(mode="json"),
                delivery_correlation_id=correlation_id,
            )
            if not result.ok:
                raise RuntimeError(result.error or "source runtime rejected MoFox output")

        try:
            await self.engine.process(event, emit)
        except Exception as error:
            self.logger.bind(
                correlation_id=correlation_id,
                trace_id=trace.trace_id if trace is not None else None,
            ).error("MoFox event failed: {}", error)
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
    logger = get_logger(component="mofox", runtime=os.environ.get("LITEYUKI_RUNTIME_ID", "mofox"))
    client = RuntimeClient.from_environment("mofox")
    host: MoFoxRuntimeHost | None = None
    try:
        logger.info("starting MoFox headless runtime")
        options = await client.connect()
        state_directory = Path(os.environ["LITEYUKI_RUNTIME_STATE_DIR"])
        engine = MoFoxHeadlessEngine(state_directory, options)
        await engine.start()
        host = MoFoxRuntimeHost(
            client,
            engine,
            max_concurrent_events=_positive_int(options, "max_concurrent_events", 8),
        )
        await client.ready(
            ("runtime.events.receive", "runtime.events.complete", "runtime.actions.send", "mofox.chatter")
        )
        logger.info("MoFox headless runtime is ready")
        await host.serve()
    except Exception as error:
        logger.error("MoFox headless runtime failed: {}", error)
        raise
    finally:
        if host is not None:
            await host.close()
        elif "engine" in locals():
            await engine.close()
        await client.close()
        logger.info("MoFox headless runtime stopped")


def _positive_int(options: Mapping[str, object], key: str, default: int) -> int:
    value = options.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"MoFox runtime option {key!r} must be a positive integer")
    return value


def _install_upstream_namespace() -> None:
    """Restore Neo-MoFox's ``src.*`` imports from its installed wheel layout.

    Neo-MoFox publishes ``app``, ``core``, and ``kernel`` as top-level wheel
    directories while its source retains absolute ``src.*`` imports. The bridge
    exists only in the isolated child runtime process and points solely at the
    installed ``neo-mofox`` distribution root.
    """
    try:
        distribution = importlib.metadata.distribution("neo-mofox")
    except importlib.metadata.PackageNotFoundError as error:
        raise RuntimeError(f"Neo-MoFox must be installed before this runtime: {NEO_MOFOX_REQUIREMENT}") from error
    distribution_root = Path(str(distribution.locate_file("")))
    if not all((distribution_root / name).is_dir() for name in ("app", "core", "kernel")):
        raise RuntimeError(f"neo-mofox installation is missing its runtime modules: {distribution_root}")
    namespace = ModuleType("src")
    namespace.__package__ = "src"
    namespace.__path__ = [str(distribution_root)]
    namespace.__spec__ = ModuleSpec("src", loader=None, is_package=True)
    sys.modules["src"] = namespace


def _enforce_headless_config(path: Path) -> None:
    """Keep Neo-MoFox's private lifecycle non-interactive and non-listening."""
    document = path.read_text(encoding="utf-8") if path.is_file() else ""
    for section, key in (
        ("bot", "llm_preflight_check"),
        ("bot", "enable_watchdog"),
        ("http_router", "enable_http_router"),
        ("plugin_deps", "enabled"),
        ("plugin_market", "enabled"),
    ):
        document = _set_toml_boolean(document, section, key, False)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding="utf-8")


def _prepare_managed_plugins(root: Path, options: Mapping[str, object]) -> None:
    generation = os.environ.get("LITEYUKI_RUNTIME_GENERATION_DIR")
    if generation is None:
        return
    mode = options.get("projection_mode", "copy")
    if not isinstance(mode, str):
        raise ValueError("MoFox runtime option 'projection_mode' must be a string")
    project_managed_plugins(
        generation,
        root / "plugins",
        root / "managed-plugin-backups",
        mode=mode,
    )


def _set_toml_boolean(document: str, section: str, key: str, value: bool) -> str:
    """Replace one simple TOML boolean while preserving unrelated user settings."""
    rendered = "true" if value else "false"
    section_pattern = re.compile(
        rf"(?ms)(^\[{re.escape(section)}\]\r?\n)(.*?)(?=^\[|\Z)",
    )
    section_match = section_pattern.search(document)
    if section_match is None:
        separator = "" if not document or document.endswith("\n") else "\n"
        return f"{document}{separator}[{section}]\n{key} = {rendered}\n"
    body = section_match.group(2)
    key_pattern = re.compile(rf"(?m)^{re.escape(key)}\s*=.*$")
    if key_pattern.search(body):
        replacement_body = key_pattern.sub(f"{key} = {rendered}", body, count=1)
    else:
        replacement_body = f"{body}{key} = {rendered}\n"
    return f"{document[:section_match.start(2)]}{replacement_body}{document[section_match.end(2):]}"
