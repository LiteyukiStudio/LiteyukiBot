"""AstrBot's native-platform gateway for the standalone Liteyuki broker."""

from __future__ import annotations

import asyncio
import os
import sys
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from importlib import import_module
from importlib.resources import files
from inspect import isawaitable
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse
from uuid import uuid4

import zmq.asyncio

from liteyukibot.broker import (
    MESSAGE_SEND_KIND,
    ActionOutcome,
    ActionRequest,
    ActionResourceDeclaration,
    BoundedIngressPublisher,
    BridgeAccess,
    BridgeClient,
    BridgeManifest,
    BrokerBridgeRunner,
    EventIngress,
    MessageSendPayload,
    RuntimeApiDeclaration,
    RuntimeApiInvoke,
    RuntimeApiOperation,
    RuntimeApiOutcome,
    parse_message_send_request,
    portable_conversation_schema,
    portable_message_schema,
    runtime_api_catalog,
)
from liteyukibot.config import AppSettings, LoggingSettings
from liteyukibot.events import ConversationRef, JsonValue, Message, Segment
from liteyukibot.logging import configure_logging, get_logger
from liteyukibot.lyip import LyipLane

from .listener import configure_publisher
from .translate import to_event_envelope

type IngressSink = Callable[[EventIngress], Awaitable[None]]

MESSAGE_CREATED_TOPIC = "message.created"
logger = get_logger(component="astrbot")


class AstrBotLogBridge:
    """Forward AstrBot's public LogBroker records into the process Yukilog sink."""

    def __init__(self, broker: Any, output: Any) -> None:
        self._broker = broker
        self._output = output
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
            output = self._output.bind(upstream="astrbot", upstream_category=category)
            getattr(output, level, output.info)("{}", message)


class AstrBotGateway:
    """Run AstrBot unchanged while adding a non-blocking broker observation hook."""

    def __init__(
        self,
        workspace: Path,
        bridge_id: str,
        output: Any,
        logging_settings: LoggingSettings | None = None,
    ) -> None:
        self.workspace = workspace
        self.bridge_id = bridge_id
        self._output = output
        self._logging_settings = logging_settings
        self._lifecycle: Any | None = None
        self._lifecycle_task: asyncio.Task[None] | None = None
        self._log_bridge: AstrBotLogBridge | None = None
        self._import_root: str | None = None
        self._ingress_sink: IngressSink | None = None
        self._ingress_publisher: BoundedIngressPublisher[Any] | None = None
        self._reply_events: OrderedDict[str, tuple[str, Any]] = OrderedDict()
        self._events_by_source_id: OrderedDict[str, Any] = OrderedDict()
        self._bot_platforms: dict[str, str] = {}

    async def start(self, ingress_sink: IngressSink, *, start_pipeline: bool = True) -> None:
        """Initialize AstrBot and start its configured native platform adapters."""

        self.workspace.mkdir(parents=True, exist_ok=True)
        os.environ["ASTRBOT_ROOT"] = str(self.workspace)
        os.environ["ASTRBOT_RELOAD"] = "0"
        self._install_import_root()
        self._install_star_plugin()
        configure_publisher(self._spawn_ingress)
        astrbot_core = import_module("astrbot.core")
        lifecycle_type = import_module("astrbot.core.core_lifecycle").AstrBotCoreLifecycle
        database_type = import_module("astrbot.core.db.sqlite").SQLiteDatabase
        broker = astrbot_core.LogBroker()
        lifecycle = lifecycle_type(broker, database_type(str(self.workspace / "astrbot.db")))
        log_bridge: AstrBotLogBridge | None = None
        try:
            await lifecycle.initialize()
            self._ingress_sink = ingress_sink
            self._ingress_publisher = BoundedIngressPublisher(
                self._publish_ingress,
                on_error=self._report_ingress_error,
                task_name=f"liteyuki-astrbot-ingress:{self.bridge_id}",
            )
            await self._ingress_publisher.start()
            if self._logging_settings is not None:
                configured = configure_logging(self._logging_settings)
                self._output = configured.bind(component="astrbot", bridge=self.bridge_id)
            log_bridge = AstrBotLogBridge(broker, self._output)
            log_bridge.start(astrbot_core.LogManager, astrbot_core.logger)
        except BaseException:
            configure_publisher(None)
            if self._ingress_publisher is not None:
                await self._ingress_publisher.close()
                self._ingress_publisher = None
            if log_bridge is not None:
                await log_bridge.close()
            self._remove_import_root()
            raise
        self._lifecycle = lifecycle
        self._log_bridge = log_bridge
        if start_pipeline:
            self._lifecycle_task = asyncio.create_task(lifecycle.start(), name="astrbot-lifecycle")

    async def serve_forever(self) -> None:
        if self._lifecycle_task is None:
            raise RuntimeError("AstrBot gateway is not started")
        await self._lifecycle_task

    async def close(self) -> None:
        lifecycle, self._lifecycle = self._lifecycle, None
        lifecycle_task, self._lifecycle_task = self._lifecycle_task, None
        log_bridge, self._log_bridge = self._log_bridge, None
        ingress_publisher, self._ingress_publisher = self._ingress_publisher, None
        try:
            if ingress_publisher is not None:
                await ingress_publisher.close()
            if lifecycle_task is not None and not lifecycle_task.done():
                lifecycle_task.cancel()
                await asyncio.gather(lifecycle_task, return_exceptions=True)
            if lifecycle is not None:
                await lifecycle.stop()
        finally:
            try:
                if log_bridge is not None:
                    await log_bridge.close()
            finally:
                try:
                    await _dispose_astrbot_global_database(self._output)
                finally:
                    self._reply_events.clear()
                    self._events_by_source_id.clear()
                    self._bot_platforms.clear()
                    configure_publisher(None)
                    self._remove_import_root()

    async def execute_message_send(self, request: ActionRequest) -> ActionOutcome:
        """Send the broker's sole portable action through the owning AstrBot platform."""

        try:
            payload = parse_message_send_request(request, owner_bridge_id=self.bridge_id)
            result = await self._send_message(payload)
        except (KeyError, ValueError) as error:
            return ActionOutcome(success=False, payload={"error": "message_send_failed", "message": str(error)})
        return ActionOutcome(success=True, payload=_json_result(result))

    async def execute_runtime_api(self, request: RuntimeApiInvoke) -> RuntimeApiOutcome:
        event = self._events_by_source_id.get(request.source_event_id)
        if event is None:
            return RuntimeApiOutcome(success=False, error_code="RUNTIME_EVENT_UNAVAILABLE")
        if request.api_id == "event.snapshot":
            if request.arguments:
                return RuntimeApiOutcome(success=False, error_code="RUNTIME_API_INVALID_ARGUMENTS")
            return RuntimeApiOutcome(
                success=True,
                result=self._event_snapshot(event, runtime_id=self.bridge_id),
            )
        if request.api_id == "event.send":
            if request.authorization.bot_id != str(event.get_self_id()):
                return RuntimeApiOutcome(success=False, error_code="RUNTIME_API_AUTHORIZATION_MISMATCH")
            try:
                if set(request.arguments) != {"message"}:
                    raise ValueError("event.send accepts only message")
                message = _runtime_message(request.arguments["message"])
            except (TypeError, ValueError):
                return RuntimeApiOutcome(success=False, error_code="RUNTIME_API_INVALID_ARGUMENTS")
            try:
                result = await event.send(_to_astr_chain(message))
            except Exception:
                return RuntimeApiOutcome(success=False, error_code="RUNTIME_API_SEND_FAILED")
            return RuntimeApiOutcome(success=True, result={"sent": True, "result": _json_result(result)})
        if request.api_id == "bot.snapshot":
            if request.arguments:
                return RuntimeApiOutcome(success=False, error_code="RUNTIME_API_INVALID_ARGUMENTS")
            try:
                return RuntimeApiOutcome(success=True, result=self._bot_snapshot(request.authorization.bot_id))
            except (KeyError, ValueError):
                return RuntimeApiOutcome(success=False, error_code="RUNTIME_BOT_UNAVAILABLE")
        if request.api_id == "bot.send":
            try:
                if set(request.arguments) != {"bot_id", "message", "conversation"}:
                    raise ValueError("bot.send requires bot_id, message, and conversation")
                bot_id = request.arguments["bot_id"]
                if bot_id != request.authorization.bot_id:
                    raise ValueError("bot.send bot ID does not match the active event")
                payload = MessageSendPayload(
                    bot_id=bot_id,
                    message=_runtime_message(request.arguments["message"]),
                    conversation=ConversationRef.model_validate(request.arguments["conversation"]),
                )
                result = await self._send_message(payload)
            except (KeyError, TypeError, ValueError):
                return RuntimeApiOutcome(success=False, error_code="RUNTIME_API_INVALID_ARGUMENTS")
            except Exception:
                return RuntimeApiOutcome(success=False, error_code="RUNTIME_API_SEND_FAILED")
            return RuntimeApiOutcome(success=True, result={"sent": True, "result": _json_result(result)})
        return RuntimeApiOutcome(success=False, error_code="RUNTIME_API_NOT_REGISTERED")

    def _spawn_ingress(self, event: Any) -> None:
        publisher = self._ingress_publisher
        if publisher is not None:
            publisher.submit(event)

    def _report_ingress_error(self, error: Exception) -> None:
        self._output.bind(runtime=self.bridge_id, component="ingress").warning(
            "AstrBot broker ingress delivery failed: {}",
            type(error).__name__,
        )

    async def _publish_ingress(self, event: Any) -> None:
        sink = self._ingress_sink
        if sink is None:
            return
        platform_id = str(event.get_platform_id()).strip()
        source_event_id = str(getattr(getattr(event, "message_obj", None), "message_id", "")).strip()
        if not platform_id or not source_event_id:
            self._output.warning("AstrBot event cannot be published without platform and message IDs")
            return
        reply_token = f"{platform_id}:{source_event_id}"
        envelope = to_event_envelope(event, reply_token=reply_token, runtime_id=self.bridge_id)
        self._reply_events[reply_token] = (envelope.bot_id, event)
        self._events_by_source_id[envelope.id] = event
        self._reply_events.move_to_end(reply_token)
        self._events_by_source_id.move_to_end(envelope.id)
        while len(self._reply_events) > 2_048:
            self._reply_events.popitem(last=False)
        while len(self._events_by_source_id) > 2_048:
            self._events_by_source_id.popitem(last=False)
        self._bot_platforms[envelope.bot_id] = platform_id
        await sink(
            EventIngress(
                source_event_id=envelope.id,
                topic=MESSAGE_CREATED_TOPIC,
                ordering_key=envelope.conversation.ordering_key,
                payload=envelope.model_dump(mode="json"),
            )
        )

    async def _send_message(self, payload: MessageSendPayload) -> Any:
        chain = _to_astr_chain(payload.message)
        if payload.reply_token is not None:
            target = self._reply_events.get(payload.reply_token)
            if target is None:
                raise ValueError("reply token is unknown or expired")
            bot_id, event = target
            if bot_id != payload.bot_id:
                raise ValueError("reply token belongs to a different bot")
            return await event.send(chain)
        if payload.conversation is None:
            raise ValueError("message.send requires conversation when reply_token is absent")
        platform_id = self._bot_platforms.get(payload.bot_id)
        if platform_id is None:
            raise ValueError("bot has no observed AstrBot platform session")
        platform = self._platform(platform_id)
        message_type = import_module("astrbot.core.platform.message_type").MessageType
        session_type = import_module("astrbot.core.platform.message_session").MessageSession
        native_type = (
            message_type.GROUP_MESSAGE
            if payload.conversation.type == "group"
            else message_type.FRIEND_MESSAGE
        )
        session = session_type(platform_name=platform_id, message_type=native_type, session_id=payload.conversation.id)
        return await platform.send_by_session(session, chain)

    def _platform(self, platform_id: str) -> Any:
        if self._lifecycle is None:
            raise RuntimeError("AstrBot gateway is not started")
        for platform in self._lifecycle.platform_manager.get_insts():
            if str(platform.meta().id) == platform_id:
                return platform
        raise ValueError("AstrBot platform is no longer available")

    @staticmethod
    def _event_snapshot(event: Any, *, runtime_id: str = "astrbot") -> dict[str, JsonValue]:
        envelope = to_event_envelope(
            event,
            reply_token=f"{event.get_platform_id()}:{getattr(getattr(event, 'message_obj', None), 'message_id', '')}",
            runtime_id=runtime_id,
        )
        message = envelope.message
        assert message is not None
        return {
            "platform_id": str(event.get_platform_id()),
            "platform_name": envelope.adapter,
            "bot_id": envelope.bot_id,
            "session_id": str(event.get_session_id()),
            "group_id": envelope.conversation.id if envelope.conversation.type == "group" else None,
            "sender_id": None if envelope.actor is None else envelope.actor.id,
            "message": message.plain_text,
            "message_type": str(event.get_message_type()),
            "conversation_id": envelope.conversation.id,
            "conversation_type": envelope.conversation.type,
            "actor_name": None if envelope.actor is None else envelope.actor.display_name,
            "actor_is_bot": False if envelope.actor is None else envelope.actor.is_bot,
            "message_segments": cast(
                JsonValue,
                [segment.model_dump(mode="json") for segment in message.segments],
            ),
        }

    def _bot_snapshot(self, bot_id: str) -> dict[str, JsonValue]:
        platform_id = self._bot_platforms.get(bot_id)
        if platform_id is None:
            raise ValueError("bot has no observed AstrBot platform session")
        platform = self._platform(platform_id)
        meta = platform.meta()
        return {
            "bot_id": bot_id,
            "platform_id": platform_id,
            "platform_name": str(getattr(meta, "name", platform_id)),
            "capabilities": cast(JsonValue, []),
        }

    def _install_import_root(self) -> None:
        value = str(self.workspace)
        sys.path.insert(0, value)
        self._import_root = value

    def _install_star_plugin(self) -> None:
        """Install the package-owned Star hook without touching user plugins."""

        plugin_root = self.workspace / "data" / "plugins" / "liteyuki_broker_ingress"
        plugin_root.mkdir(parents=True, exist_ok=True)
        source = files("liteyukibot_runtime_astrbot").joinpath("star_bootstrap.py").read_text(encoding="utf-8")
        (plugin_root / "main.py").write_text(source, encoding="utf-8")
        (plugin_root / "metadata.yaml").write_text(
            "name: liteyuki_broker_ingress\n"
            "description: Liteyuki broker ingress hook\n"
            "version: 1.0.0\n"
            "author: LiteyukiBot\n",
            encoding="utf-8",
        )

    def _remove_import_root(self) -> None:
        value, self._import_root = self._import_root, None
        if value is not None:
            with suppress(ValueError):
                sys.path.remove(value)


async def launch(settings: AppSettings, bridge_id: str, token: str) -> None:
    """Launch a configured AstrBot platform gateway in the bridge process."""

    bridge = settings.broker.bridges.get(bridge_id)
    if bridge is None:
        raise RuntimeError(f"broker bridge {bridge_id!r} is not configured")
    if bridge.kind != "astrbot":
        raise RuntimeError(f"broker bridge {bridge_id!r} is not an AstrBot bridge")
    manifest = BridgeManifest(
        bridge_id=bridge_id,
        access=BridgeAccess(bridge.access),
        subscriptions=bridge.subscriptions,
        action_resources=tuple(
            ActionResourceDeclaration(
                kind=item.kind,
                resource=item.resource,
                resource_prefix=item.resource_prefix,
            )
            for item in bridge.action_resources
        ),
        runtime_apis=_runtime_api_declarations(),
    )
    client = BridgeClient(
        context=zmq.asyncio.Context.instance(),
        endpoints=_broker_endpoints(settings.broker.endpoint),
        generation=settings.broker.generation,
        identity=f"astrbot:{bridge_id}:{uuid4()}".encode("ascii"),
        manifest=manifest,
        instance_token=token,
    )
    gateway = AstrBotGateway(
        _workspace_path(settings, bridge_id, bridge.options),
        bridge_id,
        logger,
        settings.logging,
    )
    runner = BrokerBridgeRunner(
        client,
        action_handlers={MESSAGE_SEND_KIND: gateway.execute_message_send},
        runtime_api_handlers={
            "event.snapshot": gateway.execute_runtime_api,
            "event.send": gateway.execute_runtime_api,
            "bot.snapshot": gateway.execute_runtime_api,
            "bot.send": gateway.execute_runtime_api,
        },
    )
    serving: asyncio.Task[None] | None = None
    try:
        await runner.start()
        await gateway.start(client.send_event_ingress)
        serving = asyncio.create_task(runner.serve_forever(), name="astrbot-broker-runner")
        await gateway.serve_forever()
    finally:
        if serving is not None:
            serving.cancel()
            await asyncio.gather(serving, return_exceptions=True)
        await gateway.close()
        await runner.stop()
        runner.close()


async def run_standalone() -> None:
    raise RuntimeError("AstrBot is a broker gateway; use 'liteyuki bridge run <bridge-id>'")


def _workspace_path(settings: AppSettings, bridge_id: str, options: Mapping[str, object]) -> Path:
    workspace = options.get("workspace")
    if workspace is None:
        return (settings.core.data_dir / "bridges" / bridge_id / "astrbot").resolve()
    if not isinstance(workspace, str) or not workspace.strip():
        raise ValueError("AstrBot bridge option 'workspace' must be a non-empty string")
    return Path(workspace).expanduser().resolve()


def _broker_endpoints(endpoint: str) -> dict[LyipLane, str]:
    parsed = urlparse(endpoint)
    if parsed.scheme != "tcp" or parsed.hostname is None or parsed.port is None:
        raise ValueError("broker endpoint must be a valid tcp URL")
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    return {
        LyipLane.CONTROL: f"tcp://{host}:{parsed.port}",
        LyipLane.BUSINESS: f"tcp://{host}:{parsed.port + 1}",
    }


def _to_astr_chain(message: Message) -> Any:
    components = import_module("astrbot.core.message.components")
    chain_type = import_module("astrbot.core.message.message_event_result").MessageChain
    rendered: list[Any] = []
    for segment in message.segments:
        data = segment.model_dump(mode="json")["data"]
        assert isinstance(data, dict)
        if segment.type == "text":
            rendered.append(components.Plain(data["text"]))
        elif segment.type == "mention":
            if data.get("scope") == "all":
                rendered.append(components.AtAll())
            elif isinstance(data.get("user_id"), str):
                rendered.append(components.At(qq=data["user_id"]))
            else:
                raise ValueError("AstrBot mentions require user_id or scope=all")
        elif segment.type == "reply":
            identifier = data.get("message_id")
            if not isinstance(identifier, str) or not identifier:
                raise ValueError("AstrBot reply segments require message_id")
            rendered.append(components.Reply(id=identifier))
        elif segment.type == "media":
            source = data.get("url") or data.get("file")
            if not isinstance(source, str) or not source:
                raise ValueError("AstrBot media segments require url or file")
            media_type = data.get("media_type")
            if media_type == "image":
                rendered.append(components.Image(file=source, url=source))
            elif media_type in {"audio", "voice"}:
                rendered.append(components.Record(file=source, url=source))
            elif media_type == "video":
                rendered.append(components.Video(file=source, url=source))
            elif media_type == "file":
                name = data.get("name")
                rendered.append(
                    components.File(
                        name=name if isinstance(name, str) and name else "attachment",
                        file=source,
                        url=source,
                    )
                )
            else:
                raise ValueError(f"AstrBot does not support media_type {media_type!r}")
        else:
            raise ValueError(f"AstrBot cannot represent portable segment {segment.type!r}")
    return chain_type(chain=rendered)


def _json_result(value: object) -> JsonValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_result(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return tuple(_json_result(item) for item in value)
    return type(value).__name__


def _optional_text(value: object) -> str | None:
    rendered = str(value or "").strip()
    return rendered or None


def _runtime_api_declarations() -> tuple[RuntimeApiDeclaration, ...]:
    return runtime_api_catalog(
        "astrbot",
        (
            RuntimeApiOperation(
                namespace="event",
                operation="snapshot",
                input_schema={"type": "object", "additionalProperties": False},
                output_schema=_event_snapshot_schema(),
            ),
            RuntimeApiOperation(
                namespace="event",
                operation="send",
                input_schema={
                    "type": "object",
                    "properties": {
                        "message": {
                            "oneOf": [
                                {"type": "string", "minLength": 1},
                                portable_message_schema(),
                            ]
                        }
                    },
                    "required": ["message"],
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "additionalProperties": True},
            ),
            RuntimeApiOperation(
                namespace="bot",
                operation="snapshot",
                input_schema={"type": "object", "additionalProperties": False},
                output_schema=_bot_snapshot_schema(),
            ),
            RuntimeApiOperation(
                namespace="bot",
                operation="send",
                input_schema={
                    "type": "object",
                    "properties": {
                        "bot_id": {"type": "string", "minLength": 1},
                        "message": portable_message_schema(),
                        "conversation": portable_conversation_schema(),
                    },
                    "required": ["bot_id", "message", "conversation"],
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "additionalProperties": True},
            ),
        ),
    )


def _bot_snapshot_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "bot_id": {"type": "string", "minLength": 1},
            "platform_id": {"type": "string", "minLength": 1},
            "platform_name": {"type": "string", "minLength": 1},
            "capabilities": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["bot_id", "platform_id", "platform_name", "capabilities"],
        "additionalProperties": False,
    }


def _event_snapshot_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "platform_id": {"type": "string", "minLength": 1},
            "platform_name": {"type": "string", "minLength": 1},
            "bot_id": {"type": "string", "minLength": 1},
            "session_id": {"type": "string", "minLength": 1},
            "group_id": {"type": ["string", "null"]},
            "sender_id": {"type": ["string", "null"]},
            "message": {"type": "string"},
            "message_type": {"type": "string", "minLength": 1},
            "conversation_id": {"type": "string", "minLength": 1},
            "conversation_type": {"type": "string", "minLength": 1},
            "actor_name": {"type": ["string", "null"]},
            "actor_is_bot": {"type": "boolean"},
            "message_segments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["text", "media", "mention", "reply", "adapter"]},
                        "data": {"type": "object", "additionalProperties": True},
                    },
                    "required": ["type", "data"],
                    "additionalProperties": False,
                },
            },
        },
        "required": [
            "platform_id",
            "platform_name",
            "bot_id",
            "session_id",
            "group_id",
            "sender_id",
            "message",
            "message_type",
            "conversation_id",
            "conversation_type",
            "actor_name",
            "actor_is_bot",
            "message_segments",
        ],
        "additionalProperties": False,
    }


def _runtime_message(value: object) -> Message:
    if isinstance(value, str):
        if not value.strip():
            raise ValueError("runtime message text must not be blank")
        return Message(segments=(Segment(type="text", data={"text": value}),))
    if not isinstance(value, Mapping):
        raise TypeError("runtime message must be text or a portable Message object")
    return Message.model_validate(value)


async def _dispose_astrbot_global_database(output: Any) -> None:
    try:
        database = import_module("astrbot.core").db_helper
        result = database.engine.dispose()
        if isawaitable(result):
            await result
    except Exception as error:
        output.warning("AstrBot global database cleanup failed: {}", error)


__all__ = ["AstrBotGateway", "MESSAGE_CREATED_TOPIC", "launch"]
