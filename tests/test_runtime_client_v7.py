from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest
import zmq.asyncio

from liteyukibot.exceptions import RuntimeProtocolError
from liteyukibot.lyip import LyipError, LyipLane, LyipOfferResult, ZmqLyipRouter
from liteyukibot.runtime import RuntimeClient
from liteyukibot.runtime.lyip import decode_runtime_message, encode_runtime_message
from liteyukibot.runtime.protocol import (
    PROTOCOL_VERSION,
    ActionRequest,
    ActionResponse,
    ConfigMessage,
    ErrorMessage,
    EventMessage,
    Heartbeat,
    Hello,
    ManagementRequest,
    ManagementResponse,
    ProtocolVersion,
    Ready,
    Shutdown,
    Welcome,
    WireMessage,
)


@dataclass
class _KernelPeer:
    router: ZmqLyipRouter
    sequences: dict[str, int] = field(default_factory=dict)

    async def receive(self, lane: LyipLane) -> tuple[bytes, WireMessage]:
        identity, frame = await self.router.receive(lane)
        assert frame.lease_id == "lease"
        assert frame.stream_id == f"runtime:fixture:{lane}"
        return identity, decode_runtime_message(frame)

    async def send(self, identity: bytes, message: WireMessage) -> None:
        probe = encode_runtime_message(message, generation=1, stream_id="probe", sequence=0, lease_id="lease")
        stream_id = f"kernel:fixture:{probe.lane}"
        frame = encode_runtime_message(
            message,
            generation=1,
            stream_id=stream_id,
            sequence=self.sequences.get(stream_id, 0),
            lease_id="lease",
        )
        assert await self.router.offer(identity, frame) is LyipOfferResult.ACCEPTED
        self.sequences[stream_id] = frame.sequence + 1


@dataclass
class _Fixture:
    context: zmq.asyncio.Context
    router: ZmqLyipRouter
    peer: _KernelPeer
    client: RuntimeClient

    async def close(self) -> None:
        await self.client.close()
        self.router.close()
        self.context.term()


def _fixture(protocol_version: ProtocolVersion = PROTOCOL_VERSION) -> _Fixture:
    context = zmq.asyncio.Context()
    router = ZmqLyipRouter(
        context=context,
        endpoint="inproc://runtime-client",
        generation=1,
        business_hwm=32,
        control_hwm=32,
    )
    client = RuntimeClient(
        business_endpoint=router.endpoints[LyipLane.BUSINESS],
        control_endpoint=router.endpoints[LyipLane.CONTROL],
        generation=1,
        lease_id="lease",
        identity="fixture-identity",
        runtime_id="fixture",
        kind="test",
        token="secret",
        protocol_version=protocol_version,
        context=context,
    )
    return _Fixture(context, router, _KernelPeer(router), client)


async def _connect(fixture: _Fixture, *, welcome: Welcome | None = None) -> bytes:
    connect = asyncio.create_task(fixture.client.connect())
    identity, hello = await fixture.peer.receive(LyipLane.CONTROL)
    assert hello == Hello(
        runtime_id="fixture", kind="test", token="secret", protocol=fixture.client.protocol_version
    )
    await fixture.peer.send(
        identity,
        welcome or Welcome(protocol=fixture.client.protocol_version, heartbeat_interval=0.01),
    )
    await fixture.peer.send(identity, ConfigMessage(options={"enabled": True}))
    assert await connect == {"enabled": True}
    return identity


def test_runtime_client_rejects_invalid_lyip_configuration() -> None:
    with pytest.raises(ValueError, match="LYIP runtime identity"):
        RuntimeClient(
            business_endpoint="",
            control_endpoint="inproc://control",
            generation=1,
            lease_id="lease",
            identity="identity",
            runtime_id="runtime",
            kind="test",
            token="secret",
        )
    with pytest.raises(ValueError, match="generation must be positive"):
        RuntimeClient(
            business_endpoint="inproc://business",
            control_endpoint="inproc://control",
            generation=0,
            lease_id="lease",
            identity="identity",
            runtime_id="runtime",
            kind="test",
            token="secret",
        )
    with pytest.raises(ValueError, match="unsupported runtime protocol version"):
        RuntimeClient(
            business_endpoint="inproc://business",
            control_endpoint="inproc://control",
            generation=1,
            lease_id="lease",
            identity="identity",
            runtime_id="runtime",
            kind="test",
            token="secret",
            protocol_version=6,  # type: ignore[arg-type]
        )


def test_runtime_client_requires_lyip_environment_without_tcp_fallback() -> None:
    with pytest.raises(RuntimeError, match="LYIP runtime bootstrap is required"):
        RuntimeClient.from_environment("test", {"LITEYUKI_RUNTIME_HOST": "127.0.0.1"})

    client = RuntimeClient.from_environment(
        "test",
        {
            "LITEYUKI_LYIP_BUSINESS_ENDPOINT": "inproc://business",
            "LITEYUKI_LYIP_CONTROL_ENDPOINT": "inproc://control",
            "LITEYUKI_LYIP_GENERATION": "7",
            "LITEYUKI_LYIP_LEASE_ID": "lease",
            "LITEYUKI_LYIP_IDENTITY": "runtime-identity",
            "LITEYUKI_RUNTIME_ID": "runtime",
            "LITEYUKI_RUNTIME_TOKEN": "token",
        },
    )
    assert client.generation == 7
    assert client.business_endpoint == "inproc://business"
    assert client.control_endpoint == "inproc://control"

    with pytest.raises(ValueError, match="positive integer"):
        RuntimeClient.from_environment(
            "test",
            {
                "LITEYUKI_LYIP_BUSINESS_ENDPOINT": "inproc://business",
                "LITEYUKI_LYIP_CONTROL_ENDPOINT": "inproc://control",
                "LITEYUKI_LYIP_GENERATION": "0",
                "LITEYUKI_LYIP_LEASE_ID": "lease",
                "LITEYUKI_LYIP_IDENTITY": "runtime-identity",
                "LITEYUKI_RUNTIME_ID": "runtime",
                "LITEYUKI_RUNTIME_TOKEN": "token",
            },
        )


@pytest.mark.asyncio
async def test_runtime_client_handshake_ready_heartbeat_and_close() -> None:
    fixture = _fixture()
    try:
        await _connect(fixture)
        await fixture.client.ready(("events",))
        identity, ready = await fixture.peer.receive(LyipLane.CONTROL)
        assert ready == Ready(capabilities=("events",))
        _, heartbeat = await fixture.peer.receive(LyipLane.CONTROL)
        assert identity == b"fixture-identity"
        assert isinstance(heartbeat, Heartbeat)
        await fixture.client.close()
        await fixture.client.close()
        assert fixture.client.connected is False
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_runtime_client_serializes_concurrent_writes_by_lane_sequence() -> None:
    fixture = _fixture()
    try:
        await _connect(fixture)
        await asyncio.gather(
            fixture.client.send(ErrorMessage(code="first", message="one")),
            fixture.client.send(ErrorMessage(code="second", message="two")),
        )
        _, first = await fixture.peer.receive(LyipLane.CONTROL)
        _, second = await fixture.peer.receive(LyipLane.CONTROL)
        assert {message.code for message in (first, second) if isinstance(message, ErrorMessage)} == {
            "first",
            "second",
        }
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_runtime_client_rejects_invalid_handshake_and_closes() -> None:
    fixture = _fixture()
    try:
        connect = asyncio.create_task(fixture.client.connect())
        identity, hello = await fixture.peer.receive(LyipLane.CONTROL)
        assert isinstance(hello, Hello)
        await fixture.peer.send(identity, ConfigMessage())
        with pytest.raises(RuntimeProtocolError, match="expected welcome"):
            await connect
        assert fixture.client.connected is False
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_runtime_client_can_negotiate_older_protocol() -> None:
    fixture = _fixture(protocol_version=2)
    try:
        await _connect(fixture)
        assert fixture.client.negotiated_protocol == 2
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_runtime_client_rejects_protocol_version_mismatch() -> None:
    fixture = _fixture()
    try:
        connect = asyncio.create_task(fixture.client.connect())
        identity, _ = await fixture.peer.receive(LyipLane.CONTROL)
        await fixture.peer.send(identity, Welcome(protocol=1))
        with pytest.raises(RuntimeProtocolError, match="different runtime protocol"):
            await connect
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_runtime_client_routes_business_response_without_stealing_control() -> None:
    fixture = _fixture()
    response = ActionResponse(correlation_id="action-1", ok=True, data={"message_id": "sent-1"})
    try:
        await _connect(fixture)
        await fixture.client.ready(("runtime.actions.send",))
        identity, _ = await fixture.peer.receive(LyipLane.CONTROL)
        action = asyncio.create_task(fixture.client.execute_action("action-1", {"value": 1}))
        _, request = await fixture.peer.receive(LyipLane.BUSINESS)
        assert request == ActionRequest(correlation_id="action-1", payload={"value": 1})
        await fixture.peer.send(identity, EventMessage(correlation_id="event-1", payload={"value": 2}))
        await fixture.peer.send(identity, response)
        await fixture.peer.send(identity, EventMessage(correlation_id="after-action", payload={}))
        await fixture.peer.send(identity, ManagementRequest(correlation_id="management-1", command="status"))
        await fixture.peer.send(identity, Shutdown())
        received = [await fixture.client.receive() for _ in range(4)]
        expected = (
            ManagementRequest(correlation_id="management-1", command="status"),
            EventMessage(correlation_id="event-1", payload={"value": 2}),
            EventMessage(correlation_id="after-action", payload={}),
            Shutdown(),
        )
        assert all(message in received for message in expected)
        assert await action == response
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_runtime_client_correlates_concurrent_actions_returned_in_reverse() -> None:
    fixture = _fixture()
    try:
        await _connect(fixture)
        await fixture.client.ready(("runtime.actions.send",))
        identity, _ = await fixture.peer.receive(LyipLane.CONTROL)
        first = asyncio.create_task(fixture.client.execute_action("first", {"order": 1}))
        second = asyncio.create_task(fixture.client.execute_action("second", {"order": 2}))
        _, first_request = await fixture.peer.receive(LyipLane.BUSINESS)
        _, second_request = await fixture.peer.receive(LyipLane.BUSINESS)
        assert isinstance(first_request, ActionRequest)
        assert isinstance(second_request, ActionRequest)
        for request in (second_request, first_request):
            await fixture.peer.send(
                identity,
                ActionResponse(correlation_id=request.correlation_id, ok=True, data=request.payload),
            )
        await fixture.peer.send(identity, EventMessage(correlation_id="after-actions", payload={}))
        await fixture.peer.send(identity, Shutdown())
        assert await fixture.client.receive() == Shutdown()
        assert await fixture.client.receive() == EventMessage(correlation_id="after-actions", payload={})
        assert (await first).data == {"order": 1}
        assert (await second).data == {"order": 2}
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_runtime_client_rejects_bad_lease_and_stream() -> None:
    fixture = _fixture()
    try:
        identity = await _connect(fixture)
        frame = encode_runtime_message(
            Shutdown(),
            generation=1,
            stream_id="kernel:fixture:control",
            sequence=fixture.peer.sequences["kernel:fixture:control"],
            lease_id="wrong-lease",
        )
        assert await fixture.router.offer(identity, frame) is LyipOfferResult.ACCEPTED
        with pytest.raises(LyipError, match="lease"):
            await fixture.client.receive()
        stream_frame = encode_runtime_message(
            Shutdown(), generation=1, stream_id="kernel:other:control", sequence=0, lease_id="lease"
        )
        assert await fixture.router.offer(identity, stream_frame) is LyipOfferResult.ACCEPTED
        with pytest.raises(LyipError, match="stream"):
            await fixture.client.receive()
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_runtime_client_close_fails_pending_action() -> None:
    fixture = _fixture()
    try:
        await _connect(fixture)
        await fixture.client.ready(("runtime.actions.send",))
        await fixture.peer.receive(LyipLane.CONTROL)
        action = asyncio.create_task(fixture.client.execute_action("pending", {}))
        await fixture.peer.receive(LyipLane.BUSINESS)
        await fixture.client.close()
        with pytest.raises(ConnectionError, match="runtime client closed"):
            await action
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_runtime_client_executes_capability_gated_management_command() -> None:
    fixture = _fixture()
    try:
        await _connect(fixture)
        await fixture.client.ready(("runtime.management.execute",))
        identity, _ = await fixture.peer.receive(LyipLane.CONTROL)
        management = asyncio.create_task(fixture.client.execute_management("management-1", "status"))
        _, request = await fixture.peer.receive(LyipLane.CONTROL)
        assert request == ManagementRequest(correlation_id="management-1", command="status")
        response = ManagementResponse(correlation_id="management-1", ok=True, text="ready")
        await fixture.peer.send(identity, response)
        await fixture.peer.send(identity, Shutdown())
        assert await fixture.client.receive() == Shutdown()
        assert await management == response
    finally:
        await fixture.close()
