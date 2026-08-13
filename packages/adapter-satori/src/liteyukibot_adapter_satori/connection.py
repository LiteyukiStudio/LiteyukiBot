"""External Satori v1 gateway client and HTTP action adapter."""

from __future__ import annotations

import asyncio
import html
import json
import re
import ssl
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import uuid4
from xml.etree import ElementTree

from liteyukibot_runtime_adapter.contracts import AdapterConnection, AdapterContext, EventEmitter
from websockets.asyncio.client import connect

from liteyukibot.events import (
    ActionEnvelope,
    ActorRef,
    CallApi,
    ConversationRef,
    EditMessage,
    EventEnvelope,
    Message,
    Segment,
    SendMessage,
)
from liteyukibot.runtime.protocol import JsonValue, json_value

_EVENT = 0
_PING = 1
_PONG = 2
_IDENTIFY = 3
_READY = 4
_MAX_BODY_BYTES = 1024 * 1024
_HTTP_TIMEOUT_SECONDS = 15
_ELEMENT_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]*\\Z")


class SatoriError(ValueError):
    """The configured Satori gateway or action is invalid."""


class SatoriConnection(AdapterConnection):
    """Connect to one external Satori gateway and own its account actions."""

    def __init__(self, context: AdapterContext) -> None:
        self.context = context
        self._gateway_url = _required_websocket_url(context.config, "gateway_url")
        self._api_root = _required_http_url(context.config, "api_root")
        self._access_token = _optional_token(context.config, "access_token")
        self._emit: EventEmitter | None = None
        self._task: asyncio.Task[None] | None = None
        self._ready = asyncio.Event()
        self._closed = False
        self._sequence: int | None = None

    async def start(self, emit: EventEmitter) -> None:
        self._emit = emit
        self._task = asyncio.create_task(self._gateway_loop(), name="satori-gateway")
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=10)
        except TimeoutError as error:
            await self.close()
            raise SatoriError("Satori gateway did not send READY") from error

    async def execute(self, action: ActionEnvelope) -> JsonValue:
        if isinstance(action.action, SendMessage):
            conversation = action.action.conversation
            if conversation is None:
                raise SatoriError("Satori send_message requires a conversation")
            return await self._call_api(
                "message.create",
                {"channel_id": conversation.id, "content": _to_satori_content(action.action.message)},
            )
        if isinstance(action.action, EditMessage):
            conversation = action.action.conversation
            if conversation is None:
                raise SatoriError("Satori edit_message requires a conversation")
            return await self._call_api(
                "message.update",
                {
                    "channel_id": conversation.id,
                    "message_id": action.action.message_id,
                    "content": _to_satori_content(action.action.message),
                },
            )
        if isinstance(action.action, CallApi):
            return await self._call_api(action.action.api.replace("_", "."), action.action.params)
        raise SatoriError(f"unsupported Satori action {action.action.type!r}")

    async def close(self) -> None:
        self._closed = True
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._ready.clear()
        self._emit = None

    async def _gateway_loop(self) -> None:
        headers = {"Authorization": f"Bearer {self._access_token}"} if self._access_token else None
        while not self._closed:
            try:
                async with connect(
                    self._gateway_url, additional_headers=headers, max_size=_MAX_BODY_BYTES
                ) as websocket:
                    await websocket.send(
                        json.dumps({"op": _IDENTIFY, "body": {"token": self._access_token, "sn": self._sequence}})
                    )
                    async for raw in websocket:
                        if not isinstance(raw, str):
                            continue
                        payload = _json_object(raw, "Satori gateway frame")
                        opcode = payload.get("op")
                        if opcode == _READY:
                            self._ready.set()
                        elif opcode == _PING:
                            await websocket.send(json.dumps({"op": _PONG, "body": {}}))
                        elif opcode == _EVENT:
                            await self._handle_event(payload.get("body"))
            except asyncio.CancelledError:
                raise
            except Exception:
                self._ready.clear()
                if not self._closed:
                    await asyncio.sleep(1)

    async def _handle_event(self, body: object) -> None:
        if not isinstance(body, Mapping):
            raise SatoriError("Satori EVENT body must be an object")
        sequence = body.get("sn")
        if isinstance(sequence, int) and not isinstance(sequence, bool):
            self._sequence = sequence
        event = _normalize_event(self.context, body)
        if event is not None:
            if self._emit is None:
                raise RuntimeError("Satori connection has no event emitter")
            await self._emit(event)

    async def _call_api(self, api: str, params: Mapping[str, Any]) -> JsonValue:
        if not api or any(character.isspace() for character in api):
            raise SatoriError("Satori API name must be a non-empty token")
        response = await _post_json(self._api_root, api, params, self._access_token)
        return json_value(response)


def _normalize_event(context: AdapterContext, value: Mapping[str, Any]) -> EventEnvelope | None:
    if value.get("type") not in {"message-created", "message"}:
        return None
    if str(value.get("self_id", "")) != context.bot_id:
        raise SatoriError("Satori event self ID does not match configured bot_id")
    channel = value.get("channel")
    message = value.get("message")
    if not isinstance(channel, Mapping) or not isinstance(message, Mapping):
        raise SatoriError("Satori message events require channel and message")
    channel_id = channel.get("id")
    if not isinstance(channel_id, str) or not channel_id:
        raise SatoriError("Satori message event channel requires id")
    channel_type = channel.get("type")
    conversation_type: Literal["private", "channel"] = "private" if channel_type == 1 else "channel"
    guild = value.get("guild")
    parent_id = channel.get("parent_id") or channel.get("guild_id")
    if not isinstance(parent_id, str) and isinstance(guild, Mapping):
        parent_id = guild.get("id")
    user = value.get("user")
    actor = None
    if isinstance(user, Mapping) and isinstance(user.get("id"), str):
        actor = ActorRef(id=user["id"], display_name=user.get("name") if isinstance(user.get("name"), str) else None)
    content = message.get("content", "")
    if not isinstance(content, str):
        raise SatoriError("Satori message content must be a string")
    timestamp = value.get("timestamp")
    values: dict[str, Any] = {
        "runtime_id": context.runtime_id,
        "adapter": "satori",
        "bot_id": context.bot_id,
        "type": "message.private" if conversation_type == "private" else "message.channel",
        "conversation": ConversationRef(
            id=channel_id,
            type=conversation_type,
            parent_id=parent_id if isinstance(parent_id, str) else None,
        ),
        "actor": actor,
        "message": _from_satori_content(content),
        "reply_token": str(uuid4()),
        "raw": json_value(value),
    }
    if isinstance(timestamp, (int, float)) and not isinstance(timestamp, bool):
        values["timestamp"] = datetime.fromtimestamp(timestamp / 1000, UTC)
    return EventEnvelope.model_validate(values)


def _from_satori_content(content: str) -> Message:
    try:
        root = ElementTree.fromstring(f"<root>{content}</root>")
    except ElementTree.ParseError:
        return Message(segments=(Segment(type="text", data={"text": content}),))
    segments: list[Segment] = []
    if root.text:
        segments.append(Segment(type="text", data={"text": root.text}))
    for element in root:
        tag = element.tag
        attributes = {key: value for key, value in element.attrib.items()}
        if tag == "at":
            if "id" in attributes:
                segments.append(Segment(type="mention", data={"user_id": attributes["id"]}))
            elif "role" in attributes:
                segments.append(Segment(type="mention", data={"role_id": attributes["role"]}))
            elif attributes.get("type") in {"all", "here"}:
                segments.append(Segment(type="mention", data={"scope": attributes["type"]}))
        elif tag == "quote" and "id" in attributes:
            segments.append(Segment(type="reply", data={"message_id": attributes["id"]}))
        elif tag in {"img", "audio", "video", "file"}:
            source = attributes.get("src") or attributes.get("url")
            data: dict[str, JsonValue] = {"media_type": {"img": "image"}.get(tag, tag)}
            if source:
                data["url"] = source
            segments.append(Segment.model_validate({"type": "media", "data": data}))
        else:
            segments.append(Segment(type="adapter", data={"adapter": "satori", "type": tag, "data": attributes}))
        if element.tail:
            segments.append(Segment(type="text", data={"text": element.tail}))
    return Message(segments=tuple(segments))


def _to_satori_content(message: Message) -> str:
    rendered: list[str] = []
    for segment in message.segments:
        data = segment.model_dump(mode="json")["data"]
        assert isinstance(data, dict)
        if segment.type == "text":
            rendered.append(html.escape(str(data["text"])))
        elif segment.type == "mention":
            if "user_id" in data:
                rendered.append(f'<at id="{html.escape(str(data["user_id"]), quote=True)}"/>')
            elif "role_id" in data:
                rendered.append(f'<at role="{html.escape(str(data["role_id"]), quote=True)}"/>')
            elif data.get("scope") in {"all", "here"}:
                rendered.append(f'<at type="{data["scope"]}"/>')
            else:
                raise SatoriError("Satori mentions require user_id, role_id, or scope")
        elif segment.type == "reply":
            identifier = data.get("message_id")
            if not isinstance(identifier, str) or not identifier:
                raise SatoriError("Satori reply segments require message_id")
            rendered.append(f'<quote id="{html.escape(identifier, quote=True)}"/>')
        elif segment.type == "media":
            media_type = data.get("media_type")
            tag = {
                "image": "img",
                "audio": "audio",
                "voice": "audio",
                "video": "video",
                "file": "file",
            }.get(str(media_type))
            source = data.get("url") or data.get("file")
            if tag is None or not isinstance(source, str) or not source:
                raise SatoriError("Satori media requires supported media_type and url or file")
            rendered.append(f'<{tag} src="{html.escape(source, quote=True)}"/>')
        elif segment.type == "adapter":
            if data.get("adapter") != "satori" or not isinstance(data.get("type"), str):
                raise SatoriError("adapter segments must target satori")
            if _ELEMENT_NAME.fullmatch(data["type"]) is None:
                raise SatoriError("Satori adapter segment type must be a valid element name")
            native_data = data.get("data", {})
            if not isinstance(native_data, Mapping):
                raise SatoriError("Satori adapter segment data must be an object")
            attrs = "".join(f' {key}="{html.escape(str(value), quote=True)}"' for key, value in native_data.items())
            rendered.append(f"<{data['type']}{attrs}/>")
        else:
            raise SatoriError(f"unsupported Satori segment {segment.type!r}")
    return "".join(rendered)


async def _post_json(api_root: str, api: str, params: Mapping[str, Any], token: str | None) -> dict[str, Any]:
    url = urlsplit(f"{api_root}/{api}")
    if url.scheme not in {"http", "https"} or not url.hostname:
        raise SatoriError("Satori api_root must be an absolute HTTP(S) URL")
    payload = json.dumps(json_value(params), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > _MAX_BODY_BYTES:
        raise SatoriError("Satori API request body is too large")
    ssl_context = ssl.create_default_context() if url.scheme == "https" else None
    try:
        async with asyncio.timeout(_HTTP_TIMEOUT_SECONDS):
            reader, writer = await asyncio.open_connection(
                url.hostname,
                url.port or (443 if url.scheme == "https" else 80),
                ssl=ssl_context,
                server_hostname=url.hostname if ssl_context else None,
            )
            try:
                headers = [
                    f"POST {url.path or '/'} HTTP/1.1",
                    f"Host: {url.netloc}",
                    "Content-Type: application/json",
                    f"Content-Length: {len(payload)}",
                    "Connection: close",
                ]
                if token:
                    headers.append(f"Authorization: Bearer {token}")
                writer.write("\r\n".join(headers).encode("ascii") + b"\r\n\r\n" + payload)
                await writer.drain()
                status_line = await reader.readline()
                if len(status_line) > 8192:
                    raise SatoriError("Satori API response status line is too large")
                status_fields = status_line.decode("ascii").rstrip("\r\n").split(" ", maxsplit=2)
                if len(status_fields) < 2:
                    raise SatoriError("Satori API response has an invalid status line")
                status = int(status_fields[1])
                headers_map: dict[str, str] = {}
                header_bytes = 0
                while line := await reader.readline():
                    header_bytes += len(line)
                    if header_bytes > 16384:
                        raise SatoriError("Satori API response headers are too large")
                    if line == b"\r\n":
                        break
                    key, value = line.decode("ascii").rstrip("\r\n").split(":", 1)
                    headers_map[key.lower()] = value.strip()
                length = headers_map.get("content-length")
                if length is None or not length.isdecimal() or int(length) > _MAX_BODY_BYTES:
                    raise SatoriError("Satori API response has an invalid content length")
                body = await reader.readexactly(int(length))
                if not 200 <= status < 300:
                    raise SatoriError(f"Satori API {api!r} returned HTTP {status}")
                return _json_object(body.decode("utf-8"), "Satori API response")
            finally:
                writer.close()
                await writer.wait_closed()
    except TimeoutError as error:
        raise SatoriError(f"Satori API {api!r} timed out") from error


def _json_object(value: str, subject: str) -> dict[str, Any]:
    parsed = json.loads(value)
    normalized = json_value(parsed)
    if not isinstance(normalized, dict):
        raise SatoriError(f"{subject} must be an object")
    return normalized


def _required_websocket_url(config: Mapping[str, JsonValue], key: str) -> str:
    value = config.get(key)
    if (
        not isinstance(value, str)
        or not value.startswith(("ws://", "wss://"))
        or any(character.isspace() for character in value)
    ):
        raise SatoriError(f"adapter config {key!r} must be a WebSocket URL")
    return value


def _required_http_url(config: Mapping[str, JsonValue], key: str) -> str:
    value = config.get(key)
    if (
        not isinstance(value, str)
        or not value.startswith(("http://", "https://"))
        or any(character.isspace() for character in value)
    ):
        raise SatoriError(f"adapter config {key!r} must be an HTTP URL")
    return value.rstrip("/")


def _optional_token(config: Mapping[str, JsonValue], key: str) -> str | None:
    value = config.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value or value != value.strip():
        raise SatoriError(f"adapter config {key!r} must be a non-empty token when set")
    return value


async def create_satori(context: AdapterContext) -> AdapterConnection:
    return SatoriConnection(context)


__all__ = ["SatoriConnection", "SatoriError", "create_satori"]
