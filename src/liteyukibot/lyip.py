"""Transport-neutral Liteyuki IPC test primitives."""

from __future__ import annotations

import json
from base64 import b64decode, b64encode
from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

import zmq
import zmq.asyncio

from .config.models import LyipSettings


class LyipError(RuntimeError):
    pass


class LyipLane(StrEnum):
    BUSINESS = "business"
    CONTROL = "control"


class LyipOfferResult(StrEnum):
    ACCEPTED = "accepted"
    FULL = "full"


class LyipBackend(StrEnum):
    SHM = "shm"
    ZMQ = "zmq"


@dataclass(frozen=True, slots=True)
class LyipFrame:
    protocol: Literal[1]
    generation: int
    lane: LyipLane
    type_id: int
    stream_id: str
    sequence: int
    lease_id: str
    payload: bytes

    def __post_init__(self) -> None:
        if self.generation < 1 or self.type_id < 0 or self.sequence < 0:
            raise ValueError("LYIP generation, type ID, and sequence must be non-negative")
        if not self.stream_id or self.stream_id != self.stream_id.strip() or not self.lease_id:
            raise ValueError("LYIP stream and lease identifiers must be non-empty")


def select_lyip_backend(
    settings: LyipSettings,
    runtime_id: str,
    *,
    native_shared_memory_available: bool = False,
) -> LyipBackend:
    """Resolve one runtime link without claiming an unavailable native transport."""

    link = settings.links.get(runtime_id)
    requested = link.backend if link is not None and link.backend is not None else settings.default_backend
    if requested == "auto":
        return LyipBackend.SHM if native_shared_memory_available else LyipBackend.ZMQ
    if requested == "shm" and not native_shared_memory_available:
        raise LyipError("LYIP native shared-memory backend is unavailable")
    return LyipBackend(requested)


class InMemoryLyipLink:
    """Bounded deterministic link used as the semantic reference backend."""

    def __init__(self, *, generation: int, business_capacity: int, control_capacity: int) -> None:
        if generation < 1 or business_capacity < 1 or control_capacity < 1:
            raise ValueError("LYIP generation and lane capacities must be positive")
        self.generation = generation
        self._capacities = {LyipLane.BUSINESS: business_capacity, LyipLane.CONTROL: control_capacity}
        self._frames = {LyipLane.BUSINESS: deque[LyipFrame](), LyipLane.CONTROL: deque[LyipFrame]()}
        self._next_sequence: dict[str, int] = {}

    def offer(self, frame: LyipFrame) -> LyipOfferResult:
        if frame.generation != self.generation:
            raise LyipError("LYIP frame generation does not match link generation")
        expected = self._next_sequence.get(frame.stream_id, 0)
        if frame.sequence != expected:
            raise LyipError(f"LYIP frame sequence {frame.sequence} does not match expected {expected}")
        lane = self._frames[frame.lane]
        if len(lane) >= self._capacities[frame.lane]:
            return LyipOfferResult.FULL
        lane.append(frame)
        self._next_sequence[frame.stream_id] = expected + 1
        return LyipOfferResult.ACCEPTED

    def receive(self, lane: LyipLane) -> LyipFrame | None:
        frames = self._frames[lane]
        return frames.popleft() if frames else None

    def pressure(self, lane: LyipLane) -> tuple[int, int]:
        return len(self._frames[lane]), self._capacities[lane]


def _encode_frame(frame: LyipFrame) -> bytes:
    return json.dumps(
        {
            "protocol": frame.protocol,
            "generation": frame.generation,
            "lane": frame.lane,
            "type_id": frame.type_id,
            "stream_id": frame.stream_id,
            "sequence": frame.sequence,
            "lease_id": frame.lease_id,
            "payload": b64encode(frame.payload).decode("ascii"),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _decode_frame(raw: bytes) -> LyipFrame:
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError
        return LyipFrame(
            value["protocol"], value["generation"], LyipLane(value["lane"]), value["type_id"],
            value["stream_id"], value["sequence"], value["lease_id"], b64decode(value["payload"], validate=True),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise LyipError("LYIP ZMQ frame is invalid") from error


class _ZmqEndpoint:
    def __init__(self, generation: int) -> None:
        self.generation = generation
        self._sent: dict[tuple[bytes | None, str], int] = {}
        self._received: dict[tuple[bytes | None, str], int] = {}

    def _validate_offer(self, frame: LyipFrame, *, peer: bytes | None = None) -> int:
        if frame.generation != self.generation:
            raise LyipError("LYIP frame generation does not match link generation")
        expected = self._sent.get((peer, frame.stream_id), 0)
        if frame.sequence != expected:
            raise LyipError(f"LYIP frame sequence {frame.sequence} does not match expected {expected}")
        return expected

    def _commit_offer(self, frame: LyipFrame, expected: int, *, peer: bytes | None = None) -> None:
        self._sent[(peer, frame.stream_id)] = expected + 1

    def _receive(self, frame: LyipFrame, *, peer: bytes | None = None) -> LyipFrame:
        if frame.generation != self.generation:
            raise LyipError("LYIP frame generation does not match link generation")
        expected = self._received.get((peer, frame.stream_id), 0)
        if frame.sequence != expected:
            raise LyipError(f"LYIP received sequence {frame.sequence} does not match expected {expected}")
        self._received[(peer, frame.stream_id)] = expected + 1
        return frame


class ZmqLyipRouter(_ZmqEndpoint):
    """Kernel-side directed LYIP endpoint with isolated lane sockets."""

    def __init__(
        self,
        *,
        context: zmq.asyncio.Context,
        endpoint: str,
        generation: int,
        business_hwm: int,
        control_hwm: int,
    ) -> None:
        super().__init__(generation)
        self.endpoints: dict[LyipLane, str] = {}
        self._sockets: dict[LyipLane, zmq.asyncio.Socket] = {}
        for lane, hwm in ((LyipLane.BUSINESS, business_hwm), (LyipLane.CONTROL, control_hwm)):
            socket = context.socket(zmq.ROUTER)
            socket.sndhwm = hwm
            socket.rcvhwm = hwm
            if endpoint.startswith("tcp://") and endpoint.rsplit(":", 1)[-1] in {"0", "*"}:
                base_endpoint = endpoint.rsplit(":", 1)[0]
                port = socket.bind_to_random_port(base_endpoint)
                self.endpoints[lane] = f"{base_endpoint}:{port}"
            else:
                self.endpoints[lane] = f"{endpoint}.{lane}"
                socket.bind(self.endpoints[lane])
            self._sockets[lane] = socket

    async def receive(self, lane: LyipLane) -> tuple[bytes, LyipFrame]:
        identity, raw = await self._sockets[lane].recv_multipart()
        frame = self._receive(_decode_frame(raw), peer=identity)
        if frame.lane is not lane:
            raise LyipError("LYIP ZMQ frame arrived on the wrong lane")
        return identity, frame

    async def offer(self, identity: bytes, frame: LyipFrame) -> LyipOfferResult:
        expected = self._validate_offer(frame, peer=identity)
        try:
            await self._sockets[frame.lane].send_multipart((identity, _encode_frame(frame)), flags=zmq.NOBLOCK)
        except zmq.Again:
            return LyipOfferResult.FULL
        self._commit_offer(frame, expected, peer=identity)
        return LyipOfferResult.ACCEPTED

    def close(self) -> None:
        for socket in self._sockets.values():
            socket.close(linger=0)


class ZmqLyipDealer(_ZmqEndpoint):
    """Runtime-side directed LYIP endpoint paired with a kernel router."""

    def __init__(
        self,
        *,
        context: zmq.asyncio.Context,
        endpoints: dict[LyipLane, str],
        generation: int,
        identity: bytes,
        business_hwm: int,
        control_hwm: int,
    ) -> None:
        super().__init__(generation)
        self._sockets: dict[LyipLane, zmq.asyncio.Socket] = {}
        for lane, hwm in ((LyipLane.BUSINESS, business_hwm), (LyipLane.CONTROL, control_hwm)):
            socket = context.socket(zmq.DEALER)
            socket.identity = identity
            socket.sndhwm = hwm
            socket.rcvhwm = hwm
            socket.connect(endpoints[lane])
            self._sockets[lane] = socket

    async def offer(self, frame: LyipFrame) -> LyipOfferResult:
        expected = self._validate_offer(frame)
        try:
            await self._sockets[frame.lane].send(_encode_frame(frame), flags=zmq.NOBLOCK)
        except zmq.Again:
            return LyipOfferResult.FULL
        self._commit_offer(frame, expected)
        return LyipOfferResult.ACCEPTED

    async def receive(self, lane: LyipLane) -> LyipFrame:
        frame = self._receive(_decode_frame(await self._sockets[lane].recv()))
        if frame.lane is not lane:
            raise LyipError("LYIP ZMQ frame arrived on the wrong lane")
        return frame

    def close(self) -> None:
        for socket in self._sockets.values():
            socket.close(linger=0)
