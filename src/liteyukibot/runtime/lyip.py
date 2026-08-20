"""LYIP v1 encoding for the existing typed runtime message catalog."""

from __future__ import annotations

import json
from collections.abc import Mapping

from ..lyip import LyipError, LyipFrame, LyipLane
from .protocol import WIRE_ADAPTER, WireMessage

LYIP_RUNTIME_ABI = 1

_TYPE_IDS: Mapping[str, int] = {
    "hello": 1,
    "welcome": 2,
    "config": 3,
    "ready": 4,
    "heartbeat": 5,
    "shutdown": 6,
    "event": 10,
    "event_accepted": 11,
    "event_completed": 12,
    "action": 20,
    "action_result": 21,
    "management": 50,
    "management_result": 51,
    "error": 255,
}
_TYPE_NAMES = {value: key for key, value in _TYPE_IDS.items()}
_CONTROL_TYPES = frozenset(
    {
        "hello",
        "welcome",
        "config",
        "ready",
        "heartbeat",
        "shutdown",
        "management",
        "management_result",
        "error",
    }
)


def encode_runtime_message(
    message: WireMessage,
    *,
    generation: int,
    stream_id: str,
    sequence: int,
    lease_id: str,
) -> LyipFrame:
    type_id = _TYPE_IDS[message.type]
    lane = LyipLane.CONTROL if message.type in _CONTROL_TYPES else LyipLane.BUSINESS
    return LyipFrame(
        1,
        generation,
        lane,
        type_id,
        stream_id,
        sequence,
        lease_id,
        message.model_dump_json(exclude_none=True).encode("utf-8"),
    )


def decode_runtime_message(frame: LyipFrame) -> WireMessage:
    expected_type = _TYPE_NAMES.get(frame.type_id)
    if expected_type is None:
        raise LyipError(f"unsupported LYIP runtime type ID: {frame.type_id}")
    try:
        value = json.loads(frame.payload)
        message = WIRE_ADAPTER.validate_python(value)
    except (json.JSONDecodeError, ValueError) as error:
        raise LyipError("LYIP runtime payload is invalid") from error
    if message.type != expected_type:
        raise LyipError("LYIP runtime type ID does not match payload type")
    expected_lane = LyipLane.CONTROL if message.type in _CONTROL_TYPES else LyipLane.BUSINESS
    if frame.lane is not expected_lane:
        raise LyipError("LYIP runtime payload arrived on the wrong lane")
    return message


__all__ = ["LYIP_RUNTIME_ABI", "decode_runtime_message", "encode_runtime_message"]
