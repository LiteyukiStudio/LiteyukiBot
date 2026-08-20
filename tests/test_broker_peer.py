from __future__ import annotations

import asyncio

import pytest
import zmq.asyncio
from pydantic import ValidationError

from liteyukibot.broker import (
    ActionResourceDeclaration,
    BridgeAccess,
    BridgeClient,
    BridgeManifest,
    BridgeRegister,
    BridgeRegistered,
    BridgeRegistrationError,
    BridgeRejected,
    BridgeUnregister,
    BrokerLedger,
    BrokerPeerServer,
    BrokerPeerService,
    BrokerWireError,
    decode_broker_message,
    encode_broker_message,
)
from liteyukibot.lyip import LyipError, LyipFrame, LyipLane, LyipOfferResult, ZmqLyipDealer


def _manifest(bridge_id: str = "astrbot") -> BridgeManifest:
    return BridgeManifest(
        bridge_id=bridge_id,
        access=BridgeAccess.LIMITED,
        subscriptions=("message.created",),
        action_resources=(ActionResourceDeclaration(kind="message.send", resource_prefix="bot:"),),
    )


def _register_frame(
    *,
    bridge_id: str = "astrbot",
    token: str = "token",
    sequence: int = 0,
) -> LyipFrame:
    manifest = _manifest(bridge_id)
    return encode_broker_message(
        BridgeRegister(bridge_id=bridge_id, instance_token=token, manifest=manifest),
        generation=1,
        stream_id=f"bridge:{bridge_id}:control",
        sequence=sequence,
        lease_id="registration",
    )


def test_manifest_is_immutable_json_safe_and_rejects_invalid_declarations() -> None:
    manifest = _manifest()

    assert manifest.model_dump(mode="json") == {
        "bridge_id": "astrbot",
        "access": "limited",
        "subscriptions": ["message.created"],
        "action_resources": [{"kind": "message.send", "resource_prefix": "bot:"}],
        "tools": [],
        "controls": [],
    }
    with pytest.raises(ValidationError, match="duplicates"):
        BridgeManifest(
            bridge_id="astrbot",
            access=BridgeAccess.LIMITED,
            subscriptions=("message.created", "message.created"),
        )
    with pytest.raises(ValidationError, match="non-empty"):
        BridgeManifest(bridge_id=" ", access=BridgeAccess.LIMITED)


def test_event_ledger_defaults_are_consistent_across_broker_hosts() -> None:
    expected = (1024, 16384, 3600.0, 30.0)

    ledger = BrokerLedger()
    service = BrokerPeerService(instance_tokens={"astrbot": "token"}, generation=1)
    context = zmq.asyncio.Context()
    server = BrokerPeerServer(
        context=context,
        endpoint="inproc://broker-defaults",
        generation=1,
        instance_tokens={"astrbot": "token"},
    )
    try:
        for candidate in (ledger, service.ledger, server.service.ledger):
            assert (
                candidate.active_capacity,
                candidate.terminal_capacity,
                candidate.terminal_ttl_seconds,
                candidate.delivery_timeout_seconds,
            ) == expected
    finally:
        server.close()
        context.term()


def test_protocol_rejects_wrong_lane_type_id_and_malformed_payload() -> None:
    frame = _register_frame()
    wrong_lane = LyipFrame(
        protocol=frame.protocol,
        generation=frame.generation,
        lane=LyipLane.BUSINESS,
        type_id=frame.type_id,
        stream_id=frame.stream_id,
        sequence=frame.sequence,
        lease_id=frame.lease_id,
        payload=frame.payload,
    )
    malformed = LyipFrame(
        protocol=frame.protocol,
        generation=frame.generation,
        lane=frame.lane,
        type_id=frame.type_id,
        stream_id=frame.stream_id,
        sequence=frame.sequence,
        lease_id=frame.lease_id,
        payload=b"{",
    )

    assert isinstance(decode_broker_message(frame), BridgeRegister)
    with pytest.raises(BrokerWireError, match="wrong LYIP lane"):
        decode_broker_message(wrong_lane)
    with pytest.raises(BrokerWireError, match="payload is invalid"):
        decode_broker_message(malformed)


def test_service_rejects_unknown_token_duplicate_and_unregistered_business_peers() -> None:
    service = BrokerPeerService(instance_tokens={"astrbot": "token"}, generation=1)
    peer = b"astrbot-peer"

    unknown = service.handle_control(peer, _register_frame(bridge_id="unknown"))
    assert isinstance(decode_broker_message(unknown), BridgeRejected)
    assert decode_broker_message(unknown).code == "unknown_bridge"  # type: ignore[union-attr]

    invalid_token = service.handle_control(peer, _register_frame(token="wrong"))
    assert isinstance(decode_broker_message(invalid_token), BridgeRejected)
    assert decode_broker_message(invalid_token).code == "invalid_token"  # type: ignore[union-attr]

    registered = service.handle_control(peer, _register_frame())
    assert isinstance(decode_broker_message(registered), BridgeRegistered)
    duplicate = service.handle_control(peer, _register_frame(sequence=1))
    assert isinstance(decode_broker_message(duplicate), BridgeRejected)
    assert decode_broker_message(duplicate).code == "already_registered"  # type: ignore[union-attr]

    business = LyipFrame(1, 1, LyipLane.BUSINESS, 999, "business", 0, "lease", b"{}")
    with pytest.raises(BridgeRegistrationError, match="session binding"):
        service.require_business_peer(peer, business)
    session = service.sessions[0]
    bound_business = LyipFrame(
        1,
        1,
        LyipLane.BUSINESS,
        999,
        f"bridge:astrbot:{session.session_id}:events",
        0,
        "lease",
        b"{}",
    )
    assert service.require_business_peer(peer, bound_business).bridge_id == "astrbot"
    with pytest.raises(BridgeRegistrationError, match="unregistered"):
        service.require_business_peer(b"unregistered", bound_business)


def test_service_releases_registration_after_explicit_disconnect() -> None:
    service = BrokerPeerService(instance_tokens={"astrbot": "token"}, generation=1)
    peer = b"astrbot-peer"
    response = service.handle_control(peer, _register_frame())
    first = decode_broker_message(response)
    assert isinstance(first, BridgeRegistered)

    stale = _register_frame()
    stale = LyipFrame(
        stale.protocol,
        2,
        stale.lane,
        stale.type_id,
        stale.stream_id,
        stale.sequence,
        stale.lease_id,
        stale.payload,
    )
    stale_response = decode_broker_message(service.handle_control(peer, stale))
    assert isinstance(stale_response, BridgeRejected)
    assert stale_response.code == "stale_generation"

    assert service.disconnect(peer) is not None
    response = service.handle_control(peer, _register_frame(sequence=1))
    assert isinstance(decode_broker_message(response), BridgeRegistered)

    response = service.handle_control(
        peer,
        encode_broker_message(
            BridgeUnregister(session_id=first.session_id),
            generation=1,
            stream_id="bridge:astrbot:control",
            sequence=2,
            lease_id="registration",
        ),
    )
    rejected = decode_broker_message(response)
    assert isinstance(rejected, BridgeRejected)
    assert rejected.code == "invalid_session"


def test_registration_normalizes_tokens_and_rejects_identity_and_resource_conflicts() -> None:
    service = BrokerPeerService(instance_tokens={" one ": " one-token ", "two": "two-token"}, generation=1)
    first_manifest = BridgeManifest(
        bridge_id="one",
        access=BridgeAccess.LIMITED,
        action_resources=(ActionResourceDeclaration(kind="message.send", resource_prefix="bot:"),),
    )
    first_frame = encode_broker_message(
        BridgeRegister(bridge_id=" one ", instance_token=" one-token ", manifest=first_manifest),
        generation=1,
        stream_id="bridge:one:control",
        sequence=0,
        lease_id="registration",
    )
    first = decode_broker_message(service.handle_control(b"one-peer", first_frame))
    assert isinstance(first, BridgeRegistered)

    identity_bound = decode_broker_message(
        service.handle_control(
            b"one-peer",
            encode_broker_message(
                BridgeRegister(
                    bridge_id="two",
                    instance_token="two-token",
                    manifest=BridgeManifest(bridge_id="two", access=BridgeAccess.LIMITED),
                ),
                generation=1,
                stream_id="bridge:two:control",
                sequence=0,
                lease_id="registration",
            ),
        )
    )
    assert isinstance(identity_bound, BridgeRejected)
    assert identity_bound.code == "identity_bound"

    conflicting = decode_broker_message(
        service.handle_control(
            b"two-peer",
            encode_broker_message(
                BridgeRegister(
                    bridge_id="two",
                    instance_token="two-token",
                    manifest=BridgeManifest(
                        bridge_id="two",
                        access=BridgeAccess.LIMITED,
                        action_resources=(
                            ActionResourceDeclaration(kind="message.send", resource_prefix="bot:"),
                        ),
                    ),
                ),
                generation=1,
                stream_id="bridge:two:control",
                sequence=0,
                lease_id="registration",
            ),
        )
    )
    assert isinstance(conflicting, BridgeRejected)
    assert conflicting.code == "resource_conflict"


@pytest.mark.asyncio
async def test_zmq_registration_binds_lanes_and_releases_on_unregister() -> None:
    context = zmq.asyncio.Context()
    server = BrokerPeerServer(
        context=context,
        endpoint="inproc://broker-peer",
        generation=1,
        instance_tokens={"astrbot": "token"},
    )
    client = BridgeClient(
        context=context,
        endpoints=server.endpoints,
        generation=1,
        identity=b"astrbot-peer",
        manifest=_manifest(),
        instance_token="token",
    )
    try:
        register_task = asyncio.create_task(client.register())
        await server.serve_control_once()
        session_id = await register_task
        assert session_id == server.service.sessions[0].session_id

        business_frame = LyipFrame(
            1,
            1,
            LyipLane.BUSINESS,
            999,
            client.business_stream_id("events"),
            0,
            "lease",
            b"{}",
        )
        assert await client._dealer.offer(business_frame) is LyipOfferResult.ACCEPTED
        session, received = await server.receive_business_once()
        assert session.bridge_id == "astrbot"
        assert received.stream_id == client.business_stream_id("events")

        unregister_task = asyncio.create_task(client.unregister())
        await server.serve_control_once()
        await unregister_task
        assert server.service.sessions == ()
    finally:
        client.close()
        server.close()
        context.term()


@pytest.mark.asyncio
async def test_zmq_rejects_token_and_preserves_lyip_sequence_protection() -> None:
    context = zmq.asyncio.Context()
    server = BrokerPeerServer(
        context=context,
        endpoint="inproc://broker-peer-token",
        generation=1,
        instance_tokens={"astrbot": "token"},
    )
    client = BridgeClient(
        context=context,
        endpoints=server.endpoints,
        generation=1,
        identity=b"bad-token-peer",
        manifest=_manifest(),
        instance_token="wrong",
    )
    raw = ZmqLyipDealer(
        context=context,
        endpoints=server.endpoints,
        generation=1,
        identity=b"sequence-peer",
        business_hwm=2,
        control_hwm=2,
    )
    try:
        register_task = asyncio.create_task(client.register())
        await server.serve_control_once()
        with pytest.raises(BridgeRegistrationError, match="invalid_token"):
            await register_task

        with pytest.raises(LyipError, match="expected 0"):
            await raw.offer(_register_frame(sequence=1))
    finally:
        raw.close()
        client.close()
        server.close()
        context.term()
