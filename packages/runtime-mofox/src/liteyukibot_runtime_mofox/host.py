"""Headless Neo-MoFox host behind a limited Liteyuki Broker bridge."""

from __future__ import annotations

import asyncio
import importlib.metadata
import os
import re
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextvars import ContextVar, Token
from importlib import import_module
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import zmq.asyncio

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
from liteyukibot.events import EventEnvelope, Message, Segment
from liteyukibot.logging import get_logger
from liteyukibot.lyip import LyipLane

from .translate import to_mofox_envelope, to_mofox_event_input

type MessageSink = Callable[[Message], Awaitable[None]]

NEO_MOFOX_REQUIREMENT = (
    "neo-mofox @ git+https://github.com/MoFox-Studio/Neo-MoFox.git@e2ee2ff73b494428bbdfd983c7569c6f074a9c76"
)
_ALLOWED_BRIDGE_OPTION_KEYS = frozenset({"workspace", "max_concurrent_events"})


class _HeadlessMessageSender:
    """Forward upstream output to the active source bridge delivery."""

    def __init__(self, sink: ContextVar[MessageSink | None]) -> None:
        """Initialize the headless message sender.

        Args:
            sink: The sink value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_HeadlessMessageSender.__init__`. It performs the local
            state transition directly and is not a stable extension boundary.
        """
        self._sink = sink

    async def send_message(self, message: Any, adapter_signature: str | None = None) -> bool:
        """Send message.

        Args:
            message: Message content associated with the operation.
            adapter_signature: The adapter signature value used by the operation.

        Returns:
            Whether the requested condition is satisfied.

        Notes:
            Internal implementation detail for `_HeadlessMessageSender.send_message`. It delegates to `get`,
            `_portable_message_from_mofox`, `sink`, `getattr` while keeping intermediate state local to the
            owning operation.
        """
        del adapter_signature
        sink = self._sink.get()
        if sink is None:
            raise RuntimeError("MoFox attempted to send outside an active Liteyuki event")
        structured = _portable_message_from_mofox(message)
        if structured is not None:
            await sink(structured)
            return True
        text = getattr(message, "processed_plain_text", None)
        if not isinstance(text, str) or not text:
            content = getattr(message, "content", "")
            text = content if isinstance(content, str) else str(content)
        if not text:
            return True
        await sink(Message(segments=(Segment(type="text", data={"text": text}),)))
        return True


def _portable_message_from_mofox(message: Any) -> Message | None:
    """Use an upstream structured reply when it matches the portable schema.

    Args:
        message: Message content associated with the operation.

    Returns:
        The `Message | None` result produced by the operation.

    Notes:
        Internal implementation detail for `_portable_message_from_mofox`. It delegates to `getattr`,
        `get`, `append`, `model_validate` while keeping intermediate state local to the owning
        operation.
    """

    candidate = getattr(message, "message_segment", None)
    if candidate is None:
        candidate = getattr(message, "content", None)
    if not isinstance(candidate, list) or not candidate:
        return None
    segments: list[Segment] = []
    for value in candidate:
        if not isinstance(value, Mapping) or not isinstance(value.get("type"), str):
            raise ValueError("MoFox structured output segments must be objects with type")
        data = value.get("data")
        if value["type"] == "text" and isinstance(data, str):
            segments.append(Segment(type="text", data={"text": data}))
            continue
        if not isinstance(data, Mapping):
            raise ValueError("MoFox structured output segment data must be an object")
        segments.append(Segment.model_validate({"type": value["type"], "data": dict(data)}))
    return Message(segments=tuple(segments))


class MoFoxHeadlessEngine:
    """Own one isolated Neo-MoFox workspace without managed projections."""

    def __init__(self, workspace: Path, options: Mapping[str, object]) -> None:
        """Initialize the mo fox headless engine.

        Args:
            workspace: The workspace value used by the operation.
            options: Validated optional settings for the operation.

        Returns:
            None.
        """
        self.workspace = workspace
        self.options = options
        self._bot: Any | None = None
        self._previous_cwd: Path | None = None
        self._sink: ContextVar[MessageSink | None] = ContextVar("liteyuki_mofox_sink", default=None)
        self._previous_src: ModuleType | None = None
        self._had_src_module = False

    async def start(self) -> None:
        """Start the mo fox headless engine.

        Returns:
            None.
        """
        root = self.workspace.resolve()
        root.mkdir(parents=True, exist_ok=True)
        self._previous_cwd = Path.cwd()
        self._had_src_module = "src" in sys.modules
        self._previous_src = sys.modules.get("src")
        try:
            os.chdir(root)
            _enforce_headless_config(root / "config" / "core.toml")
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
            self._restore_upstream_namespace()
            self._restore_working_directory()
            raise

    async def process(self, event: EventEnvelope, sink: MessageSink) -> None:
        """Implement the process operation for the mo fox headless engine.

        Args:
            event: Event associated with the operation.
            sink: The sink value used by the operation.

        Returns:
            None.
        """
        bot = self._bot
        if bot is None or bot.message_receiver is None:
            raise RuntimeError("MoFox headless lifecycle is not started")
        translated = to_mofox_event_input(event)
        token: Token[MessageSink | None] = self._sink.set(sink)
        try:
            await bot.message_receiver.receive_envelope(
                to_mofox_envelope(translated),
                adapter_signature="liteyuki:adapter:injected",
            )
        finally:
            self._sink.reset(token)

    async def close(self) -> None:
        """Close the mo fox headless engine and release its owned resources.

        Returns:
            None.
        """
        bot, self._bot = self._bot, None
        try:
            if bot is not None:
                await bot.shutdown()
        finally:
            self._restore_upstream_namespace()
            self._restore_working_directory()

    def _restore_working_directory(self) -> None:
        """Implement the restore working directory operation for the mo fox headless engine.

        Returns:
            None.

        Notes:
            Internal implementation detail for `MoFoxHeadlessEngine._restore_working_directory`. It
            delegates to `chdir` while keeping intermediate state local to the owning operation.
        """
        previous, self._previous_cwd = self._previous_cwd, None
        if previous is not None:
            os.chdir(previous)

    def _restore_upstream_namespace(self) -> None:
        """Implement the restore upstream namespace operation for the mo fox headless engine.

        Returns:
            None.

        Notes:
            Internal implementation detail for `MoFoxHeadlessEngine._restore_upstream_namespace`. It
            delegates to `pop` while keeping intermediate state local to the owning operation.
        """
        if self._previous_cwd is None and not self._had_src_module:
            return
        if self._had_src_module:
            if self._previous_src is not None:
                sys.modules["src"] = self._previous_src
        else:
            sys.modules.pop("src", None)
        self._previous_src = None
        self._had_src_module = False


class MoFoxBridgeHost:
    """Represent the mo fox bridge host contract."""
    def __init__(self, engine: MoFoxHeadlessEngine, *, max_concurrent_events: int) -> None:
        """Initialize the mo fox bridge host.

        Args:
            engine: The engine value used by the operation.
            max_concurrent_events: Maximum number of events dispatched concurrently.

        Returns:
            None.
        """
        self.engine = engine
        self._capacity = asyncio.Semaphore(max_concurrent_events)

    async def handle_delivery(self, delivery: BrokerDelivery) -> None:
        """Handle delivery.

        Args:
            delivery: The delivery value used by the operation.

        Returns:
            None.
        """
        async with self._capacity:
            broker_event = delivery.message.event
            event = EventEnvelope.model_validate(broker_event.payload)
            if event.runtime_id != broker_event.source_bridge_id:
                raise ValueError("MoFox event runtime_id does not match its broker source bridge")
            to_mofox_event_input(event)

            async def emit(message: Message) -> None:
                payload = MessageSendPayload(
                    bot_id=event.bot_id,
                    message=message,
                    conversation=event.conversation,
                    reply_token=event.reply_token,
                )
                result = await delivery.request_action(
                    correlation_id=f"mofox:{event.id}:{uuid4()}",
                    kind=MESSAGE_SEND_KIND,
                    resource_key=message_send_resource_key(event.runtime_id, event.bot_id),
                    payload=payload.model_dump(mode="json", exclude_none=True),
                )
                if not result.success:
                    raise RuntimeError(f"source bridge rejected message.send: {result.payload}")

            await self.engine.process(event, emit)


async def launch(settings: AppSettings, bridge_id: str, token: str) -> None:
    """Launch one limited MoFox bridge through the standalone Broker.

    Args:
        settings: Validated application settings.
        bridge_id: Stable identifier for the bridge.
        token: Authentication token presented at the boundary.

    Returns:
        None.
    """

    bridge = settings.broker.bridges.get(bridge_id)
    if bridge is None:
        raise RuntimeError(f"broker bridge {bridge_id!r} is not configured")
    if bridge.kind != "mofox":
        raise RuntimeError(f"broker bridge {bridge_id!r} is not a MoFox bridge")
    _validate_bridge_settings(bridge.access, bridge.subscriptions, bridge.action_resources, bridge.options)

    manifest = BridgeManifest(
        bridge_id=bridge_id,
        access=BridgeAccess.LIMITED,
        subscriptions=bridge.subscriptions,
    )
    client = BridgeClient(
        context=zmq.asyncio.Context.instance(),
        endpoints=_broker_endpoints(settings.broker.endpoint),
        generation=settings.broker.generation,
        identity=f"mofox:{bridge_id}:{uuid4()}".encode("ascii"),
        manifest=manifest,
        instance_token=token,
    )
    engine = MoFoxHeadlessEngine(_workspace_path(settings, bridge_id, bridge.options), bridge.options)
    host = MoFoxBridgeHost(
        engine,
        max_concurrent_events=_positive_int(bridge.options, "max_concurrent_events", 8),
    )
    runner = BrokerBridgeRunner(client, event_handler=host.handle_delivery)
    logger = get_logger(component="mofox", runtime=bridge_id)
    try:
        await runner.start()
        await engine.start()
        logger.info("MoFox compatibility bridge {} is ready", bridge_id)
        await runner.serve_forever()
    finally:
        try:
            await engine.close()
        finally:
            try:
                await runner.stop()
            finally:
                runner.close()


def _validate_bridge_settings(
    access: str,
    subscriptions: Sequence[str],
    action_resources: Sequence[Any],
    options: Mapping[str, Any],
) -> None:
    """Validate bridge settings.

    Args:
        access: The access value used by the operation.
        subscriptions: The subscriptions value used by the operation.
        action_resources: The action resources value used by the operation.
        options: Validated optional settings for the operation.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_validate_bridge_settings`. It delegates to `sorted`,
        `difference`, `join`, `get` while keeping intermediate state local to the owning operation.
    """
    if access != BridgeAccess.LIMITED.value:
        raise RuntimeError("MoFox compatibility bridge must use limited access")
    if not subscriptions:
        raise RuntimeError("MoFox compatibility bridge must declare at least one subscription")
    if action_resources:
        raise RuntimeError("MoFox compatibility bridge must not own platform actions")
    unsupported = sorted(set(options).difference(_ALLOWED_BRIDGE_OPTION_KEYS))
    if unsupported:
        raise RuntimeError(
            "migration_required: MoFox managed projection options are removed: " + ", ".join(unsupported)
        )
    if os.environ.get("LITEYUKI_RUNTIME_GENERATION_DIR"):
        raise RuntimeError("migration_required: managed MoFox generations are not supported by the bridge")


def _workspace_path(settings: AppSettings, bridge_id: str, options: Mapping[str, object]) -> Path:
    """Implement the workspace path operation for the component.

    Args:
        settings: Validated application settings.
        bridge_id: Stable identifier for the bridge.
        options: Validated optional settings for the operation.

    Returns:
        The `Path` result produced by the operation.

    Notes:
        Internal implementation detail for `_workspace_path`. It delegates to `get`, `strip`,
        `expanduser`, `resolve` while keeping intermediate state local to the owning operation.
    """
    configured = options.get("workspace")
    if configured is None:
        path = settings.core.data_dir / "bridges" / bridge_id / "mofox"
    elif isinstance(configured, str) and configured.strip():
        path = Path(configured).expanduser()
    else:
        raise ValueError("MoFox bridge option 'workspace' must be a non-empty string")
    resolved = path.resolve()
    if resolved == settings.core.data_dir.resolve():
        raise ValueError("MoFox workspace must be isolated below its own directory")
    return resolved


def _positive_int(options: Mapping[str, object], key: str, default: int) -> int:
    """Implement the positive int operation for the component.

    Args:
        options: Validated optional settings for the operation.
        key: Stable FIFO ordering key for the queued work.
        default: The default value used by the operation.

    Returns:
        The `int` result produced by the operation.

    Notes:
        Internal implementation detail for `_positive_int`. It delegates to `get` while keeping
        intermediate state local to the owning operation.
    """
    value = options.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"MoFox bridge option {key!r} must be a positive integer")
    return value


def _install_upstream_namespace() -> None:
    """Restore Neo-MoFox's ``src.*`` imports from its installed wheel layout.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_install_upstream_namespace`. It delegates to
        `distribution`, `locate_file`, `all`, `is_dir` while keeping intermediate state local to the
        owning operation.
    """

    try:
        distribution = importlib.metadata.distribution("neo-mofox")
    except importlib.metadata.PackageNotFoundError as error:
        raise RuntimeError(f"Neo-MoFox must be installed before this bridge: {NEO_MOFOX_REQUIREMENT}") from error
    distribution_root = Path(str(distribution.locate_file("")))
    if not all((distribution_root / name).is_dir() for name in ("app", "core", "kernel")):
        raise RuntimeError(f"neo-mofox installation is missing its runtime modules: {distribution_root}")
    namespace = ModuleType("src")
    namespace.__package__ = "src"
    namespace.__path__ = [str(distribution_root)]
    namespace.__spec__ = ModuleSpec("src", loader=None, is_package=True)
    sys.modules["src"] = namespace


def _enforce_headless_config(path: Path) -> None:
    """Keep Neo-MoFox's private lifecycle non-interactive and non-listening.

    Args:
        path: Filesystem or logical resource path.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_enforce_headless_config`. It delegates to `is_file`,
        `read_text`, `_set_toml_boolean`, `mkdir` while keeping intermediate state local to the owning
        operation.
    """

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


def _set_toml_boolean(document: str, section: str, key: str, value: bool) -> str:
    """Replace one simple TOML boolean while preserving unrelated user settings.

    Args:
        document: The document value used by the operation.
        section: The section value used by the operation.
        key: Stable FIFO ordering key for the queued work.
        value: Value to validate, transform, or store.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_set_toml_boolean`. It delegates to `compile`, `escape`,
        `search`, `endswith` while keeping intermediate state local to the owning operation.
    """

    rendered = "true" if value else "false"
    section_pattern = re.compile(rf"(?ms)(^\[{re.escape(section)}\]\r?\n)(.*?)(?=^\[|\Z)")
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
    return f"{document[: section_match.start(2)]}{replacement_body}{document[section_match.end(2) :]}"


def _broker_endpoints(endpoint: str) -> dict[LyipLane, str]:
    """Implement the broker endpoints operation for the component.

    Args:
        endpoint: Transport endpoint used for the connection.

    Returns:
        The `dict[LyipLane, str]` result produced by the operation.

    Notes:
        Internal implementation detail for `_broker_endpoints`. It delegates to `urlparse` while keeping
        intermediate state local to the owning operation.
    """
    parsed = urlparse(endpoint)
    if parsed.scheme != "tcp" or parsed.hostname is None or parsed.port is None:
        raise ValueError("broker endpoint must be a valid tcp URL")
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    return {
        LyipLane.CONTROL: f"tcp://{host}:{parsed.port}",
        LyipLane.BUSINESS: f"tcp://{host}:{parsed.port + 1}",
    }


__all__ = [
    "NEO_MOFOX_REQUIREMENT",
    "MoFoxBridgeHost",
    "MoFoxHeadlessEngine",
    "_enforce_headless_config",
    "_install_upstream_namespace",
    "_workspace_path",
    "launch",
]
