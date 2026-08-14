from __future__ import annotations

import pytest

from liteyukibot.lyip import LyipError, LyipLane
from liteyukibot.runtime.lyip import LYIP_RUNTIME_ABI, decode_runtime_message, encode_runtime_message
from liteyukibot.runtime.protocol import EventMessage, Ready


def test_runtime_lyip_round_trip_assigns_business_and_control_lanes() -> None:
    event = encode_runtime_message(
        EventMessage(correlation_id="event", payload={}), generation=1, stream_id="event", sequence=0, lease_id="lease"
    )
    ready = encode_runtime_message(Ready(), generation=1, stream_id="control", sequence=0, lease_id="lease")

    assert LYIP_RUNTIME_ABI == 1
    assert event.lane is LyipLane.BUSINESS
    assert ready.lane is LyipLane.CONTROL
    assert decode_runtime_message(event).type == "event"
    assert decode_runtime_message(ready).type == "ready"


def test_runtime_lyip_rejects_type_lane_mismatch() -> None:
    frame = encode_runtime_message(Ready(), generation=1, stream_id="control", sequence=0, lease_id="lease")
    frame = frame.__class__(
        frame.protocol,
        frame.generation,
        LyipLane.BUSINESS,
        frame.type_id,
        frame.stream_id,
        frame.sequence,
        frame.lease_id,
        frame.payload,
    )

    with pytest.raises(LyipError, match="wrong lane"):
        decode_runtime_message(frame)
