from __future__ import annotations

import pytest
import zmq.asyncio

from liteyukibot.config import LyipLinkSettings, LyipSettings
from liteyukibot.lyip import (
    InMemoryLyipLink,
    LyipBackend,
    LyipError,
    LyipFrame,
    LyipLane,
    LyipOfferResult,
    ZmqLyipDealer,
    ZmqLyipRouter,
    select_lyip_backend,
)


def _frame(
    stream_id: str,
    sequence: int,
    *,
    lane: LyipLane = LyipLane.BUSINESS,
    generation: int = 1,
) -> LyipFrame:
    return LyipFrame(1, generation, lane, 7, stream_id, sequence, f"lease-{stream_id}-{sequence}", b"payload")


def test_business_pressure_cannot_consume_control_capacity() -> None:
    link = InMemoryLyipLink(generation=1, business_capacity=1, control_capacity=1)

    assert link.offer(_frame("one", 0)) is LyipOfferResult.ACCEPTED
    assert link.offer(_frame("two", 0)) is LyipOfferResult.FULL
    assert link.offer(_frame("control", 0, lane=LyipLane.CONTROL)) is LyipOfferResult.ACCEPTED
    assert link.pressure(LyipLane.BUSINESS) == (1, 1)
    assert link.pressure(LyipLane.CONTROL) == (1, 1)


def test_link_preserves_each_stream_sequence_and_allows_independent_streams() -> None:
    link = InMemoryLyipLink(generation=1, business_capacity=4, control_capacity=1)

    assert link.offer(_frame("one", 0)) is LyipOfferResult.ACCEPTED
    assert link.offer(_frame("two", 0)) is LyipOfferResult.ACCEPTED
    assert link.offer(_frame("one", 1)) is LyipOfferResult.ACCEPTED

    assert [link.receive(LyipLane.BUSINESS).stream_id for _ in range(3)] == ["one", "two", "one"]  # type: ignore[union-attr]


def test_link_rejects_generation_and_sequence_mismatches_without_advancing_state() -> None:
    link = InMemoryLyipLink(generation=1, business_capacity=2, control_capacity=1)

    with pytest.raises(LyipError, match="generation"):
        link.offer(_frame("one", 0, generation=2))
    with pytest.raises(LyipError, match="expected 0"):
        link.offer(_frame("one", 1))
    assert link.offer(_frame("one", 0)) is LyipOfferResult.ACCEPTED


def test_backend_selection_falls_back_to_zmq_and_rejects_unavailable_shm() -> None:
    automatic = LyipSettings()
    explicit_shm = LyipSettings(default_backend="shm")
    override = LyipSettings(default_backend="shm", links={"worker": LyipLinkSettings(backend="zmq")})

    assert select_lyip_backend(automatic, "worker") is LyipBackend.ZMQ
    assert select_lyip_backend(automatic, "worker", native_shared_memory_available=True) is LyipBackend.SHM
    assert select_lyip_backend(override, "worker") is LyipBackend.ZMQ
    with pytest.raises(LyipError, match="shared-memory backend is unavailable"):
        select_lyip_backend(explicit_shm, "worker")


@pytest.mark.asyncio
async def test_zmq_router_dealer_preserve_lanes_sequences_and_generation() -> None:
    context = zmq.asyncio.Context()
    router = ZmqLyipRouter(
        context=context,
        endpoint="inproc://lyip-test",
        generation=1,
        business_hwm=2,
        control_hwm=1,
    )
    dealer = ZmqLyipDealer(
        context=context,
        endpoints=router.endpoints,
        generation=1,
        identity=b"runtime",
        business_hwm=2,
        control_hwm=1,
    )
    try:
        assert await dealer.offer(_frame("business", 0)) is LyipOfferResult.ACCEPTED
        assert await dealer.offer(_frame("control", 0, lane=LyipLane.CONTROL)) is LyipOfferResult.ACCEPTED
        identity, business = await router.receive(LyipLane.BUSINESS)
        control_identity, control = await router.receive(LyipLane.CONTROL)
        assert identity == control_identity == b"runtime"
        assert business.stream_id == "business"
        assert control.lane is LyipLane.CONTROL

        assert await router.offer(identity, _frame("reply", 0)) is LyipOfferResult.ACCEPTED
        assert (await dealer.receive(LyipLane.BUSINESS)).stream_id == "reply"
    finally:
        dealer.close()
        router.close()
        context.term()


@pytest.mark.asyncio
async def test_zmq_router_owns_sequences_per_directed_identity() -> None:
    context = zmq.asyncio.Context()
    router = ZmqLyipRouter(
        context=context,
        endpoint="inproc://lyip-directed-test",
        generation=1,
        business_hwm=4,
        control_hwm=4,
    )
    first = ZmqLyipDealer(
        context=context,
        endpoints=router.endpoints,
        generation=1,
        identity=b"first",
        business_hwm=4,
        control_hwm=4,
    )
    second = ZmqLyipDealer(
        context=context,
        endpoints=router.endpoints,
        generation=1,
        identity=b"second",
        business_hwm=4,
        control_hwm=4,
    )
    try:
        assert await first.offer(_frame("control", 0, lane=LyipLane.CONTROL)) is LyipOfferResult.ACCEPTED
        assert await second.offer(_frame("control", 0, lane=LyipLane.CONTROL)) is LyipOfferResult.ACCEPTED
        first_identity, first_frame = await router.receive(LyipLane.CONTROL)
        second_identity, second_frame = await router.receive(LyipLane.CONTROL)
        assert {first_identity, second_identity} == {b"first", b"second"}
        assert first_frame.sequence == second_frame.sequence == 0

        assert (
            await router.offer(first_identity, _frame("control", 0, lane=LyipLane.CONTROL))
            is LyipOfferResult.ACCEPTED
        )
        assert (
            await router.offer(second_identity, _frame("control", 0, lane=LyipLane.CONTROL))
            is LyipOfferResult.ACCEPTED
        )
        assert (await first.receive(LyipLane.CONTROL)).sequence == 0
        assert (await second.receive(LyipLane.CONTROL)).sequence == 0
    finally:
        first.close()
        second.close()
        router.close()
        context.term()


@pytest.mark.asyncio
async def test_zmq_router_disconnect_forgets_per_peer_sequence_state() -> None:
    context = zmq.asyncio.Context()
    router = ZmqLyipRouter(
        context=context,
        endpoint="inproc://lyip-disconnect-test",
        generation=1,
        business_hwm=4,
        control_hwm=4,
    )
    first = ZmqLyipDealer(
        context=context,
        endpoints=router.endpoints,
        generation=1,
        identity=b"reused",
        business_hwm=4,
        control_hwm=4,
    )
    try:
        assert await first.offer(_frame("control", 0, lane=LyipLane.CONTROL)) is LyipOfferResult.ACCEPTED
        identity, _received = await router.receive(LyipLane.CONTROL)
        assert identity == b"reused"
        assert await router.offer(identity, _frame("reply", 0)) is LyipOfferResult.ACCEPTED
        router.disconnect(identity)
        assert not router._received
        assert not router._sent
    finally:
        first.close()
        router.close()
        context.term()
