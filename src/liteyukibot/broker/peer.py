"""Peer registration and lane-identity binding for the broker migration."""

from __future__ import annotations

import hmac
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

import zmq.asyncio

from ..lyip import LyipError, LyipFrame, LyipLane, LyipOfferResult, ZmqLyipDealer, ZmqLyipRouter
from .protocol import (
    BridgeManifest,
    BridgeRegister,
    BridgeRegistered,
    BridgeRejected,
    BridgeUnregister,
    BridgeUnregistered,
    BrokerWireError,
    BrokerWireMessage,
    decode_broker_message,
    encode_broker_message,
)

if TYPE_CHECKING:
    from .business import BrokerBusinessMessage
    from .routing import (
        ActionRequest,
        ActionResult,
        BrokerEvent,
        BrokerLedger,
        EventAccepted,
        EventCompleted,
        EventIngress,
        EventMessage,
        RoutedAction,
    )


class BridgeRegistrationError(LyipError):
    """Raised when a bridge has not established a valid broker session."""


@dataclass(frozen=True, slots=True)
class BridgeSession:
    """Broker-owned identity for a registered bridge peer."""

    bridge_id: str
    session_id: str
    manifest: BridgeManifest
    peer_identity: bytes


@dataclass(frozen=True, slots=True)
class BusinessDispatch:
    """One broker-originated business message directed to an authenticated bridge."""

    target: BridgeSession
    message: BrokerBusinessMessage


class BrokerPeerService:
    """Owns authenticated registrations independently of framework runtimes."""

    def __init__(
        self,
        *,
        instance_tokens: Mapping[str, str],
        generation: int,
        active_capacity: int = 1024,
        terminal_capacity: int = 16384,
        terminal_ttl_seconds: float = 3600.0,
        delivery_timeout_seconds: float = 30.0,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        if generation < 1:
            raise ValueError("broker LYIP generation must be positive")
        self.generation = generation
        self._instance_tokens = {bridge_id.strip(): token.strip() for bridge_id, token in instance_tokens.items()}
        if not self._instance_tokens or any(
            not bridge_id or not token.strip() for bridge_id, token in self._instance_tokens.items()
        ):
            raise ValueError("broker instance tokens must have non-empty bridge IDs and tokens")
        self._sessions_by_bridge: dict[str, BridgeSession] = {}
        self._sessions_by_identity: dict[bytes, BridgeSession] = {}
        self._reply_sequences: dict[bytes, int] = {}
        from .routing import BrokerLedger

        self.ledger: BrokerLedger
        if monotonic is None:
            self.ledger = BrokerLedger(
                active_capacity=active_capacity,
                terminal_capacity=terminal_capacity,
                terminal_ttl_seconds=terminal_ttl_seconds,
                delivery_timeout_seconds=delivery_timeout_seconds,
            )
        else:
            self.ledger = BrokerLedger(
                active_capacity=active_capacity,
                terminal_capacity=terminal_capacity,
                terminal_ttl_seconds=terminal_ttl_seconds,
                delivery_timeout_seconds=delivery_timeout_seconds,
                monotonic=monotonic,
            )

    @property
    def sessions(self) -> tuple[BridgeSession, ...]:
        return tuple(self._sessions_by_bridge.values())

    def handle_control(self, peer_identity: bytes, frame: LyipFrame) -> LyipFrame:
        """Handle one control frame and return a deterministic v6 acknowledgement."""

        if frame.generation != self.generation:
            return self._reply(
                peer_identity,
                frame,
                BridgeRejected(code="stale_generation", message="broker LYIP generation does not match"),
            )
        try:
            message = decode_broker_message(frame)
        except BrokerWireError as error:
            return self._reply(peer_identity, frame, BridgeRejected(code="malformed", message=str(error)))

        if isinstance(message, BridgeRegister):
            return self._register(peer_identity, frame, message)
        if isinstance(message, BridgeUnregister):
            return self._unregister(peer_identity, frame, message)
        return self._reply(
            peer_identity,
            frame,
            BridgeRejected(code="unexpected_message", message="bridge sent a broker-only response message"),
        )

    def require_business_peer(self, peer_identity: bytes, frame: LyipFrame) -> BridgeSession:
        """Validate identity plus an opaque session-bound stream before B5 delivery work."""

        if frame.lane is not LyipLane.BUSINESS:
            raise BridgeRegistrationError("broker business admission requires the business lane")
        session = self._sessions_by_identity.get(peer_identity)
        if session is None:
            raise BridgeRegistrationError("broker rejected business frame from an unregistered peer")
        prefix = f"bridge:{session.bridge_id}:{session.session_id}:"
        if not frame.stream_id.startswith(prefix):
            raise BridgeRegistrationError("broker rejected business frame without the registered session binding")
        return session

    def disconnect(self, peer_identity: bytes) -> BridgeSession | None:
        """Terminalize a known peer when a host deliberately disconnects or goes stale."""

        session = self._sessions_by_identity.pop(peer_identity, None)
        if session is not None:
            self._sessions_by_bridge.pop(session.bridge_id, None)
            self.ledger.disconnect_bridge(session.bridge_id)
        self._reply_sequences.pop(peer_identity, None)
        return session

    def admit_event(self, peer_identity: bytes, ingress: EventIngress) -> BrokerEvent:
        """Admit one decoded event from a registered business peer."""

        session = self._sessions_by_identity.get(peer_identity)
        if session is None:
            raise BridgeRegistrationError("broker rejected event from an unregistered peer")
        return self.ledger.admit_event(session, ingress, self.sessions)

    def event_subscribers(self, event: BrokerEvent) -> tuple[BridgeSession, ...]:
        """Return the currently registered bridges allowed to receive an admitted event."""

        return self.ledger.event_subscribers(event, self.sessions)

    def route_action(self, peer_identity: bytes, action: ActionRequest) -> RoutedAction:
        """Route one decoded portable action to its currently registered target."""

        session = self._sessions_by_identity.get(peer_identity)
        if session is None:
            raise BridgeRegistrationError("broker rejected action from an unregistered peer")
        return self.ledger.route_action(session, action, self.sessions)

    def handle_business(self, peer_identity: bytes, frame: LyipFrame) -> tuple[BusinessDispatch, ...]:
        """Apply one authenticated business message and return its direct deliveries."""

        from .business import decode_business_message
        from .routing import (
            ActionRequest,
            ActionResult,
            BrokerAdmissionError,
            EventAccepted,
            EventCompleted,
            EventIngress,
            EventMessage,
        )

        session = self.require_business_peer(peer_identity, frame)
        message = decode_business_message(frame)
        if isinstance(message, EventIngress):
            event = self.ledger.admit_event(session, message, self.sessions)
            return tuple(
                BusinessDispatch(
                    target=self._session_for_delivery(delivery.target_bridge_id),
                    message=EventMessage(
                        delivery_id=delivery.delivery_id,
                        lease_id=delivery.lease_id,
                        lease_ttl_ms=delivery.lease_ttl_ms,
                        attempt=delivery.attempt,
                        event=event,
                    ),
                )
                for delivery in self.ledger.offered_deliveries(event.kernel_event_id)
            )
        if isinstance(message, EventAccepted):
            self._require_frame_lease(frame, message.lease_id)
            self.ledger.accept_delivery(session, message.delivery_id, message.lease_id)
            self.ledger.activate_delivery(session, message.delivery_id, message.lease_id)
            return ()
        if isinstance(message, EventCompleted):
            self._require_frame_lease(frame, message.lease_id)
            _completed, next_offer = self.ledger.complete_delivery_with_next_offer(
                session,
                message.delivery_id,
                message.lease_id,
                success=message.success,
                failure_reason=message.failure_reason,
            )
            if next_offer is None:
                return ()
            event, delivery = next_offer
            return (
                BusinessDispatch(
                    target=self._session_for_delivery(delivery.target_bridge_id),
                    message=EventMessage(
                        delivery_id=delivery.delivery_id,
                        lease_id=delivery.lease_id,
                        lease_ttl_ms=delivery.lease_ttl_ms,
                        attempt=delivery.attempt,
                        event=event,
                    ),
                ),
            )
        if isinstance(message, ActionRequest):
            if message.action_id is not None:
                raise BrokerAdmissionError("unexpected_action_id", "bridges must not assign action IDs")
            self._require_frame_lease(frame, message.lease_id)
            routed = self.ledger.route_action(session, message, self.sessions)
            if routed.replayed:
                result = self.ledger.action_result(routed.action_id, session)
                if result is None:
                    return ()
                return (BusinessDispatch(target=routed.origin, message=result),)
            return (
                BusinessDispatch(
                    target=routed.target,
                    message=message.model_copy(update={"action_id": routed.action_id}),
                ),
            )
        if isinstance(message, ActionResult):
            routed = self.ledger.action_route(message.action_id)
            result = self.ledger.complete_action(
                session,
                message.action_id,
                success=message.success,
                payload=message.payload,
            )
            return (BusinessDispatch(target=routed.origin, message=result),)
        if isinstance(message, EventMessage):
            raise BrokerAdmissionError("unexpected_message", "bridges must not send broker event deliveries")
        raise BrokerAdmissionError("unexpected_message", "broker does not accept this business message from a bridge")

    def _session_for_delivery(self, bridge_id: str) -> BridgeSession:
        from .routing import BrokerAdmissionError

        session = self._sessions_by_bridge.get(bridge_id)
        if session is None:
            raise BrokerAdmissionError("delivery_target_missing", "delivery target is no longer registered")
        return session

    @staticmethod
    def _require_frame_lease(frame: LyipFrame, lease_id: str) -> None:
        from .routing import BrokerAdmissionError

        if not hmac.compare_digest(frame.lease_id, lease_id):
            raise BrokerAdmissionError("invalid_lease", "business frame lease does not match its delivery lease")

    def _register(self, peer_identity: bytes, frame: LyipFrame, message: BridgeRegister) -> LyipFrame:
        expected_token = self._instance_tokens.get(message.bridge_id)
        if expected_token is None:
            return self._reply(
                peer_identity,
                frame,
                BridgeRejected(code="unknown_bridge", message="bridge is not configured"),
            )
        if not hmac.compare_digest(expected_token, message.instance_token):
            return self._reply(
                peer_identity,
                frame,
                BridgeRejected(code="invalid_token", message="instance token is invalid"),
            )
        if message.bridge_id in self._sessions_by_bridge:
            return self._reply(
                peer_identity,
                frame,
                BridgeRejected(code="already_registered", message="bridge already has a live session"),
            )
        existing = self._sessions_by_identity.get(peer_identity)
        if existing is not None:
            return self._reply(
                peer_identity,
                frame,
                BridgeRejected(code="identity_bound", message="peer identity already belongs to another bridge"),
            )
        for current in self._sessions_by_bridge.values():
            if current.manifest.access is not message.manifest.access:
                continue
            current_resources = {
                (resource.kind, resource.resource_prefix) for resource in current.manifest.action_resources
            }
            requested_resources = {
                (resource.kind, resource.resource_prefix) for resource in message.manifest.action_resources
            }
            if current_resources & requested_resources:
                return self._reply(
                    peer_identity,
                    frame,
                    BridgeRejected(
                        code="resource_conflict",
                        message="an equal access-class bridge already owns this action resource",
                    ),
                )

        session = BridgeSession(
            bridge_id=message.bridge_id,
            session_id=secrets.token_urlsafe(32),
            manifest=message.manifest,
            peer_identity=peer_identity,
        )
        self._sessions_by_bridge[session.bridge_id] = session
        self._sessions_by_identity[peer_identity] = session
        return self._reply(peer_identity, frame, BridgeRegistered(session_id=session.session_id))

    def _unregister(self, peer_identity: bytes, frame: LyipFrame, message: BridgeUnregister) -> LyipFrame:
        session = self._sessions_by_identity.get(peer_identity)
        if session is None:
            return self._reply(
                peer_identity,
                frame,
                BridgeRejected(code="not_registered", message="peer has no live bridge session"),
            )
        if not hmac.compare_digest(session.session_id, message.session_id):
            return self._reply(
                peer_identity,
                frame,
                BridgeRejected(code="invalid_session", message="session identity is invalid"),
            )
        reply = self._reply(peer_identity, frame, BridgeUnregistered(session_id=session.session_id))
        self.disconnect(peer_identity)
        return reply

    def _reply(self, peer_identity: bytes, incoming: LyipFrame, message: BrokerWireMessage) -> LyipFrame:
        sequence = self._reply_sequences.get(peer_identity, 0)
        self._reply_sequences[peer_identity] = sequence + 1
        return encode_broker_message(
            message,
            generation=self.generation,
            stream_id="broker:control",
            sequence=sequence,
            lease_id=incoming.lease_id,
        )


class BrokerPeerServer:
    """Host-initialized ZMQ endpoint for registered broker peers and business traffic."""

    def __init__(
        self,
        *,
        context: zmq.asyncio.Context,
        endpoint: str,
        generation: int,
        instance_tokens: Mapping[str, str],
        business_hwm: int = 100,
        control_hwm: int = 100,
        active_capacity: int = 1024,
        terminal_capacity: int = 16384,
        terminal_ttl_seconds: float = 3600.0,
        delivery_timeout_seconds: float = 30.0,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self.router = ZmqLyipRouter(
            context=context,
            endpoint=endpoint,
            generation=generation,
            business_hwm=business_hwm,
            control_hwm=control_hwm,
        )
        self.service = BrokerPeerService(
            instance_tokens=instance_tokens,
            generation=generation,
            active_capacity=active_capacity,
            terminal_capacity=terminal_capacity,
            terminal_ttl_seconds=terminal_ttl_seconds,
            delivery_timeout_seconds=delivery_timeout_seconds,
            monotonic=monotonic,
        )
        self._business_sequences: dict[tuple[bytes, str], int] = {}

    @property
    def endpoints(self) -> dict[LyipLane, str]:
        return self.router.endpoints

    async def serve_control_once(self) -> None:
        peer_identity, frame = await self.router.receive(LyipLane.CONTROL)
        reply = self.service.handle_control(peer_identity, frame)
        if await self.router.offer(peer_identity, reply) is not LyipOfferResult.ACCEPTED:
            raise BridgeRegistrationError("broker control acknowledgement could not be queued")
        if isinstance(decode_broker_message(reply), BridgeUnregistered):
            self.router.disconnect(peer_identity)
            self._business_sequences = {
                key: sequence for key, sequence in self._business_sequences.items() if key[0] != peer_identity
            }

    async def receive_business_once(self) -> tuple[BridgeSession, LyipFrame]:
        peer_identity, frame = await self.router.receive(LyipLane.BUSINESS)
        return self.service.require_business_peer(peer_identity, frame), frame

    async def serve_business_once(self) -> tuple[BridgeSession, BrokerBusinessMessage] | None:
        """Receive one bridge message, apply its lifecycle transition, and send direct outputs."""

        from .business import BrokerBusinessWireError, decode_business_message
        from .routing import BrokerAdmissionError

        peer_identity, frame = await self.router.receive(LyipLane.BUSINESS)
        try:
            session = self.service.require_business_peer(peer_identity, frame)
            message = decode_business_message(frame)
            dispatches = self.service.handle_business(peer_identity, frame)
        except (BrokerBusinessWireError, BrokerAdmissionError):
            return None
        for dispatch in dispatches:
            await self.send_business(dispatch.target, dispatch.message)
        return session, message

    async def send_business(self, target: BridgeSession, message: BrokerBusinessMessage) -> None:
        """Send one catalog message on a target's registered session-bound business stream."""

        from .business import encode_business_message
        from .routing import EventMessage

        suffix = "delivery" if isinstance(message, EventMessage) else "action"
        stream_id = f"bridge:{target.bridge_id}:{target.session_id}:{suffix}"
        sequence_key = (target.peer_identity, stream_id)
        sequence = self._business_sequences.get(sequence_key, 0)
        frame = encode_business_message(
            message,
            generation=self.service.generation,
            stream_id=stream_id,
            sequence=sequence,
            lease_id=message.lease_id if isinstance(message, EventMessage) else "broker-business",
        )
        if await self.router.offer(target.peer_identity, frame) is not LyipOfferResult.ACCEPTED:
            raise BridgeRegistrationError("broker business delivery could not be queued")
        self._business_sequences[sequence_key] = sequence + 1

    def close(self) -> None:
        self.router.close()


class BridgeClient:
    """Host-initialized bridge registration client with no process bootstrap path."""

    def __init__(
        self,
        *,
        context: zmq.asyncio.Context,
        endpoints: Mapping[LyipLane, str],
        generation: int,
        identity: bytes,
        manifest: BridgeManifest,
        instance_token: str,
        business_hwm: int = 100,
        control_hwm: int = 100,
    ) -> None:
        if not identity:
            raise ValueError("bridge peer identity must be non-empty")
        if not instance_token.strip():
            raise ValueError("bridge instance token must be non-empty")
        self.manifest = manifest
        self._instance_token = instance_token.strip()
        self._generation = generation
        self._dealer = ZmqLyipDealer(
            context=context,
            endpoints=dict(endpoints),
            generation=generation,
            identity=identity,
            business_hwm=business_hwm,
            control_hwm=control_hwm,
        )
        self._control_sequence = 0
        self._business_sequences: dict[str, int] = {}
        self._delivery_leases: dict[str, str] = {}
        self.session_id: str | None = None

    async def register(self) -> str:
        if self.session_id is not None:
            raise BridgeRegistrationError("bridge is already registered")
        response = await self._request(
            BridgeRegister(
                bridge_id=self.manifest.bridge_id,
                instance_token=self._instance_token,
                manifest=self.manifest,
            )
        )
        if isinstance(response, BridgeRejected):
            raise BridgeRegistrationError(f"bridge registration rejected: {response.code}")
        if not isinstance(response, BridgeRegistered):
            raise BridgeRegistrationError("broker returned an unexpected registration response")
        self.session_id = response.session_id
        return response.session_id

    async def unregister(self) -> None:
        if self.session_id is None:
            raise BridgeRegistrationError("bridge is not registered")
        response = await self._request(BridgeUnregister(session_id=self.session_id))
        if isinstance(response, BridgeRejected):
            raise BridgeRegistrationError(f"bridge unregistration rejected: {response.code}")
        if not isinstance(response, BridgeUnregistered) or response.session_id != self.session_id:
            raise BridgeRegistrationError("broker returned an unexpected unregistration response")
        self.session_id = None

    def close(self) -> None:
        self._dealer.close()

    def business_stream_id(self, suffix: str) -> str:
        """Build the session-bound stream identifier required for business admission."""

        if self.session_id is None:
            raise BridgeRegistrationError("bridge must register before creating a business stream")
        normalized = suffix.strip()
        if not normalized:
            raise ValueError("business stream suffix must be non-empty")
        return f"bridge:{self.manifest.bridge_id}:{self.session_id}:{normalized}"

    async def send_event_ingress(self, message: EventIngress) -> None:
        """Send one bridge-originated event without a cross-process deadline."""

        await self._send_business(message, suffix="ingress", lease_id="bridge-business")

    async def send_event_accepted(self, message: EventAccepted) -> None:
        self._require_delivery_lease(message.delivery_id, message.lease_id)
        await self._send_business(message, suffix="delivery", lease_id=message.lease_id)

    async def send_event_completed(self, message: EventCompleted) -> None:
        self._require_delivery_lease(message.delivery_id, message.lease_id)
        await self._send_business(message, suffix="delivery", lease_id=message.lease_id)
        self._delivery_leases.pop(message.delivery_id, None)

    async def send_action_request(self, message: ActionRequest) -> None:
        if message.action_id is not None:
            raise BridgeRegistrationError("bridge action requests must not include a broker action ID")
        self._require_delivery_lease(message.delivery_id, message.lease_id)
        await self._send_business(message, suffix="action", lease_id=message.lease_id)

    async def send_action_result(self, message: ActionResult) -> None:
        await self._send_business(message, suffix="action", lease_id="bridge-business")

    async def receive_business(self) -> BrokerBusinessMessage:
        """Receive one broker business message and bind offered leases to this live session."""

        from .business import decode_business_message
        from .routing import EventMessage

        frame = await self._dealer.receive(LyipLane.BUSINESS)
        if self.session_id is None:
            raise BridgeRegistrationError("bridge must register before receiving business traffic")
        expected_prefix = f"bridge:{self.manifest.bridge_id}:{self.session_id}:"
        if not frame.stream_id.startswith(expected_prefix):
            raise BridgeRegistrationError("broker business message is not bound to this bridge session")
        message = decode_business_message(frame)
        if isinstance(message, EventMessage):
            if not hmac.compare_digest(frame.lease_id, message.lease_id):
                raise BridgeRegistrationError("broker event delivery frame lease does not match payload lease")
            self._delivery_leases[message.delivery_id] = message.lease_id
        return message

    async def receive_event_message(self) -> EventMessage:
        from .routing import EventMessage

        message = await self.receive_business()
        if not isinstance(message, EventMessage):
            raise BridgeRegistrationError("broker sent a non-event message while an event delivery was expected")
        return message

    async def receive_action_request(self) -> ActionRequest:
        from .routing import ActionRequest

        message = await self.receive_business()
        if not isinstance(message, ActionRequest) or message.action_id is None:
            raise BridgeRegistrationError("broker sent a non-action request while an action request was expected")
        return message

    async def receive_action_result(self) -> ActionResult:
        from .routing import ActionResult

        message = await self.receive_business()
        if not isinstance(message, ActionResult):
            raise BridgeRegistrationError("broker sent a non-action result while an action result was expected")
        return message

    async def _send_business(self, message: BrokerBusinessMessage, *, suffix: str, lease_id: str) -> None:
        from .business import encode_business_message

        stream_id = self.business_stream_id(suffix)
        sequence = self._business_sequences.get(stream_id, 0)
        frame = encode_business_message(
            message,
            generation=self._generation,
            stream_id=stream_id,
            sequence=sequence,
            lease_id=lease_id,
        )
        if await self._dealer.offer(frame) is not LyipOfferResult.ACCEPTED:
            raise BridgeRegistrationError("bridge business message could not be queued")
        self._business_sequences[stream_id] = sequence + 1

    def _require_delivery_lease(self, delivery_id: str, lease_id: str) -> None:
        current = self._delivery_leases.get(delivery_id)
        if current is None or not hmac.compare_digest(current, lease_id):
            raise BridgeRegistrationError("business message does not carry a current broker delivery lease")

    async def _request(self, message: BridgeRegister | BridgeUnregister) -> BrokerWireMessage:
        frame = encode_broker_message(
            message,
            generation=self._generation,
            stream_id=f"bridge:{self.manifest.bridge_id}:control",
            sequence=self._control_sequence,
            lease_id="bridge-registration",
        )
        if await self._dealer.offer(frame) is not LyipOfferResult.ACCEPTED:
            raise BridgeRegistrationError("bridge control request could not be queued")
        self._control_sequence += 1
        return decode_broker_message(await self._dealer.receive(LyipLane.CONTROL))
