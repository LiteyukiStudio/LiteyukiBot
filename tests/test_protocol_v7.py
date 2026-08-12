from __future__ import annotations

import asyncio
import json
import struct
from typing import Any, cast

import pytest

from liteyukibot.exceptions import RuntimeProtocolError
from liteyukibot.runtime.protocol import (
    MAX_FRAME_SIZE,
    ActionRequest,
    EventCompleted,
    EventMessage,
    EventTrace,
    Hello,
    Ready,
    json_mapping,
    read_message,
    write_message,
)


class MemoryWriter:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    def write(self, value: bytes) -> None:
        self.chunks.append(value)

    async def drain(self) -> None:
        return None


def _reader(payload: bytes) -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    reader.feed_data(payload)
    reader.feed_eof()
    return reader


@pytest.mark.asyncio
async def test_protocol_round_trip_preserves_message_shape() -> None:
    message = EventMessage(
        correlation_id="delivery-1",
        payload={"nested": {"enabled": True}},
        trace=EventTrace(
            trace_id="trace-1",
            source_runtime_id="nonebot",
            source_event_id="event-1",
        ),
        agent_tool_catalog={
            "tools": [
                {
                    "id": "docs.search",
                    "description": "Search the docs.",
                    "input_schema": {"type": "object"},
                }
            ]
        },
    )
    writer = MemoryWriter()

    await write_message(cast(asyncio.StreamWriter, writer), message)

    frame = b"".join(writer.chunks)
    assert struct.unpack(">I", frame[:4])[0] == len(frame) - 4
    assert await read_message(_reader(frame)) == message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        struct.pack(">I", 0),
        struct.pack(">I", MAX_FRAME_SIZE + 1),
        struct.pack(">I", 3) + b"{}?",
        struct.pack(">I", len(json.dumps({"type": "ready", "unexpected": True}).encode()))
        + json.dumps({"type": "ready", "unexpected": True}).encode(),
    ],
)
async def test_protocol_rejects_invalid_frames(payload: bytes) -> None:
    with pytest.raises(RuntimeProtocolError):
        await read_message(_reader(payload))


@pytest.mark.asyncio
async def test_protocol_rejects_truncated_frame() -> None:
    with pytest.raises(EOFError, match="during frame"):
        await read_message(_reader(struct.pack(">I", 10) + b"{}"))


def test_json_mapping_rejects_non_json_values() -> None:
    with pytest.raises((TypeError, ValueError)):
        json_mapping({"invalid": object()})


def test_json_mapping_returns_mutable_json_object() -> None:
    value: dict[str, Any] = {"items": (1, 2), "nested": {"ok": True}}

    result = json_mapping(value)

    assert result == {"items": [1, 2], "nested": {"ok": True}}


@pytest.mark.asyncio
async def test_protocol_accepts_discriminated_ready_message() -> None:
    payload = json.dumps(Ready(capabilities=("events",)).model_dump(mode="json")).encode()
    frame = struct.pack(">I", len(payload)) + payload

    assert await read_message(_reader(frame)) == Ready(capabilities=("events",))


@pytest.mark.parametrize("protocol", [1, 2, 3, 4, 5])
@pytest.mark.asyncio
async def test_protocol_accepts_negotiated_hello_versions(protocol: int) -> None:
    payload = json.dumps(
        {
            "type": "hello",
            "protocol": protocol,
            "runtime_id": "fixture",
            "kind": "custom",
            "token": "secret",
        }
    ).encode()
    frame = struct.pack(">I", len(payload)) + payload

    message = await read_message(_reader(frame))
    assert isinstance(message, Hello)
    assert message.protocol == protocol


@pytest.mark.asyncio
async def test_protocol_rejects_unsupported_hello_version() -> None:
    payload = json.dumps(
        {
            "type": "hello",
            "protocol": 6,
            "runtime_id": "fixture",
            "kind": "custom",
            "token": "secret",
        }
    ).encode()
    frame = struct.pack(">I", len(payload)) + payload

    with pytest.raises(RuntimeProtocolError):
        await read_message(_reader(frame))


@pytest.mark.asyncio
async def test_protocol_accepts_v4_event_completion() -> None:
    message = EventCompleted(correlation_id="delivery-1", status="completed")
    writer = MemoryWriter()

    await write_message(cast(asyncio.StreamWriter, writer), message)

    assert await read_message(_reader(b"".join(writer.chunks))) == message


@pytest.mark.asyncio
async def test_protocol_preserves_v4_action_delivery_provenance() -> None:
    message = ActionRequest(
        correlation_id="action-1",
        delivery_correlation_id="delivery-1",
        payload={"type": "send_message"},
    )
    writer = MemoryWriter()

    await write_message(cast(asyncio.StreamWriter, writer), message)

    assert await read_message(_reader(b"".join(writer.chunks))) == message
