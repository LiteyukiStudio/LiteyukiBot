from __future__ import annotations

import asyncio

import pytest

from liteyukibot.broker import BoundedIngressPublisher


@pytest.mark.asyncio
async def test_bounded_ingress_publisher_is_fifo_and_drops_when_full() -> None:
    first_started = asyncio.Event()
    completed = asyncio.Event()
    release = asyncio.Event()
    received: list[str] = []

    async def handler(value: str) -> None:
        if value == "first":
            first_started.set()
            await release.wait()
        received.append(value)
        if value == "second":
            completed.set()

    publisher = BoundedIngressPublisher(handler, capacity=1, timeout_seconds=0.2)
    await publisher.start()

    assert publisher.submit("first") is True
    await asyncio.wait_for(first_started.wait(), timeout=0.2)
    assert publisher.submit("second") is True
    assert publisher.submit("third") is False

    release.set()
    await asyncio.wait_for(completed.wait(), timeout=0.5)
    await publisher.close()

    assert received == ["first", "second"]
    assert publisher.stats.accepted == 2
    assert publisher.stats.completed == 2
    assert publisher.stats.failed == 0
    assert publisher.stats.dropped == 1
    assert publisher.stats.pending == 0


@pytest.mark.asyncio
async def test_bounded_ingress_publisher_isolates_handler_failures_and_timeouts() -> None:
    completed = asyncio.Event()
    errors: list[Exception] = []

    async def handler(value: str) -> None:
        if value == "error":
            raise RuntimeError("upstream failed")
        if value == "slow":
            await asyncio.sleep(1)
        completed.set()

    def on_error(error: Exception) -> None:
        errors.append(error)
        raise RuntimeError("logging must not break the publisher")

    publisher = BoundedIngressPublisher(handler, timeout_seconds=0.01, on_error=on_error)
    await publisher.start()
    assert publisher.submit("error") is True
    assert publisher.submit("slow") is True
    assert publisher.submit("healthy") is True

    await asyncio.wait_for(completed.wait(), timeout=0.5)
    await publisher.close()

    assert [type(error) for error in errors] == [RuntimeError, TimeoutError]
    assert publisher.stats.accepted == 3
    assert publisher.stats.completed == 1
    assert publisher.stats.failed == 2
    assert publisher.stats.dropped == 0


@pytest.mark.asyncio
async def test_bounded_ingress_publisher_close_drops_pending_items() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def handler(_value: str) -> None:
        started.set()
        await release.wait()

    publisher = BoundedIngressPublisher(handler, capacity=2)
    assert publisher.submit("before-start") is False
    await publisher.start()
    assert publisher.submit("active") is True
    await asyncio.wait_for(started.wait(), timeout=0.2)
    assert publisher.submit("pending-1") is True
    assert publisher.submit("pending-2") is True

    await publisher.close()

    assert publisher.closed is True
    assert publisher.stats.dropped == 3
    release.set()
