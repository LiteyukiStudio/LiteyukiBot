from __future__ import annotations

from uuid import uuid4

import pytest
from liteyukibot_ipc_native import native_available

if not native_available:
    pytest.skip("shared SPSC ring requires a supported native platform", allow_module_level=True)

from liteyukibot_ipc_native import SharedSpscRing


def _name() -> str:
    return f"lyip-python-test-{uuid4().hex}"


def test_native_availability_requires_shared_memory_probe() -> None:
    assert native_available


def test_named_ring_attaches_and_preserves_order() -> None:
    owner = SharedSpscRing(_name(), capacity=3, slot_size=8)
    peer = SharedSpscRing.open(owner.name)

    assert peer.capacity == 3
    assert peer.slot_size == 8
    assert owner.try_push(b"first")
    assert owner.try_push(b"second")
    assert peer.try_pop() == b"first"
    assert peer.try_pop() == b"second"
    assert peer.try_pop() is None


def test_full_ring_rejects_and_physical_slots_wrap() -> None:
    ring = SharedSpscRing(_name(), capacity=2, slot_size=4)

    assert ring.try_push(b"a")
    assert ring.try_push(b"b")
    assert not ring.try_push(b"c")
    assert ring.try_pop() == b"a"
    assert ring.try_push(b"c")
    assert ring.try_pop() == b"b"
    assert ring.try_pop() == b"c"


def test_payload_larger_than_fixed_slot_is_rejected() -> None:
    ring = SharedSpscRing(_name(), capacity=1, slot_size=2)

    with pytest.raises(ValueError, match="exceeds fixed slot size"):
        ring.try_push(b"abc")


def test_independent_control_ring_is_not_consumed_by_business_backpressure() -> None:
    business = SharedSpscRing(_name(), capacity=1, slot_size=4)
    control = SharedSpscRing(_name(), capacity=1, slot_size=4)

    assert business.try_push(b"data")
    assert not business.try_push(b"more")
    assert control.try_push(b"ack")
    assert control.try_pop() == b"ack"
