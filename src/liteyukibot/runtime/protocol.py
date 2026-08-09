"""Versioned, framed JSON protocol used by local child runtimes."""

from __future__ import annotations

import asyncio
import json
import struct
from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from ..exceptions import RuntimeProtocolError

type ProtocolVersion = Literal[1, 2, 3]
type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]

PROTOCOL_VERSION: ProtocolVersion = 3
SUPPORTED_PROTOCOL_VERSIONS: tuple[ProtocolVersion, ...] = (1, 2, 3)
MAX_FRAME_SIZE = 8 * 1024 * 1024


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Hello(WireModel):
    type: Literal["hello"] = "hello"
    protocol: ProtocolVersion = PROTOCOL_VERSION
    runtime_id: str
    kind: str
    token: str


class Welcome(WireModel):
    type: Literal["welcome"] = "welcome"
    protocol: ProtocolVersion = PROTOCOL_VERSION
    heartbeat_interval: float = 10.0


class ConfigMessage(WireModel):
    type: Literal["config"] = "config"
    options: dict[str, JsonValue] = Field(default_factory=dict)


class Ready(WireModel):
    type: Literal["ready"] = "ready"
    capabilities: tuple[str, ...] = ()


class Heartbeat(WireModel):
    type: Literal["heartbeat"] = "heartbeat"
    monotonic: float


class Shutdown(WireModel):
    type: Literal["shutdown"] = "shutdown"
    reason: str = "requested"


class EventMessage(WireModel):
    type: Literal["event"] = "event"
    correlation_id: str
    payload: dict[str, JsonValue]


class EventAccepted(WireModel):
    type: Literal["event_accepted"] = "event_accepted"
    correlation_id: str
    status: Literal["accepted", "overloaded", "invalid"]
    detail: str | None = None


class ActionRequest(WireModel):
    type: Literal["action"] = "action"
    correlation_id: str
    payload: dict[str, JsonValue]


class ActionResponse(WireModel):
    type: Literal["action_result"] = "action_result"
    correlation_id: str
    ok: bool
    data: JsonValue = None
    error: str | None = None


class ErrorMessage(WireModel):
    type: Literal["error"] = "error"
    code: str
    message: str
    correlation_id: str | None = None


type WireMessage = Annotated[
    Hello
    | Welcome
    | ConfigMessage
    | Ready
    | Heartbeat
    | Shutdown
    | EventMessage
    | EventAccepted
    | ActionRequest
    | ActionResponse
    | ErrorMessage,
    Field(discriminator="type"),
]
WIRE_ADAPTER: TypeAdapter[WireMessage] = TypeAdapter(WireMessage)


async def read_message(
    reader: asyncio.StreamReader, *, max_size: int = MAX_FRAME_SIZE
) -> WireMessage:
    try:
        header = await reader.readexactly(4)
    except asyncio.IncompleteReadError as exc:
        raise EOFError("runtime connection closed") from exc
    size = struct.unpack(">I", header)[0]
    if size == 0 or size > max_size:
        raise RuntimeProtocolError(f"invalid runtime frame size: {size}")
    try:
        payload = await reader.readexactly(size)
        value = json.loads(payload)
        return WIRE_ADAPTER.validate_python(value)
    except asyncio.IncompleteReadError as exc:
        raise EOFError("runtime connection closed during frame") from exc
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeProtocolError("invalid runtime JSON message") from exc


async def write_message(writer: asyncio.StreamWriter, message: WireMessage) -> None:
    payload = message.model_dump_json(exclude_none=True).encode("utf-8")
    if not payload or len(payload) > MAX_FRAME_SIZE:
        raise RuntimeProtocolError(f"runtime message is too large: {len(payload)}")
    writer.write(struct.pack(">I", len(payload)))
    writer.write(payload)
    await writer.drain()


def json_mapping(value: Mapping[str, Any]) -> dict[str, JsonValue]:
    """Validate an arbitrary mapping as JSON-safe data."""

    encoded = json.dumps(
        _mutable_json(value),
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise TypeError("expected a JSON object")
    return decoded


def _mutable_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _mutable_json(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_mutable_json(item) for item in value]
    return value
