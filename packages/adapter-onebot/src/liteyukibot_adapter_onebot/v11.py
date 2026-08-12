"""OneBot v11 HTTP Post and HTTP API adapter without a framework dependency."""

from __future__ import annotations

import asyncio
import hmac
import ipaddress
import json
import re
import ssl
from collections import OrderedDict
from collections.abc import Mapping, MutableMapping, Sequence
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import uuid4

from liteyukibot_runtime_adapter.contracts import AdapterConnection, AdapterContext, EventEmitter

from liteyukibot.events import (
    ActionEnvelope,
    ActorRef,
    CallApi,
    ConversationRef,
    EventEnvelope,
    Message,
    Segment,
    SendMessage,
)
from liteyukibot.runtime.protocol import JsonValue, json_value

_MAX_HEADER_BYTES = 16 * 1024
_MAX_BODY_BYTES = 1024 * 1024
_MAX_REPLY_ROUTES = 2048
_MAX_CONCURRENT_REQUESTS = 100
_HTTP_TIMEOUT_SECONDS = 15
_API_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")
_MEDIA_TYPES = frozenset({"image", "record", "video"})


class OneBotV11Error(ValueError):
    """The requested operation cannot be represented by OneBot v11."""


class OneBotV11Connection(AdapterConnection):
    """Own one OneBot v11 HTTP callback listener and API endpoint."""

    def __init__(self, context: AdapterContext) -> None:
        self.context = context
        self._event_host = _config_string(context.config, "event_host", "127.0.0.1")
        self._event_port = _config_port(context.config, "event_port", 5700)
        self._event_path = _config_path(context.config, "event_path", "/onebot/v11/http")
        self._api_root = _config_api_root(context.config)
        self._access_token = _config_optional_string(context.config, "access_token")
        if not _is_loopback_host(self._event_host) and not self._access_token:
            raise OneBotV11Error("non-loopback OneBot HTTP listeners require access_token")
        self._server: asyncio.Server | None = None
        self._emit: EventEmitter | None = None
        self._reply_routes: OrderedDict[str, ConversationRef] = OrderedDict()
        self._request_slots = asyncio.BoundedSemaphore(_MAX_CONCURRENT_REQUESTS)

    async def start(self, emit: EventEmitter) -> None:
        if self._server is not None:
            raise RuntimeError("OneBot v11 connection is already started")
        self._emit = emit
        self._server = await asyncio.start_server(self._handle_request, self._event_host, self._event_port)

    async def execute(self, action: ActionEnvelope) -> JsonValue:
        if isinstance(action.action, SendMessage):
            return await self._send_message(action.action)
        if isinstance(action.action, CallApi):
            return await self._call_api(action.action.api, action.action.params)
        raise OneBotV11Error(f"unsupported OneBot v11 action {action.action.type!r}")

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._emit = None
        self._reply_routes.clear()

    async def _handle_request(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            if self._request_slots.locked():
                await _write_response(writer, 503, b"")
                return
            try:
                async with self._request_slots, asyncio.timeout(_HTTP_TIMEOUT_SECONDS):
                    method, path, headers, body = await _read_http_request(reader)
                    if method != "POST" or path != self._event_path:
                        await _write_response(writer, 404, b"")
                        return
                    if not _is_json_content_type(headers.get("content-type")):
                        await _write_response(writer, 415, b"")
                        return
                    if not _authorized(headers, self._access_token):
                        await _write_response(writer, 401, b"")
                        return
                    payload = _json_object(body, "OneBot event body")
                    _validate_self_id(payload, headers, self.context.bot_id)
                    event = _normalize_event(self.context, payload)
                    if event is not None:
                        self._remember_reply_route(event)
                        if self._emit is None:
                            raise RuntimeError("OneBot v11 connection has no event emitter")
                        await self._emit(event)
            except OneBotV11Error:
                await _write_response(writer, 400, b"")
            except (asyncio.IncompleteReadError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
                await _write_response(writer, 400, b"")
            except Exception:
                await _write_response(writer, 503, b"")
            else:
                await _write_response(writer, 204, b"")
        finally:
            writer.close()
            await writer.wait_closed()

    def _remember_reply_route(self, event: EventEnvelope) -> None:
        if event.reply_token is None:
            return
        self._reply_routes[event.reply_token] = event.conversation
        self._reply_routes.move_to_end(event.reply_token)
        while len(self._reply_routes) > _MAX_REPLY_ROUTES:
            self._reply_routes.popitem(last=False)

    async def _send_message(self, action: SendMessage) -> JsonValue:
        conversation = action.conversation
        if conversation is None:
            if action.reply_token is None:
                raise OneBotV11Error("send_message requires a conversation or known reply_token")
            try:
                conversation = self._reply_routes[action.reply_token]
            except KeyError as error:
                raise OneBotV11Error("reply_token is unknown or expired") from error
        message = _to_onebot_message(action.message)
        target = _positive_integer_id(conversation.id)
        if conversation.type == "private":
            return await self._call_api("send_private_msg", {"user_id": target, "message": message})
        if conversation.type == "group":
            return await self._call_api("send_group_msg", {"group_id": target, "message": message})
        raise OneBotV11Error(f"OneBot v11 does not support {conversation.type!r} conversations")

    async def _call_api(self, api: str, params: Mapping[str, Any]) -> JsonValue:
        if not _API_NAME.fullmatch(api):
            raise OneBotV11Error("OneBot API names must contain only ASCII letters, digits, and underscores")
        response = await _post_json(self._api_root, api, params, self._access_token)
        if response.get("status") != "ok" or response.get("retcode") != 0:
            raise OneBotV11Error(f"OneBot API {api!r} failed: {response.get('wording') or response.get('retcode')!r}")
        return json_value(response.get("data"))


async def create_v11(context: AdapterContext) -> AdapterConnection:
    """Create a OneBot v11 adapter instance selected by the host."""

    return OneBotV11Connection(context)


async def _read_http_request(reader: asyncio.StreamReader) -> tuple[str, str, dict[str, str], bytes]:
    request_line = await _read_limited_line(reader)
    method, target, version = request_line.decode("ascii").rstrip("\r\n").split(" ", maxsplit=2)
    if version != "HTTP/1.1" or not method.isalpha() or not target.startswith("/"):
        raise OneBotV11Error("invalid HTTP request line")
    headers: dict[str, str] = {}
    header_bytes = len(request_line)
    while True:
        line = await _read_limited_line(reader)
        header_bytes += len(line)
        if header_bytes > _MAX_HEADER_BYTES:
            raise OneBotV11Error("HTTP headers are too large")
        if line == b"\r\n":
            break
        name, separator, value = line.decode("ascii").rstrip("\r\n").partition(":")
        normalized = name.lower()
        if not separator or not normalized or normalized in headers:
            raise OneBotV11Error("invalid or duplicate HTTP header")
        headers[normalized] = value.strip()
    if headers.get("transfer-encoding"):
        raise OneBotV11Error("chunked OneBot HTTP events are unsupported")
    length = headers.get("content-length")
    if length is None or not length.isdecimal() or (parsed := int(length)) > _MAX_BODY_BYTES:
        raise OneBotV11Error("invalid OneBot HTTP content length")
    parsed_target = urlsplit(target)
    if parsed_target.query or parsed_target.fragment:
        raise OneBotV11Error("OneBot HTTP callback URLs must not contain a query or fragment")
    return method, parsed_target.path, headers, await reader.readexactly(parsed)


async def _read_limited_line(reader: asyncio.StreamReader) -> bytes:
    line = await reader.readline()
    if not line or not line.endswith(b"\r\n") or len(line) > _MAX_HEADER_BYTES:
        raise OneBotV11Error("invalid HTTP line")
    return line


async def _write_response(writer: asyncio.StreamWriter, status: int, body: bytes) -> None:
    reason = {
        204: "No Content",
        400: "Bad Request",
        401: "Unauthorized",
        404: "Not Found",
        415: "Unsupported Media Type",
        503: "Service Unavailable",
    }[status]
    writer.write(
        f"HTTP/1.1 {status} {reason}\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode("ascii") + body
    )
    await writer.drain()


def _normalize_event(context: AdapterContext, payload: Mapping[str, Any]) -> EventEnvelope | None:
    if payload.get("post_type") != "message":
        return None
    message_type = _required_string(payload, "message_type")
    if message_type not in {"private", "group"}:
        raise OneBotV11Error(f"unsupported OneBot v11 message_type {message_type!r}")
    user_id = _required_identifier(payload, "user_id")
    conversation_type: Literal["private", "group"] = "private" if message_type == "private" else "group"
    conversation_id = _required_identifier(payload, "group_id" if conversation_type == "group" else "user_id")
    sub_type = _optional_string(payload, "sub_type") or "normal"
    sender = payload.get("sender")
    display_name = None
    if isinstance(sender, Mapping):
        display_name = _optional_string(sender, "card") or _optional_string(sender, "nickname")
    timestamp = payload.get("time")
    values: dict[str, Any] = {
        "runtime_id": context.runtime_id,
        "adapter": "onebot-v11",
        "bot_id": context.bot_id,
        "type": f"message.{conversation_type}.{sub_type}",
        "conversation": ConversationRef(id=conversation_id, type=conversation_type),
        "actor": ActorRef(id=user_id, display_name=display_name, is_bot=user_id == context.bot_id),
        "message": _to_portable_message(payload.get("message")),
        "reply_token": str(uuid4()),
        "raw": json_value(payload),
    }
    if isinstance(timestamp, (int, float)) and not isinstance(timestamp, bool):
        values["timestamp"] = datetime.fromtimestamp(timestamp, UTC)
    return EventEnvelope.model_validate(values)


def _to_portable_message(value: Any) -> Message:
    if isinstance(value, str):
        return Message(segments=(Segment(type="text", data={"text": value}),))
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise OneBotV11Error("OneBot v11 message must be a string or segment array")
    segments: list[Segment] = []
    for raw_segment in value:
        if not isinstance(raw_segment, Mapping):
            raise OneBotV11Error("OneBot v11 message segments must be objects")
        native_type = _required_string(raw_segment, "type")
        data = raw_segment.get("data", {})
        if not isinstance(data, Mapping):
            raise OneBotV11Error("OneBot v11 segment data must be an object")
        normalized = json_value(data)
        if not isinstance(normalized, dict):
            raise OneBotV11Error("OneBot v11 segment data must serialize to an object")
        segments.append(_to_portable_segment(native_type, normalized))
    return Message(segments=tuple(segments))


def _to_portable_segment(native_type: str, data: dict[str, Any]) -> Segment:
    if native_type == "text":
        text = data.get("text")
        if not isinstance(text, str):
            raise OneBotV11Error("OneBot v11 text segments require data.text")
        return Segment(type="text", data={"text": text})
    if native_type == "at":
        target = data.pop("qq", None)
        if target == "all":
            data["scope"] = "all"
        elif target is not None:
            data["user_id"] = str(target)
        else:
            raise OneBotV11Error("OneBot v11 at segments require data.qq")
        return Segment(type="mention", data=data)
    if native_type == "reply":
        identifier = data.pop("id", None)
        if identifier is None:
            raise OneBotV11Error("OneBot v11 reply segments require data.id")
        data["message_id"] = str(identifier)
        return Segment(type="reply", data=data)
    if native_type in _MEDIA_TYPES:
        source = data.get("url") or data.get("file")
        if isinstance(source, str) and source:
            data["url"] = source
        data["media_type"] = {"record": "voice"}.get(native_type, native_type)
        if native_type != data["media_type"]:
            data["adapter_type"] = native_type
        return Segment(type="media", data=data)
    return Segment(type="adapter", data={"adapter": "onebot-v11", "type": native_type, "data": data})


def _to_onebot_message(message: Message) -> list[dict[str, Any]]:
    return [_to_onebot_segment(segment) for segment in message.segments]


def _to_onebot_segment(segment: Segment) -> dict[str, Any]:
    data = dict(segment.model_dump(mode="json")["data"])
    if segment.type == "text":
        return {"type": "text", "data": {"text": data["text"]}}
    if segment.type == "mention":
        scope = data.pop("scope", None)
        if scope == "all":
            data["qq"] = "all"
        elif isinstance(data.get("user_id"), str) and data["user_id"]:
            data["qq"] = data.pop("user_id")
        else:
            raise OneBotV11Error("OneBot v11 mentions require user_id or scope=all")
        if scope == "here" or "role_id" in data:
            raise OneBotV11Error("OneBot v11 does not support this mention target")
        return {"type": "at", "data": json_value(data)}
    if segment.type == "reply":
        identifier = data.pop("message_id", None)
        if not isinstance(identifier, str) or not identifier:
            raise OneBotV11Error("reply segments require a non-empty message_id")
        data["id"] = identifier
        return {"type": "reply", "data": json_value(data)}
    if segment.type == "media":
        media_type = data.pop("media_type", None)
        adapter_type = data.pop("adapter_type", None)
        native_type = adapter_type if adapter_type in _MEDIA_TYPES else {"voice": "record"}.get(media_type, media_type)
        if native_type not in _MEDIA_TYPES:
            raise OneBotV11Error(f"OneBot v11 does not support media_type {media_type!r}")
        if not isinstance(data.get("file"), str) or not data["file"]:
            url = data.pop("url", None)
            if not isinstance(url, str) or not url:
                raise OneBotV11Error("OneBot v11 media requires data.file or data.url")
            data["file"] = url
        return {"type": native_type, "data": json_value(data)}
    if segment.type == "adapter":
        target = data.get("adapter")
        native_type = data.get("type")
        native_data = data.get("data")
        if target not in (None, "onebot-v11") or not isinstance(native_type, str) or not native_type:
            raise OneBotV11Error("adapter segments must target onebot-v11 and declare a type")
        if not isinstance(native_data, Mapping):
            raise OneBotV11Error("adapter segments require object data")
        return {"type": native_type, "data": json_value(native_data)}
    raise OneBotV11Error(f"unsupported portable segment type {segment.type!r}")


async def _post_json(
    api_root: str, api: str, params: Mapping[str, Any], access_token: str | None
) -> dict[str, Any]:
    url = urlsplit(f"{api_root}/{api}")
    if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
        raise OneBotV11Error("OneBot api_root must be an absolute HTTP(S) URL without credentials")
    port = url.port or (443 if url.scheme == "https" else 80)
    path = url.path or "/"
    payload = json.dumps(json_value(params), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ssl_context = ssl.create_default_context() if url.scheme == "https" else None
    try:
        async with asyncio.timeout(_HTTP_TIMEOUT_SECONDS):
            reader, writer = await asyncio.open_connection(
                url.hostname,
                port,
                ssl=ssl_context,
                server_hostname=url.hostname if ssl_context else None,
            )
            try:
                headers = [
                    f"POST {path} HTTP/1.1",
                    f"Host: {url.netloc}",
                    "Content-Type: application/json",
                    f"Content-Length: {len(payload)}",
                    "Connection: close",
                ]
                if access_token:
                    headers.append(f"Authorization: Bearer {access_token}")
                writer.write("\r\n".join(headers).encode("ascii") + b"\r\n\r\n" + payload)
                await writer.drain()
                status_line = await _read_limited_line(reader)
                _, status_text, _ = status_line.decode("ascii").rstrip("\r\n").split(" ", maxsplit=2)
                status = int(status_text)
                response_headers = await _read_response_headers(reader)
                length = response_headers.get("content-length")
                if length is None or not length.isdecimal() or int(length) > _MAX_BODY_BYTES:
                    raise OneBotV11Error("OneBot API response has an invalid content length")
                response_body = await reader.readexactly(int(length))
                if not 200 <= status < 300:
                    raise OneBotV11Error(f"OneBot API {api!r} returned HTTP {status}")
                return _json_object(response_body, "OneBot API response")
            finally:
                writer.close()
                await writer.wait_closed()
    except TimeoutError as error:
        raise OneBotV11Error(f"OneBot API {api!r} timed out") from error


async def _read_response_headers(reader: asyncio.StreamReader) -> dict[str, str]:
    headers: dict[str, str] = {}
    header_bytes = 0
    while True:
        line = await _read_limited_line(reader)
        header_bytes += len(line)
        if header_bytes > _MAX_HEADER_BYTES:
            raise OneBotV11Error("HTTP response headers are too large")
        if line == b"\r\n":
            return headers
        name, separator, value = line.decode("ascii").rstrip("\r\n").partition(":")
        normalized = name.lower()
        if not separator or not normalized or normalized in headers:
            raise OneBotV11Error("invalid or duplicate HTTP response header")
        headers[normalized] = value.strip()


def _json_object(raw: bytes, subject: str) -> dict[str, Any]:
    value = json.loads(raw)
    if not isinstance(value, MutableMapping):
        raise OneBotV11Error(f"{subject} must be a JSON object")
    normalized = json_value(value)
    if not isinstance(normalized, dict):
        raise OneBotV11Error(f"{subject} must serialize to a JSON object")
    return normalized


def _authorized(headers: Mapping[str, str], token: str | None) -> bool:
    if token is None:
        return True
    value = headers.get("authorization")
    if value is None or not value.startswith("Bearer "):
        return False
    return hmac.compare_digest(value[7:], token)


def _is_json_content_type(value: str | None) -> bool:
    return value is not None and value.split(";", maxsplit=1)[0].strip().lower() == "application/json"


def _validate_self_id(payload: Mapping[str, Any], headers: Mapping[str, str], bot_id: str) -> None:
    values = [str(value) for value in (payload.get("self_id"), headers.get("x-self-id")) if value is not None]
    if not values or any(value != bot_id for value in values):
        raise OneBotV11Error("OneBot event self ID does not match the configured bot_id")


def _required_identifier(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, bool) or value is None:
        raise OneBotV11Error(f"OneBot event requires {key}")
    identifier = str(value)
    if not identifier:
        raise OneBotV11Error(f"OneBot event requires {key}")
    return identifier


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise OneBotV11Error(f"OneBot event requires string {key}")
    return value


def _optional_string(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value else None


def _positive_integer_id(value: str) -> int:
    if not value.isdecimal() or (parsed := int(value)) <= 0:
        raise OneBotV11Error("OneBot v11 conversation IDs must be positive integers")
    return parsed


def _config_string(config: Mapping[str, JsonValue], key: str, default: str) -> str:
    value = config.get(key, default)
    if not isinstance(value, str) or not value or value != value.strip():
        raise OneBotV11Error(f"adapter config {key!r} must be a non-empty trimmed string")
    return value


def _config_optional_string(config: Mapping[str, JsonValue], key: str) -> str | None:
    value = config.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value or value != value.strip():
        raise OneBotV11Error(f"adapter config {key!r} must be a non-empty trimmed string when set")
    if not value.isascii() or any(ord(character) < 33 or ord(character) > 126 for character in value):
        raise OneBotV11Error(f"adapter config {key!r} must contain only printable ASCII characters")
    return value


def _config_port(config: Mapping[str, JsonValue], key: str, default: int) -> int:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise OneBotV11Error(f"adapter config {key!r} must be an integer from 1 to 65535")
    return value


def _config_path(config: Mapping[str, JsonValue], key: str, default: str) -> str:
    value = _config_string(config, key, default)
    if not value.startswith("/") or "?" in value or "#" in value:
        raise OneBotV11Error(f"adapter config {key!r} must be an absolute path without query or fragment")
    return value


def _config_api_root(config: Mapping[str, JsonValue]) -> str:
    value = _config_string(config, "api_root", "http://127.0.0.1:5701")
    if not value.isascii() or any(character.isspace() for character in value):
        raise OneBotV11Error("adapter config 'api_root' must contain only non-whitespace ASCII characters")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise OneBotV11Error(
            "adapter config 'api_root' must be an absolute HTTP(S) URL without credentials, query, or fragment"
        )
    try:
        _ = parsed.port
    except ValueError as error:
        raise OneBotV11Error("adapter config 'api_root' contains an invalid port") from error
    return value.rstrip("/")


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


__all__ = ["OneBotV11Connection", "OneBotV11Error", "create_v11"]
