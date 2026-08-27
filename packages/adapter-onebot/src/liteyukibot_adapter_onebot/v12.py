"""OneBot v12 HTTP and WebSocket adapter."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from liteyukibot_broker import MessageSendPayload
from liteyukibot_runtime_adapter.contracts import AdapterConnection, AdapterContext, EventEmitter

from liteyukibot.events import (
    ActorRef,
    ConversationRef,
    EventEnvelope,
    Message,
    Segment,
)
from liteyukibot.json_value import JsonValue, json_value

from .v11 import (
    _API_NAME,
    _config_api_root,
    _config_optional_host,
    _config_optional_port,
    _config_optional_string,
    _config_optional_url,
    _config_path,
    _config_transport,
    _is_json_content_type,
    _is_loopback_host,
    _json_object,
    _post_json,
    _read_http_request,
    _write_response,
)
from .websocket import OneBotWebSocketError, OneBotWebSocketTransport

_MAX_REPLY_ROUTES = 2048
_HTTP_TIMEOUT_SECONDS = 15


class OneBotV12Error(ValueError):
    """The requested operation cannot be represented by OneBot v12."""


class OneBotV12Connection(AdapterConnection):
    """Own one OneBot v12 callback/transport connection and API endpoint."""

    def __init__(self, context: AdapterContext) -> None:
        """Initialize the one bot v12 connection.

        Args:
            context: Runtime or authorization context for the operation.

        Returns:
            None.
        """
        self.context = context
        self._event_host = _config_optional_host(context.config, "event_host") or "127.0.0.1"
        self._event_port = _config_optional_port(context.config, "event_port") or 5702
        self._event_path = _config_path(context.config, "event_path", "/onebot/v12/http")
        self._api_root = _config_api_root(context.config)
        self._access_token = _config_optional_string(context.config, "access_token")
        self._transport_mode = _config_transport(context.config)
        if not _is_loopback_host(self._event_host) and not self._access_token:
            raise OneBotV12Error("non-loopback OneBot HTTP listeners require access_token")
        self._server: asyncio.Server | None = None
        self._websocket: OneBotWebSocketTransport | None = None
        self._emit: EventEmitter | None = None
        self._reply_routes: OrderedDict[str, ConversationRef] = OrderedDict()
        self._failure_event = asyncio.Event()
        self._failure: BaseException | None = None

    async def start(self, emit: EventEmitter) -> None:
        """Start the one bot v12 connection.

        Args:
            emit: The emit value used by the operation.

        Returns:
            None.
        """
        if self._server is not None or self._websocket is not None:
            raise RuntimeError("OneBot v12 connection is already started")
        self._failure_event.clear()
        self._failure = None
        self._emit = emit
        if self._transport_mode == "http_post":
            self._server = await asyncio.start_server(self._handle_http, self._event_host, self._event_port)
            return
        websocket = OneBotWebSocketTransport(
            mode=self._transport_mode,
            url=_config_optional_url(self.context.config, "ws_url"),
            host=_config_optional_host(self.context.config, "ws_host"),
            port=_config_optional_port(self.context.config, "ws_port"),
            path=_config_path(self.context.config, "ws_path", "/onebot/v12/ws"),
            access_token=self._access_token,
            handle_event=self._handle_payload,
            on_failure=self._transport_failed,
        )
        await websocket.start()
        self._websocket = websocket

    async def send_message(self, payload: MessageSendPayload) -> JsonValue:
        """Send message.

        Args:
            payload: JSON-safe payload carried by the operation.

        Returns:
            The `JsonValue` result produced by the operation.
        """
        return await self._send_message(payload)

    async def close(self) -> None:
        """Close the one bot v12 connection and release its owned resources.

        Returns:
            None.
        """
        websocket, self._websocket = self._websocket, None
        if websocket is not None:
            await websocket.close()
        server, self._server = self._server, None
        if server is not None:
            server.close()
            await server.wait_closed()
        self._emit = None
        self._reply_routes.clear()

    async def wait_failure(self) -> None:
        """Wait for failure.

        Returns:
            None.
        """
        await self._failure_event.wait()
        if self._failure is not None:
            raise self._failure
        raise RuntimeError("OneBot v12 connection failed without a diagnostic")

    async def _transport_failed(self, error: BaseException) -> None:
        """Implement the transport failed operation for the one bot v12 connection.

        Args:
            error: The error value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `OneBotV12Connection._transport_failed`. It delegates to
            `is_set` while keeping intermediate state local to the owning operation.
        """
        if not self._failure_event.is_set():
            self._failure = error
            self._failure_event.set()

    async def _handle_http(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Handle http.

        Args:
            reader: The reader value used by the operation.
            writer: The writer value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `OneBotV12Connection._handle_http`. It delegates to
            `timeout`, `_read_http_request`, `_write_response`, `_is_json_content_type` while keeping
            intermediate state local to the owning operation.
        """
        try:
            async with asyncio.timeout(_HTTP_TIMEOUT_SECONDS):
                method, path, headers, body = await _read_http_request(reader)
                if method != "POST" or path != self._event_path:
                    await _write_response(writer, 404, b"")
                    return
                if not _is_json_content_type(headers.get("content-type")):
                    await _write_response(writer, 415, b"")
                    return
                payload = _json_object(body, "OneBot v12 event body")
                if self._access_token is not None and headers.get("authorization") != f"Bearer {self._access_token}":
                    await _write_response(writer, 401, b"")
                    return
                await self._handle_payload(payload)
                await _write_response(writer, 204, b"")
        except (TimeoutError, ValueError, UnicodeDecodeError, asyncio.IncompleteReadError):
            await _write_response(writer, 400, b"")
        finally:
            writer.close()
            await writer.wait_closed()

    async def _handle_payload(self, payload: Mapping[str, Any]) -> None:
        """Handle payload.

        Args:
            payload: JSON-safe payload carried by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `OneBotV12Connection._handle_payload`. It delegates to `get`,
            `_normalize_event`, `move_to_end`, `popitem` while keeping intermediate state local to the
            owning operation.
        """
        if str(payload.get("self_id", "")) != self.context.bot_id:
            raise OneBotV12Error("OneBot v12 event self ID does not match configured bot_id")
        event = _normalize_event(self.context, payload)
        if event is None:
            return
        if event.reply_token is not None:
            self._reply_routes[event.reply_token] = event.conversation
            self._reply_routes.move_to_end(event.reply_token)
            while len(self._reply_routes) > _MAX_REPLY_ROUTES:
                self._reply_routes.popitem(last=False)
        if self._emit is None:
            raise RuntimeError("OneBot v12 connection has no event emitter")
        await self._emit(event)

    async def _send_message(self, payload: MessageSendPayload) -> JsonValue:
        """Send message.

        Args:
            payload: JSON-safe payload carried by the operation.

        Returns:
            The `JsonValue` result produced by the operation.

        Notes:
            Internal implementation detail for `OneBotV12Connection._send_message`. It delegates to
            `_to_onebot_message`, `_call_api` while keeping intermediate state local to the owning
            operation.
        """
        conversation = payload.conversation
        if conversation is None:
            if payload.reply_token is None or payload.reply_token not in self._reply_routes:
                raise OneBotV12Error("message.send requires a conversation or known reply_token")
            conversation = self._reply_routes[payload.reply_token]
        params: dict[str, Any] = {"detail_type": conversation.type, "message": _to_onebot_message(payload.message)}
        if conversation.type == "private":
            params["user_id"] = conversation.id
        elif conversation.type == "group":
            params["group_id"] = conversation.id
        elif conversation.type == "channel":
            params["channel_id"] = conversation.id
            if conversation.parent_id:
                params["guild_id"] = conversation.parent_id
        else:
            raise OneBotV12Error(f"OneBot v12 does not support {conversation.type!r} conversations")
        return await self._call_api("send_message", params)

    async def _call_api(self, api: str, params: Mapping[str, Any]) -> JsonValue:
        """Implement the call api operation for the one bot v12 connection.

        Args:
            api: The api value used by the operation.
            params: The params value used by the operation.

        Returns:
            The `JsonValue` result produced by the operation.

        Notes:
            Internal implementation detail for `OneBotV12Connection._call_api`. It delegates to `fullmatch`,
            `_post_json`, `execute`, `get` while keeping intermediate state local to the owning operation.
        """
        if not _API_NAME.fullmatch(api):
            raise OneBotV12Error("OneBot API names must contain only ASCII letters, digits, and underscores")
        if self._websocket is None:
            response = await _post_json(self._api_root, api, params, self._access_token)
        else:
            try:
                response = await self._websocket.execute(api, params)
            except OneBotWebSocketError as error:
                raise OneBotV12Error(str(error)) from error
        if response.get("status") != "ok" or response.get("retcode") != 0:
            raise OneBotV12Error(f"OneBot API {api!r} failed: {response.get('message') or response.get('retcode')!r}")
        return json_value(response.get("data"))


def _normalize_event(context: AdapterContext, payload: Mapping[str, Any]) -> EventEnvelope | None:
    """Normalize event.

    Args:
        context: Runtime or authorization context for the operation.
        payload: JSON-safe payload carried by the operation.

    Returns:
        The `EventEnvelope | None` result produced by the operation.

    Notes:
        Internal implementation detail for `_normalize_event`. It delegates to `get`, `json_value`,
        `append`, `model_validate` while keeping intermediate state local to the owning operation.
    """
    if payload.get("type") != "message":
        return None
    detail_type = payload.get("detail_type")
    if detail_type not in {"private", "group", "channel"}:
        return None
    conversation_id = payload.get(f"{detail_type}_id")
    if conversation_id is None:
        raise OneBotV12Error(f"OneBot v12 {detail_type} messages require {detail_type}_id")
    message = payload.get("message")
    if not isinstance(message, list):
        raise OneBotV12Error("OneBot v12 message events require a segment array")
    segments: list[Segment] = []
    for value in message:
        if not isinstance(value, Mapping) or not isinstance(value.get("type"), str):
            raise OneBotV12Error("OneBot v12 message segments must be objects")
        native_type = value["type"]
        data = value.get("data", {})
        if not isinstance(data, Mapping):
            raise OneBotV12Error("OneBot v12 segment data must be an object")
        normalized = json_value(data)
        if not isinstance(normalized, dict):
            raise OneBotV12Error("OneBot v12 segment data must serialize to an object")
        if native_type == "text" and isinstance(normalized.get("text"), str):
            segments.append(Segment.model_validate({"type": "text", "data": {"text": normalized["text"]}}))
        elif native_type in {"mention", "mention_all"}:
            mention = dict(normalized)
            if native_type == "mention_all":
                mention["scope"] = "all"
            elif "user_id" in mention:
                mention["user_id"] = str(mention["user_id"])
            segments.append(Segment.model_validate({"type": "mention", "data": mention}))
        elif native_type == "reply" and "message_id" in normalized:
            segments.append(
                Segment.model_validate(
                    {"type": "reply", "data": {**normalized, "message_id": str(normalized["message_id"])}},
                )
            )
        elif native_type in {"image", "audio", "voice", "video", "file"}:
            segments.append(
                Segment.model_validate({"type": "media", "data": {**normalized, "media_type": native_type}})
            )
        else:
            segments.append(
                Segment.model_validate(
                    {"type": "adapter", "data": {"adapter": "onebot-v12", "type": native_type, "data": normalized}},
                )
            )
    actor_id = str(payload.get("user_id", ""))
    values: dict[str, Any] = {
        "runtime_id": context.bridge_id,
        "adapter": "onebot-v12",
        "bot_id": context.bot_id,
        "type": f"message.{detail_type}",
        "conversation": ConversationRef(
            id=str(conversation_id),
            type=detail_type,
            parent_id=str(payload["guild_id"]) if detail_type == "channel" and payload.get("guild_id") else None,
        ),
        "actor": ActorRef(id=actor_id) if actor_id else None,
        "message": Message(segments=tuple(segments)),
        "reply_token": str(uuid4()),
        "raw": json_value(payload),
    }
    timestamp = payload.get("time")
    if isinstance(timestamp, (int, float)) and not isinstance(timestamp, bool):
        values["timestamp"] = datetime.fromtimestamp(timestamp, UTC)
    return EventEnvelope.model_validate(values)


async def create_v12(context: AdapterContext) -> AdapterConnection:
    """Create v12.

    Args:
        context: Runtime or authorization context for the operation.

    Returns:
        The `AdapterConnection` result produced by the operation.
    """
    return OneBotV12Connection(context)


def _to_onebot_message(message: Message) -> list[dict[str, JsonValue]]:
    """Implement the to onebot message operation for the component.

    Args:
        message: Message content associated with the operation.

    Returns:
        The `list[dict[str, JsonValue]]` result produced by the operation.

    Notes:
        Internal implementation detail for `_to_onebot_message`. It delegates to `_to_onebot_segment`
        while keeping intermediate state local to the owning operation.
    """
    return [_to_onebot_segment(segment) for segment in message.segments]


def _to_onebot_segment(segment: Segment) -> dict[str, JsonValue]:
    """Implement the to onebot segment operation for the component.

    Args:
        segment: The segment value used by the operation.

    Returns:
        The `dict[str, JsonValue]` result produced by the operation.

    Notes:
        Internal implementation detail for `_to_onebot_segment`. It delegates to `model_dump`, `get`,
        `pop`, `json_value` while keeping intermediate state local to the owning operation.
    """
    data = segment.model_dump(mode="json")["data"]
    assert isinstance(data, dict)
    if segment.type == "text":
        return {"type": "text", "data": {"text": data["text"]}}
    if segment.type == "mention":
        if data.get("scope") == "all":
            return {"type": "mention_all", "data": {}}
        if isinstance(data.get("user_id"), str):
            return {"type": "mention", "data": {"user_id": data["user_id"]}}
        raise OneBotV12Error("OneBot v12 mentions require user_id or scope=all")
    if segment.type == "reply":
        message_id = data.get("message_id")
        if not isinstance(message_id, str) or not message_id:
            raise OneBotV12Error("OneBot v12 reply segments require message_id")
        return {"type": "reply", "data": {"message_id": message_id}}
    if segment.type == "media":
        media_type = data.get("media_type")
        if media_type not in {"image", "audio", "voice", "video", "file"}:
            raise OneBotV12Error(f"OneBot v12 does not support media_type {media_type!r}")
        output = dict(data)
        output.pop("media_type", None)
        return {"type": str(media_type), "data": json_value(output)}
    if segment.type == "adapter":
        target = data.get("adapter")
        native_type = data.get("type")
        native_data = data.get("data")
        if target not in (None, "onebot-v12") or not isinstance(native_type, str) or not native_type:
            raise OneBotV12Error("adapter segments must target onebot-v12 and declare a type")
        if not isinstance(native_data, Mapping):
            raise OneBotV12Error("adapter segments require object data")
        return {"type": native_type, "data": json_value(native_data)}
    raise OneBotV12Error(f"unsupported portable segment type {segment.type!r}")


__all__ = ["OneBotV12Connection", "OneBotV12Error", "create_v12"]
