"""Versioned, framed JSON protocol used by local child runtimes."""

from __future__ import annotations

import asyncio
import json
import struct
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from ..exceptions import RuntimeProtocolError
from ..json_value import JsonValue as JsonValue
from ..json_value import json_mapping as json_mapping
from ..json_value import json_value as json_value

type ProtocolVersion = Literal[1, 2, 3, 4, 5]

PROTOCOL_VERSION: ProtocolVersion = 5
SUPPORTED_PROTOCOL_VERSIONS: tuple[ProtocolVersion, ...] = (1, 2, 3, 4, 5)
MAX_FRAME_SIZE = 8 * 1024 * 1024


class WireModel(BaseModel):
    """Represent the validated wire model contract."""
    model_config = ConfigDict(extra="forbid", frozen=True)


class Hello(WireModel):
    """Represent the validated hello contract."""
    type: Literal["hello"] = "hello"
    protocol: ProtocolVersion = PROTOCOL_VERSION
    runtime_id: str
    kind: str
    token: str


class Welcome(WireModel):
    """Represent the validated welcome contract."""
    type: Literal["welcome"] = "welcome"
    protocol: ProtocolVersion = PROTOCOL_VERSION
    heartbeat_interval: float = 10.0


class ConfigMessage(WireModel):
    """Represent the validated config message contract."""
    type: Literal["config"] = "config"
    options: dict[str, JsonValue] = Field(default_factory=dict)


class Ready(WireModel):
    """Represent the validated ready contract."""
    type: Literal["ready"] = "ready"
    capabilities: tuple[str, ...] = ()


class Heartbeat(WireModel):
    """Represent the validated heartbeat contract."""
    type: Literal["heartbeat"] = "heartbeat"
    monotonic: float


class Shutdown(WireModel):
    """Represent the validated shutdown contract."""
    type: Literal["shutdown"] = "shutdown"
    reason: str = "requested"


class EventTrace(WireModel):
    """Immutable kernel-owned context carried across an event delivery."""

    trace_id: str = Field(min_length=1)
    source_runtime_id: str = Field(min_length=1)
    source_event_id: str = Field(min_length=1)


class EventMessage(WireModel):
    """Represent the validated event message contract."""
    type: Literal["event"] = "event"
    correlation_id: str
    payload: dict[str, JsonValue]
    trace: EventTrace | None = None


class EventAccepted(WireModel):
    """Represent the validated event accepted contract."""
    type: Literal["event_accepted"] = "event_accepted"
    correlation_id: str
    status: Literal["accepted", "overloaded", "invalid"]
    detail: str | None = None


class EventCompleted(WireModel):
    """Terminal v4 outcome for an already accepted core-to-child Event."""

    type: Literal["event_completed"] = "event_completed"
    correlation_id: str = Field(min_length=1)
    status: Literal["completed", "failed"]
    detail: str | None = None


class ActionRequest(WireModel):
    """Represent the validated action request contract."""
    type: Literal["action"] = "action"
    correlation_id: str
    payload: dict[str, JsonValue]
    delivery_correlation_id: str | None = None


class ActionResponse(WireModel):
    """Represent the validated action response contract."""
    type: Literal["action_result"] = "action_result"
    correlation_id: str
    ok: bool
    data: JsonValue = None
    error: str | None = None


class ManagementRequest(WireModel):
    """A child request to execute one existing kernel management command."""

    type: Literal["management"] = "management"
    correlation_id: str = Field(min_length=1)
    command: str = Field(min_length=1)


class ManagementResponse(WireModel):
    """Represent the validated management response contract."""
    type: Literal["management_result"] = "management_result"
    correlation_id: str = Field(min_length=1)
    ok: bool
    text: str = ""
    data: JsonValue = None
    error: str | None = None


class ErrorMessage(WireModel):
    """Represent the validated error message contract."""
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
    | EventCompleted
    | ActionRequest
    | ActionResponse
    | ManagementRequest
    | ManagementResponse
    | ErrorMessage,
    Field(discriminator="type"),
]
WIRE_ADAPTER: TypeAdapter[WireMessage] = TypeAdapter(WireMessage)


async def read_message(
    reader: asyncio.StreamReader, *, max_size: int = MAX_FRAME_SIZE
) -> WireMessage:
    """Read message.

    Args:
        reader: The reader value used by the operation.
        max_size: The max size value used by the operation.

    Returns:
        The requested `WireMessage` value.
    """
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
    """Write message.

    Args:
        writer: The writer value used by the operation.
        message: Message content associated with the operation.

    Returns:
        None.
    """
    payload = message.model_dump_json(exclude_none=True).encode("utf-8")
    if not payload or len(payload) > MAX_FRAME_SIZE:
        raise RuntimeProtocolError(f"runtime message is too large: {len(payload)}")
    writer.write(struct.pack(">I", len(payload)))
    writer.write(payload)
    await writer.drain()
