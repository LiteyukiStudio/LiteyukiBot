"""Transport-neutral Liteyuki IPC test primitives."""

from __future__ import annotations

import json
from base64 import b64decode, b64encode
from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal
from urllib.parse import urlparse

import zmq
import zmq.asyncio

from .config.models import LyipSettings

MAX_LYIP_PAYLOAD_SIZE = 8 * 1024 * 1024
MAX_LYIP_WIRE_FRAME_SIZE = 12 * 1024 * 1024


class LyipError(RuntimeError):
    """Raised when the lyip contract cannot be satisfied."""
    pass


class LyipLane(StrEnum):
    """Enumerate the supported lyip lane values."""
    BUSINESS = "business"
    CONTROL = "control"


class LyipOfferResult(StrEnum):
    """Enumerate the supported lyip offer result values."""
    ACCEPTED = "accepted"
    FULL = "full"


class LyipBackend(StrEnum):
    """Enumerate the supported lyip backend values."""
    SHM = "shm"
    ZMQ = "zmq"


@dataclass(frozen=True, slots=True)
class LyipFrame:
    """Carry one generation-scoped, sequenced LYIP transport payload."""
    protocol: Literal[1]
    generation: int
    lane: LyipLane
    type_id: int
    stream_id: str
    sequence: int
    lease_id: str
    payload: bytes

    def __post_init__(self) -> None:
        """Validate frame identity fields and the opaque payload size.

        Returns:
            None.

        Security:
            Payloads originate at process boundaries and may be malformed or
            oversized. Validation is retained because bridges require opaque
            transport; the 8 MiB cap bounds content retained by downstream
            queues. See `docs/security/trusted-boundaries.md#lyip-frames`.
        """
        if self.generation < 1 or self.type_id < 0 or self.sequence < 0:
            raise ValueError("LYIP generation, type ID, and sequence must be non-negative")
        if not self.stream_id or self.stream_id != self.stream_id.strip() or not self.lease_id:
            raise ValueError("LYIP stream and lease identifiers must be non-empty")
        if len(self.payload) > MAX_LYIP_PAYLOAD_SIZE:
            raise ValueError(f"LYIP payload exceeds {MAX_LYIP_PAYLOAD_SIZE} bytes")


def select_lyip_backend(
    settings: LyipSettings,
    runtime_id: str,
    *,
    native_shared_memory_available: bool = False,
) -> LyipBackend:
    """Resolve one runtime link without claiming an unavailable native transport.

    Args:
        settings: Validated application settings.
        runtime_id: Stable runtime identifier.
        native_shared_memory_available: The native shared memory available value used by the operation.

    Returns:
        The `LyipBackend` result produced by the operation.
    """

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
        """Initialize the in memory lyip link.

        Args:
            generation: Positive protocol or deployment generation.
            business_capacity: Maximum retained business count.
            control_capacity: Maximum retained control count.

        Returns:
            None.
        """
        if generation < 1 or business_capacity < 1 or control_capacity < 1:
            raise ValueError("LYIP generation and lane capacities must be positive")
        self.generation = generation
        self._capacities = {LyipLane.BUSINESS: business_capacity, LyipLane.CONTROL: control_capacity}
        self._frames = {LyipLane.BUSINESS: deque[LyipFrame](), LyipLane.CONTROL: deque[LyipFrame]()}
        self._next_sequence: dict[str, int] = {}

    def offer(self, frame: LyipFrame) -> LyipOfferResult:
        """Append a correctly sequenced frame when its lane has capacity.

        Args:
            frame: The frame value used by the operation.

        Returns:
            The `LyipOfferResult` result produced by the operation.
        """
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
        """Remove and return the oldest frame from one lane.

        Args:
            lane: The lane value used by the operation.

        Returns:
            The `LyipFrame | None` result produced by the operation.
        """
        frames = self._frames[lane]
        return frames.popleft() if frames else None

    def pressure(self, lane: LyipLane) -> tuple[int, int]:
        """Return the lane's current depth and configured capacity.

        Args:
            lane: The lane value used by the operation.

        Returns:
            The `tuple[int, int]` result produced by the operation.
        """
        return len(self._frames[lane]), self._capacities[lane]


def _encode_frame(frame: LyipFrame) -> bytes:
    """Encode one LYIP frame as deterministic JSON with base64 payload data.

    Args:
        frame: Validated frame to serialize for transport.

    Returns:
        Encoded wire bytes ready for a ZMQ socket.

    Notes:
        Base64 is used because the reference ZMQ codec is JSON. Encoded size is
        checked after serialization so metadata and base64 expansion are also bounded.

    Security:
        Opaque bridge content can consume memory before entering an HWM-bounded
        queue. The 12 MiB wire cap is retained with the JSON transport to bound
        that exposure. See `docs/security/trusted-boundaries.md#lyip-frames`.
    """
    encoded = json.dumps(
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
    if len(encoded) > MAX_LYIP_WIRE_FRAME_SIZE:
        raise LyipError(f"LYIP wire frame exceeds {MAX_LYIP_WIRE_FRAME_SIZE} bytes")
    return encoded


def _decode_frame(raw: bytes) -> LyipFrame:
    """Decode and validate one bounded LYIP JSON wire frame.

    Args:
        raw: Untrusted bytes received from a local transport peer.

    Returns:
        Validated frame with strictly decoded base64 payload bytes.

    Notes:
        Size is rejected before JSON and base64 decoding. Field-level generation,
        sequence, and lane checks remain the endpoint's responsibility.

    Security:
        A registered peer can still send malformed bytes. Strict JSON shape,
        base64 validation, and the wire limit are retained because LYIP must
        accept framework bridge traffic. See
        `docs/security/trusted-boundaries.md#lyip-frames`.
    """
    if len(raw) > MAX_LYIP_WIRE_FRAME_SIZE:
        raise LyipError(f"LYIP wire frame exceeds {MAX_LYIP_WIRE_FRAME_SIZE} bytes")
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
    """Track per-peer stream sequences shared by ZMQ router and dealer endpoints."""
    def __init__(self, generation: int) -> None:
        """Initialize the zmq endpoint.

        Args:
            generation: Positive protocol or deployment generation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_ZmqEndpoint.__init__`. It performs the local state
            transition directly and is not a stable extension boundary.
        """
        self.generation = generation
        self._sent: dict[tuple[bytes | None, str], int] = {}
        self._received: dict[tuple[bytes | None, str], int] = {}

    def _validate_offer(self, frame: LyipFrame, *, peer: bytes | None = None) -> int:
        """Validate offer.

        Args:
            frame: The frame value used by the operation.
            peer: The peer value used by the operation.

        Returns:
            The `int` result produced by the operation.

        Notes:
            Internal implementation detail for `_ZmqEndpoint._validate_offer`. It delegates to `get` while
            keeping intermediate state local to the owning operation.
        """
        if frame.generation != self.generation:
            raise LyipError("LYIP frame generation does not match link generation")
        expected = self._sent.get((peer, frame.stream_id), 0)
        if frame.sequence != expected:
            raise LyipError(f"LYIP frame sequence {frame.sequence} does not match expected {expected}")
        return expected

    def _commit_offer(self, frame: LyipFrame, expected: int, *, peer: bytes | None = None) -> None:
        """Implement the commit offer operation for the zmq endpoint.

        Args:
            frame: The frame value used by the operation.
            expected: The expected value used by the operation.
            peer: The peer value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_ZmqEndpoint._commit_offer`. It performs the local state
            transition directly and is not a stable extension boundary.
        """
        self._sent[(peer, frame.stream_id)] = expected + 1

    def _receive(self, frame: LyipFrame, *, peer: bytes | None = None) -> LyipFrame:
        """Receive the zmq endpoint operation.

        Args:
            frame: The frame value used by the operation.
            peer: The peer value used by the operation.

        Returns:
            The `LyipFrame` result produced by the operation.

        Notes:
            Internal implementation detail for `_ZmqEndpoint._receive`. It delegates to `get` while keeping
            intermediate state local to the owning operation.
        """
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
        """Initialize the zmq lyip router.

        Args:
            context: Runtime or authorization context for the operation.
            endpoint: Transport endpoint used for the connection.
            generation: Positive protocol or deployment generation.
            business_hwm: The business hwm value used by the operation.
            control_hwm: The control hwm value used by the operation.

        Returns:
            None.
        """
        super().__init__(generation)
        self.endpoints: dict[LyipLane, str] = {}
        self._sockets: dict[LyipLane, zmq.asyncio.Socket] = {}
        for lane, hwm in ((LyipLane.BUSINESS, business_hwm), (LyipLane.CONTROL, control_hwm)):
            socket = context.socket(zmq.ROUTER)
            socket.sndhwm = hwm
            socket.rcvhwm = hwm
            socket.setsockopt(zmq.MAXMSGSIZE, MAX_LYIP_WIRE_FRAME_SIZE)
            if endpoint.startswith("tcp://") and endpoint.rsplit(":", 1)[-1] in {"0", "*"}:
                base_endpoint = endpoint.rsplit(":", 1)[0]
                port = socket.bind_to_random_port(base_endpoint)
                self.endpoints[lane] = f"{base_endpoint}:{port}"
            elif endpoint.startswith("tcp://"):
                parsed = urlparse(endpoint)
                if parsed.port is None or parsed.port >= 65_535:
                    raise LyipError("LYIP TCP endpoint must leave one port available for its business lane")
                port = parsed.port + (0 if lane is LyipLane.CONTROL else 1)
                host = parsed.hostname
                if host is None:
                    raise LyipError("LYIP TCP endpoint host is invalid")
                bind_host = f"[{host}]" if ":" in host else host
                self.endpoints[lane] = f"tcp://{bind_host}:{port}"
                socket.bind(self.endpoints[lane])
            else:
                self.endpoints[lane] = f"{endpoint}.{lane}"
                socket.bind(self.endpoints[lane])
            self._sockets[lane] = socket

    async def receive(self, lane: LyipLane) -> tuple[bytes, LyipFrame]:
        """Receive, decode, and sequence-check one frame from a router lane.

        Args:
            lane: The lane value used by the operation.

        Returns:
            Authenticated socket identity and validated frame.

        Security:
            ZMQ allocates inbound messages at the transport boundary. The socket
            `MAXMSGSIZE` limit and codec validation remain necessary because HWM
            limits message count, not individual size. See
            `docs/security/trusted-boundaries.md#lyip-frames`.
        """
        identity, raw = await self._sockets[lane].recv_multipart()
        frame = self._receive(_decode_frame(raw), peer=identity)
        if frame.lane is not lane:
            raise LyipError("LYIP ZMQ frame arrived on the wrong lane")
        return identity, frame

    async def offer(self, identity: bytes, frame: LyipFrame) -> LyipOfferResult:
        """Offer one sequenced frame to a specific router identity.

        Args:
            identity: The identity value used by the operation.
            frame: The frame value used by the operation.

        Returns:
            The `LyipOfferResult` result produced by the operation.
        """
        expected = self._validate_offer(frame, peer=identity)
        try:
            await self._sockets[frame.lane].send_multipart((identity, _encode_frame(frame)), flags=zmq.NOBLOCK)
        except zmq.Again:
            return LyipOfferResult.FULL
        self._commit_offer(frame, expected, peer=identity)
        return LyipOfferResult.ACCEPTED

    def disconnect(self, identity: bytes) -> None:
        """Forget per-peer stream state after a broker session is terminalized.

        Args:
            identity: The identity value used by the operation.

        Returns:
            None.
        """

        for state in (self._sent, self._received):
            for key in tuple(state):
                if key[0] == identity:
                    state.pop(key, None)

    def close(self) -> None:
        """Close the zmq lyip router and release its owned resources.

        Returns:
            None.
        """
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
        """Initialize the zmq lyip dealer.

        Args:
            context: Runtime or authorization context for the operation.
            endpoints: The endpoints value used by the operation.
            generation: Positive protocol or deployment generation.
            identity: The identity value used by the operation.
            business_hwm: The business hwm value used by the operation.
            control_hwm: The control hwm value used by the operation.

        Returns:
            None.
        """
        super().__init__(generation)
        self._sockets: dict[LyipLane, zmq.asyncio.Socket] = {}
        for lane, hwm in ((LyipLane.BUSINESS, business_hwm), (LyipLane.CONTROL, control_hwm)):
            socket = context.socket(zmq.DEALER)
            socket.identity = identity
            socket.sndhwm = hwm
            socket.rcvhwm = hwm
            socket.setsockopt(zmq.MAXMSGSIZE, MAX_LYIP_WIRE_FRAME_SIZE)
            socket.connect(endpoints[lane])
            self._sockets[lane] = socket

    async def offer(self, frame: LyipFrame) -> LyipOfferResult:
        """Offer the zmq lyip dealer operation.

        Args:
            frame: The frame value used by the operation.

        Returns:
            The `LyipOfferResult` result produced by the operation.
        """
        expected = self._validate_offer(frame)
        try:
            await self._sockets[frame.lane].send(_encode_frame(frame), flags=zmq.NOBLOCK)
        except zmq.Again:
            return LyipOfferResult.FULL
        self._commit_offer(frame, expected)
        return LyipOfferResult.ACCEPTED

    async def receive(self, lane: LyipLane) -> LyipFrame:
        """Receive the zmq lyip dealer operation.

        Args:
            lane: The lane value used by the operation.

        Returns:
            The `LyipFrame` result produced by the operation.
        """
        frame = self._receive(_decode_frame(await self._sockets[lane].recv()))
        if frame.lane is not lane:
            raise LyipError("LYIP ZMQ frame arrived on the wrong lane")
        return frame

    def close(self) -> None:
        """Close the zmq lyip dealer and release its owned resources.

        Returns:
            None.
        """
        for socket in self._sockets.values():
            socket.close(linger=0)
