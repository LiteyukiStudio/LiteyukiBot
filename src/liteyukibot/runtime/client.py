"""Reusable LYIP v1 client for supervised child runtimes."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Mapping, Sequence
from typing import Any

import zmq.asyncio

from ..exceptions import RuntimeProtocolError
from ..lyip import LyipError, LyipFrame, LyipLane, LyipOfferResult, ZmqLyipDealer
from .lyip import decode_runtime_message, encode_runtime_message
from .protocol import (
    PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    ActionRequest,
    ActionResponse,
    ConfigMessage,
    Heartbeat,
    Hello,
    JsonValue,
    ManagementRequest,
    ManagementResponse,
    ProtocolVersion,
    Ready,
    Welcome,
    WireMessage,
    json_mapping,
)

_DEFAULT_BUSINESS_HWM = 1024
_DEFAULT_CONTROL_HWM = 64
_LYIP_ENVIRONMENT_NAMES = (
    "LITEYUKI_LYIP_BUSINESS_ENDPOINT",
    "LITEYUKI_LYIP_CONTROL_ENDPOINT",
    "LITEYUKI_LYIP_GENERATION",
    "LITEYUKI_LYIP_LEASE_ID",
    "LITEYUKI_LYIP_IDENTITY",
    "LITEYUKI_RUNTIME_ID",
    "LITEYUKI_RUNTIME_TOKEN",
)
_LYIP_BOOTSTRAP_REQUIRED = (
    "LYIP runtime bootstrap is required; v5 TCP runtime environment variables are no longer supported"
)


class RuntimeClient:
    """Represent the runtime client contract."""
    def __init__(
        self,
        *,
        business_endpoint: str,
        control_endpoint: str,
        generation: int,
        lease_id: str,
        identity: str,
        runtime_id: str,
        kind: str,
        token: str,
        protocol_version: ProtocolVersion = PROTOCOL_VERSION,
        context: zmq.asyncio.Context | None = None,
    ) -> None:
        """Initialize the runtime client.

        Args:
            business_endpoint: The business endpoint value used by the operation.
            control_endpoint: The control endpoint value used by the operation.
            generation: Positive protocol or deployment generation.
            lease_id: Stable identifier for the lease.
            identity: The identity value used by the operation.
            runtime_id: Stable runtime identifier.
            kind: The kind value used by the operation.
            token: Authentication token presented at the boundary.
            protocol_version: The protocol version value used by the operation.
            context: Runtime or authorization context for the operation.

        Returns:
            None.
        """
        if not all(
            value and value == value.strip()
            for value in (business_endpoint, control_endpoint, lease_id, identity, runtime_id, kind, token)
        ):
            raise ValueError("LYIP runtime identity and endpoints must not be empty")
        if generation < 1:
            raise ValueError("LYIP runtime generation must be positive")
        if protocol_version not in SUPPORTED_PROTOCOL_VERSIONS:
            raise ValueError(f"unsupported runtime protocol version: {protocol_version}")

        encoded_identity = identity.encode("utf-8")
        if not encoded_identity:
            raise ValueError("LYIP runtime identity must not be empty")
        self.business_endpoint = business_endpoint
        self.control_endpoint = control_endpoint
        self.generation = generation
        self.lease_id = lease_id
        self.identity = identity
        self.runtime_id = runtime_id
        self.kind = kind
        self.token = token
        self.protocol_version = protocol_version
        self.negotiated_protocol: ProtocolVersion | None = None
        self._context = context if context is not None else zmq.asyncio.Context.instance()
        self._identity_bytes = encoded_identity
        self._dealer: ZmqLyipDealer | None = None
        self._send_lock = asyncio.Lock()
        self._receive_lock = asyncio.Lock()
        self._lane_receives: dict[LyipLane, asyncio.Task[LyipFrame]] = {}
        self._next_sequences: dict[str, int] = {}
        self._heartbeat_interval: float | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._capabilities: frozenset[str] = frozenset()
        self._pending_actions: dict[str, asyncio.Future[ActionResponse]] = {}
        self._pending_management: dict[str, asyncio.Future[ManagementResponse]] = {}
        self._closed = False

    @classmethod
    def from_environment(
        cls,
        kind: str,
        environment: Mapping[str, str] | None = None,
        *,
        protocol_version: ProtocolVersion = PROTOCOL_VERSION,
    ) -> RuntimeClient:
        """Create the runtime client from environment.

        Args:
            kind: The kind value used by the operation.
            environment: The environment value used by the operation.
            protocol_version: The protocol version value used by the operation.

        Returns:
            The `RuntimeClient` result produced by the operation.
        """
        values = os.environ if environment is None else environment
        missing = tuple(name for name in _LYIP_ENVIRONMENT_NAMES if not values.get(name, "").strip())
        if missing:
            names = ", ".join(missing)
            raise RuntimeError(f"{_LYIP_BOOTSTRAP_REQUIRED}; missing {names}")
        try:
            generation = int(values["LITEYUKI_LYIP_GENERATION"])
        except ValueError as error:
            raise ValueError("LITEYUKI_LYIP_GENERATION must be a positive integer") from error
        if generation < 1:
            raise ValueError("LITEYUKI_LYIP_GENERATION must be a positive integer")
        return cls(
            business_endpoint=values["LITEYUKI_LYIP_BUSINESS_ENDPOINT"],
            control_endpoint=values["LITEYUKI_LYIP_CONTROL_ENDPOINT"],
            generation=generation,
            lease_id=values["LITEYUKI_LYIP_LEASE_ID"],
            identity=values["LITEYUKI_LYIP_IDENTITY"],
            runtime_id=values["LITEYUKI_RUNTIME_ID"],
            kind=kind,
            token=values["LITEYUKI_RUNTIME_TOKEN"],
            protocol_version=protocol_version,
        )

    @property
    def connected(self) -> bool:
        """Return the runtime client's connected.

        Returns:
            Whether the requested condition is satisfied.
        """
        return self._dealer is not None and not self._closed

    async def connect(self) -> Mapping[str, JsonValue]:
        """Connect the runtime client operation.

        Returns:
            The `Mapping[str, JsonValue]` result produced by the operation.
        """
        if self._dealer is not None or self._closed:
            raise RuntimeError("runtime client connection is single-use")
        self._dealer = ZmqLyipDealer(
            context=self._context,
            endpoints={
                LyipLane.BUSINESS: self.business_endpoint,
                LyipLane.CONTROL: self.control_endpoint,
            },
            generation=self.generation,
            identity=self._identity_bytes,
            business_hwm=_DEFAULT_BUSINESS_HWM,
            control_hwm=_DEFAULT_CONTROL_HWM,
        )
        try:
            await self.send(
                Hello(
                    runtime_id=self.runtime_id,
                    kind=self.kind,
                    token=self.token,
                    protocol=self.protocol_version,
                )
            )
            welcome = await self._receive_lane(LyipLane.CONTROL)
            if not isinstance(welcome, Welcome):
                raise RuntimeProtocolError("expected welcome during runtime handshake")
            if welcome.protocol != self.protocol_version:
                raise RuntimeProtocolError("supervisor confirmed a different runtime protocol version")
            config = await self._receive_lane(LyipLane.CONTROL)
            if not isinstance(config, ConfigMessage):
                raise RuntimeProtocolError("expected config during runtime handshake")
            if welcome.heartbeat_interval <= 0:
                raise RuntimeProtocolError("runtime heartbeat interval must be positive")
            self._heartbeat_interval = welcome.heartbeat_interval
            self.negotiated_protocol = welcome.protocol
            return config.options
        except BaseException:
            await self.close()
            raise

    async def ready(self, capabilities: Sequence[str] = ()) -> None:
        """Implement the ready operation for the runtime client.

        Args:
            capabilities: The capabilities value used by the operation.

        Returns:
            None.
        """
        if self._heartbeat_task is not None:
            raise RuntimeError("runtime client is already ready")
        normalized = tuple(capabilities)
        await self.send(Ready(capabilities=normalized))
        self._capabilities = frozenset(normalized)
        assert self._heartbeat_interval is not None
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat(self._heartbeat_interval),
            name=f"runtime-heartbeat:{self.runtime_id}",
        )

    async def receive(self) -> WireMessage:
        """Receive the runtime client operation.

        Returns:
            The `WireMessage` result produced by the operation.
        """
        if self._dealer is None or self._closed:
            raise ConnectionError("runtime client is not connected")
        if self._receive_lock.locked():
            raise RuntimeError("runtime client already has an active receiver")
        async with self._receive_lock:
            while True:
                try:
                    message = await self._receive_any_lane()
                except (ConnectionError, LyipError, RuntimeProtocolError) as error:
                    self._fail_pending(error)
                    raise
                if isinstance(message, ActionResponse):
                    future = self._pending_actions.pop(message.correlation_id, None)
                    if future is not None and not future.done():
                        future.set_result(message)
                        continue
                if isinstance(message, ManagementResponse):
                    management_future = self._pending_management.pop(message.correlation_id, None)
                    if management_future is not None and not management_future.done():
                        management_future.set_result(message)
                        continue
                return message

    async def execute_action(
        self,
        correlation_id: str,
        payload: Mapping[str, Any],
        *,
        delivery_correlation_id: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> ActionResponse:
        """Execute action.

        Args:
            correlation_id: Stable identifier for the correlation.
            payload: JSON-safe payload carried by the operation.
            delivery_correlation_id: Stable identifier for the delivery correlation.
            timeout_seconds: Maximum duration to wait, in seconds.

        Returns:
            The `ActionResponse` result produced by the operation.
        """
        if timeout_seconds <= 0:
            raise ValueError("runtime action timeout must be positive")
        if self.negotiated_protocol not in (3, 4, 5):
            raise RuntimeError("child-originated actions require runtime protocol v3, v4, or v5")
        if delivery_correlation_id is not None and (
            not delivery_correlation_id or self.negotiated_protocol not in (4, 5)
        ):
            raise RuntimeError("action delivery correlation id requires runtime protocol v4 or v5")
        if self._heartbeat_task is None:
            raise RuntimeError("runtime client is not ready")
        if "runtime.actions.send" not in self._capabilities:
            raise RuntimeError("runtime client did not declare runtime.actions.send")
        if correlation_id in self._pending_actions:
            raise ValueError(f"duplicate action correlation id: {correlation_id}")

        request = ActionRequest(
            correlation_id=correlation_id,
            payload=json_mapping(payload),
            delivery_correlation_id=delivery_correlation_id,
        )
        future: asyncio.Future[ActionResponse] = asyncio.get_running_loop().create_future()
        self._pending_actions[correlation_id] = future
        try:
            await self.send(request)
            async with asyncio.timeout(timeout_seconds):
                return await future
        finally:
            self._pending_actions.pop(correlation_id, None)

    async def send(self, message: WireMessage) -> None:
        """Send the runtime client operation.

        Args:
            message: Message content associated with the operation.

        Returns:
            None.
        """
        dealer = self._dealer
        if dealer is None or self._closed:
            raise ConnectionError("runtime client is not connected")
        async with self._send_lock:
            if self._dealer is not dealer or self._closed:
                raise ConnectionError("runtime client is not connected")
            frame = self._encode(message)
            if await dealer.offer(frame) is LyipOfferResult.FULL:
                raise LyipError(f"LYIP {frame.lane} lane is full")
            self._next_sequences[frame.stream_id] = frame.sequence + 1

    async def execute_management(
        self, correlation_id: str, command: str, timeout_seconds: float = 30.0
    ) -> ManagementResponse:
        """Execute management.

        Args:
            correlation_id: Stable identifier for the correlation.
            command: Command or operation name to execute.
            timeout_seconds: Maximum duration to wait, in seconds.

        Returns:
            The `ManagementResponse` result produced by the operation.
        """
        if not command.strip() or timeout_seconds <= 0:
            raise ValueError("management command and timeout must be positive")
        if self.negotiated_protocol != 5 or "runtime.management.execute" not in self._capabilities:
            raise RuntimeError("runtime client did not declare runtime.management.execute over protocol v5")
        if correlation_id in self._pending_management:
            raise ValueError(f"duplicate management correlation id: {correlation_id}")
        future: asyncio.Future[ManagementResponse] = asyncio.get_running_loop().create_future()
        self._pending_management[correlation_id] = future
        try:
            await self.send(ManagementRequest(correlation_id=correlation_id, command=command))
            async with asyncio.timeout(timeout_seconds):
                return await future
        finally:
            self._pending_management.pop(correlation_id, None)

    async def close(self) -> None:
        """Close the runtime client and release its owned resources.

        Returns:
            None.
        """
        if self._closed:
            return
        self._closed = True
        self._fail_pending(ConnectionError("runtime client closed"))
        heartbeat, self._heartbeat_task = self._heartbeat_task, None
        self._capabilities = frozenset()
        if heartbeat is not None:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
        receives, self._lane_receives = tuple(self._lane_receives.values()), {}
        for receive in receives:
            receive.cancel()
        if receives:
            await asyncio.gather(*receives, return_exceptions=True)
        async with self._send_lock:
            dealer, self._dealer = self._dealer, None
            self.negotiated_protocol = None
            if dealer is not None:
                dealer.close()

    def _encode(self, message: WireMessage) -> LyipFrame:
        """Encode the runtime client operation.

        Args:
            message: Message content associated with the operation.

        Returns:
            The `LyipFrame` result produced by the operation.

        Notes:
            Internal implementation detail for `RuntimeClient._encode`. It delegates to
            `encode_runtime_message`, `get` while keeping intermediate state local to the owning operation.
        """
        probe = encode_runtime_message(
            message,
            generation=self.generation,
            stream_id="probe",
            sequence=0,
            lease_id=self.lease_id,
        )
        stream_id = f"runtime:{self.runtime_id}:{probe.lane}"
        return encode_runtime_message(
            message,
            generation=self.generation,
            stream_id=stream_id,
            sequence=self._next_sequences.get(stream_id, 0),
            lease_id=self.lease_id,
        )

    async def _receive_lane(self, lane: LyipLane) -> WireMessage:
        """Receive lane.

        Args:
            lane: The lane value used by the operation.

        Returns:
            The `WireMessage` result produced by the operation.

        Notes:
            Internal implementation detail for `RuntimeClient._receive_lane`. It delegates to `pop`,
            `create_task`, `receive`, `_decode` while keeping intermediate state local to the owning
            operation.
        """
        task = self._lane_receives.pop(lane, None)
        if task is None:
            dealer = self._dealer
            if dealer is None or self._closed:
                raise ConnectionError("runtime client is not connected")
            task = asyncio.create_task(dealer.receive(lane), name=f"runtime-lyip-receive:{self.runtime_id}:{lane}")
        frame = await task
        return self._decode(frame, lane)

    async def _receive_any_lane(self) -> WireMessage:
        """Receive any lane.

        Returns:
            The `WireMessage` result produced by the operation.

        Notes:
            Internal implementation detail for `RuntimeClient._receive_any_lane`. It delegates to
            `create_task`, `receive`, `wait`, `values` while keeping intermediate state local to the owning
            operation.
        """
        for lane in LyipLane:
            if lane not in self._lane_receives:
                dealer = self._dealer
                if dealer is None or self._closed:
                    raise ConnectionError("runtime client is not connected")
                self._lane_receives[lane] = asyncio.create_task(
                    dealer.receive(lane), name=f"runtime-lyip-receive:{self.runtime_id}:{lane}"
                )
        done, _ = await asyncio.wait(self._lane_receives.values(), return_when=asyncio.FIRST_COMPLETED)
        lane = LyipLane.CONTROL if self._lane_receives[LyipLane.CONTROL] in done else LyipLane.BUSINESS
        return await self._receive_lane(lane)

    def _decode(self, frame: LyipFrame, lane: LyipLane) -> WireMessage:
        """Decode the runtime client operation.

        Args:
            frame: The frame value used by the operation.
            lane: The lane value used by the operation.

        Returns:
            The `WireMessage` result produced by the operation.

        Notes:
            Internal implementation detail for `RuntimeClient._decode`. It delegates to
            `decode_runtime_message` while keeping intermediate state local to the owning operation.
        """
        if frame.lease_id != self.lease_id:
            raise LyipError("LYIP frame lease does not match runtime lease")
        if frame.lane is not lane:
            raise LyipError("LYIP frame arrived on the wrong lane")
        expected_stream_id = f"kernel:{self.runtime_id}:{lane}"
        if frame.stream_id != expected_stream_id:
            raise LyipError("LYIP frame stream does not match runtime direction")
        return decode_runtime_message(frame)

    def _fail_pending(self, error: BaseException) -> None:
        """Implement the fail pending operation for the runtime client.

        Args:
            error: The error value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `RuntimeClient._fail_pending`. It delegates to `values`,
            `done`, `set_exception`, `clear` while keeping intermediate state local to the owning operation.
        """
        for pending in (
            self._pending_actions,
            self._pending_management,
        ):
            for future in pending.values():
                if not future.done():
                    future.set_exception(error)
            pending.clear()

    async def _heartbeat(self, interval: float) -> None:
        """Implement the heartbeat operation for the runtime client.

        Args:
            interval: The interval value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `RuntimeClient._heartbeat`. It delegates to `sleep`, `send`,
            `monotonic` while keeping intermediate state local to the owning operation.
        """
        while True:
            await asyncio.sleep(interval)
            await self.send(Heartbeat(monotonic=time.monotonic()))


__all__ = ["RuntimeClient"]
