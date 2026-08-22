"""Peer registration and lane-identity binding for the broker migration."""

from __future__ import annotations

import asyncio
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
    BrokerDiagnosticsDetail,
    BrokerDiagnosticsList,
    BrokerDiagnosticsStatus,
    BrokerLifecycleDrain,
    BrokerLifecycleFreeze,
    BrokerLifecycleStatusResult,
    BrokerLifecycleUnfreeze,
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
        BridgeControlInvoke,
        BridgeControlResult,
        BrokerEvent,
        BrokerLedger,
        EventAccepted,
        EventCompleted,
        EventIngress,
        EventMessage,
        RoutedAction,
        RoutedTool,
        RuntimeApiInvoke,
        RuntimeApiResult,
        ToolInvoke,
        ToolResult,
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
        terminal_capacity: int = 4096,
        terminal_content_bytes_capacity: int = 16 * 1024 * 1024,
        terminal_ttl_seconds: float = 3600.0,
        delivery_timeout_seconds: float = 30.0,
        monotonic: Callable[[], float] | None = None,
        diagnostics_token: str | None = None,
        management_token: str | None = None,
    ) -> None:
        """Initialize authenticated peer sessions and their bounded routing ledger.

        Args:
            instance_tokens: Configured bridge ID to registration-secret mapping.
            generation: LYIP generation accepted by this broker instance.
            active_capacity: Maximum number of concurrently active event records.
            terminal_capacity: Maximum number of settled event records retained for inspection.
            terminal_content_bytes_capacity: Maximum serialized content retained across settled records.
            terminal_ttl_seconds: Maximum age of a settled record, in seconds.
            delivery_timeout_seconds: Lease duration offered to a target bridge, in seconds.
            monotonic: Optional clock override used by deterministic tests.
            diagnostics_token: Optional secret enabling the read-only diagnostics protocol.
            management_token: Optional secret enabling freeze, drain, and unfreeze operations.

        Returns:
            None.

        Security:
            Registration, diagnostics, and lifecycle management are separate authority domains. Their tokens
            may not be reused, and later comparisons use constant-time digest comparison. Diagnostic history is
            bounded independently by record count, content bytes, and TTL. See
            `docs/security/trusted-boundaries.md#broker-retention`.
        """
        if generation < 1:
            raise ValueError("broker LYIP generation must be positive")
        self.generation = generation
        self._instance_tokens = {bridge_id.strip(): token.strip() for bridge_id, token in instance_tokens.items()}
        if any(not bridge_id or not token.strip() for bridge_id, token in self._instance_tokens.items()):
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
                terminal_content_bytes_capacity=terminal_content_bytes_capacity,
                terminal_ttl_seconds=terminal_ttl_seconds,
                delivery_timeout_seconds=delivery_timeout_seconds,
            )
        else:
            self.ledger = BrokerLedger(
                active_capacity=active_capacity,
                terminal_capacity=terminal_capacity,
                terminal_content_bytes_capacity=terminal_content_bytes_capacity,
                terminal_ttl_seconds=terminal_ttl_seconds,
                delivery_timeout_seconds=delivery_timeout_seconds,
                monotonic=monotonic,
            )
        normalized_diagnostics_token = diagnostics_token.strip() if diagnostics_token is not None else None
        if normalized_diagnostics_token == "":
            raise ValueError("broker diagnostics token must be non-empty when configured")
        if normalized_diagnostics_token is not None and any(
            hmac.compare_digest(normalized_diagnostics_token, token) for token in self._instance_tokens.values()
        ):
            raise ValueError("broker diagnostics token must not reuse a bridge instance token")
        if normalized_diagnostics_token is None:
            self._diagnostics = None
        else:
            from .diagnostics import BrokerDiagnostics

            self._diagnostics = BrokerDiagnostics(
                ledger=self.ledger,
                generation=generation,
                token=normalized_diagnostics_token,
            )
        normalized_management_token = management_token.strip() if management_token is not None else None
        if normalized_management_token == "":
            raise ValueError("broker management token must be non-empty when configured")
        if normalized_management_token is not None and any(
            hmac.compare_digest(normalized_management_token, token) for token in self._instance_tokens.values()
        ):
            raise ValueError("broker management token must not reuse a bridge instance token")
        if normalized_management_token is not None and normalized_diagnostics_token is not None and hmac.compare_digest(
            normalized_management_token, normalized_diagnostics_token
        ):
            raise ValueError("broker management token must not reuse the diagnostics token")
        self._management_token = normalized_management_token
        self._admission_frozen = False
        self._freeze_reason: str | None = None

    @property
    def sessions(self) -> tuple[BridgeSession, ...]:
        """Return the broker peer service's sessions.

        Returns:
            The `tuple[BridgeSession, ...]` result produced by the operation.
        """
        return tuple(self._sessions_by_bridge.values())

    @property
    def admission_frozen(self) -> bool:
        """Return the broker peer service's admission frozen.

        Returns:
            Whether the requested condition is satisfied.
        """
        return self._admission_frozen

    @property
    def active_events(self) -> int:
        """Return the broker peer service's active events.

        Returns:
            The `int` result produced by the operation.
        """
        return self.ledger.active_count

    def handle_control(self, peer_identity: bytes, frame: LyipFrame) -> LyipFrame:
        """Handle one control frame and return a deterministic v7 acknowledgement.

        Args:
            peer_identity: Transport identity used to bind registration and reply sequencing.
            frame: Validated LYIP control frame containing one broker protocol message.

        Returns:
            A deterministic acknowledgement or redacted rejection frame.

        Security:
            Generation validation happens before decoding or dispatch. Each message family then applies its own
            registration, diagnostics, or management credential rather than inheriting authority from the socket.
        """

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
        if isinstance(message, (BrokerDiagnosticsStatus, BrokerDiagnosticsList, BrokerDiagnosticsDetail)):
            return self._diagnostics_reply(peer_identity, frame, message)
        if isinstance(message, (BrokerLifecycleFreeze, BrokerLifecycleDrain, BrokerLifecycleUnfreeze)):
            return self._lifecycle_reply(peer_identity, frame, message)
        return self._reply(
            peer_identity,
            frame,
            BridgeRejected(code="unexpected_message", message="bridge sent a broker-only response message"),
        )

    def _diagnostics_reply(
        self,
        peer_identity: bytes,
        frame: LyipFrame,
        message: BrokerDiagnosticsStatus | BrokerDiagnosticsList | BrokerDiagnosticsDetail,
    ) -> LyipFrame:
        """Authenticate and answer one read-only broker diagnostics request.

        Args:
            peer_identity: Transport identity used only to route the reply.
            frame: Incoming control frame whose stream metadata is mirrored in the reply.
            message: Status, list, or detail request carrying the diagnostics token.

        Returns:
            A diagnostics result or deliberately non-specific rejection frame.

        Notes:
            Request parsing errors and missing retained events are translated into stable public error codes;
            exception details are not reflected to the peer.

        Security:
            The diagnostics token is checked independently of bridge registration. Results omit business payloads
            and pseudonymize correlation keys, while still exposing operational metadata needed for support.
        """
        from .routing import BrokerAdmissionError

        if self._diagnostics is None:
            return self._reply(
                peer_identity,
                frame,
                BridgeRejected(code="diagnostics_disabled", message="broker diagnostics are not configured"),
            )
        if not self._diagnostics.authenticate(message.token):
            return self._reply(
                peer_identity,
                frame,
                BridgeRejected(code="invalid_diagnostics_token", message="diagnostics token is invalid"),
            )
        try:
            if isinstance(message, BrokerDiagnosticsStatus):
                response: BrokerWireMessage = self._diagnostics.status(
                    tuple(session.bridge_id for session in self.sessions)
                )
            elif isinstance(message, BrokerDiagnosticsList):
                response = self._diagnostics.list_events(message)
            else:
                response = self._diagnostics.detail(message.event_id)
        except ValueError:
            response = BridgeRejected(code="invalid_diagnostics_request", message="diagnostics request is invalid")
        except BrokerAdmissionError as error:
            response = BridgeRejected(code=error.code, message="diagnostics event is not retained")
        return self._reply(peer_identity, frame, response)

    def _lifecycle_reply(
        self,
        peer_identity: bytes,
        frame: LyipFrame,
        message: BrokerLifecycleFreeze | BrokerLifecycleDrain | BrokerLifecycleUnfreeze,
    ) -> LyipFrame:
        """Authorize and apply a broker freeze, drain, or unfreeze request.

        Args:
            peer_identity: Transport identity used only to route the reply.
            frame: Incoming control frame whose stream metadata is mirrored in the reply.
            message: Lifecycle command carrying the management token.

        Returns:
            Current lifecycle state or a stable rejection frame.

        Notes:
            Freeze prevents new admissions; drain reports outstanding work but does not terminate peers.

        Security:
            Lifecycle operations can deny new work and are therefore protected by a dedicated management token
            compared in constant time. This authority is intentionally unavailable when no token is configured.
        """
        if self._management_token is None:
            return self._reply(
                peer_identity,
                frame,
                BridgeRejected(code="lifecycle_disabled", message="broker lifecycle management is not configured"),
            )
        if not hmac.compare_digest(self._management_token, message.token):
            return self._reply(
                peer_identity,
                frame,
                BridgeRejected(code="invalid_management_token", message="broker management token is invalid"),
            )
        if isinstance(message, BrokerLifecycleFreeze):
            self._admission_frozen = True
            self._freeze_reason = message.reason
        elif isinstance(message, BrokerLifecycleUnfreeze):
            self._admission_frozen = False
            self._freeze_reason = None
        response = BrokerLifecycleStatusResult(
            frozen=self._admission_frozen,
            reason=self._freeze_reason,
            active_events=self.ledger.active_count,
            sessions=tuple(sorted(session.bridge_id for session in self.sessions)),
        )
        return self._reply(peer_identity, frame, response)

    def require_business_peer(self, peer_identity: bytes, frame: LyipFrame) -> BridgeSession:
        """Validate identity plus an opaque session-bound stream before B5 delivery work.

        Args:
            peer_identity: The peer identity value used by the operation.
            frame: The frame value used by the operation.

        Returns:
            The requested `BridgeSession` value.
        """

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
        """Terminalize a known peer when a host deliberately disconnects or goes stale.

        Args:
            peer_identity: The peer identity value used by the operation.

        Returns:
            The `BridgeSession | None` result produced by the operation.
        """

        session = self._sessions_by_identity.pop(peer_identity, None)
        if session is not None:
            self._sessions_by_bridge.pop(session.bridge_id, None)
            self.ledger.disconnect_bridge(session.bridge_id)
        self._reply_sequences.pop(peer_identity, None)
        return session

    def admit_event(self, peer_identity: bytes, ingress: EventIngress) -> BrokerEvent:
        """Admit one decoded event from a registered business peer.

        Args:
            peer_identity: The peer identity value used by the operation.
            ingress: The ingress value used by the operation.

        Returns:
            The `BrokerEvent` result produced by the operation.
        """

        session = self._sessions_by_identity.get(peer_identity)
        if session is None:
            raise BridgeRegistrationError("broker rejected event from an unregistered peer")
        if self._admission_frozen:
            from .routing import BrokerAdmissionError

            raise BrokerAdmissionError("admission_frozen", "broker admission is frozen for an instance update")
        return self.ledger.admit_event(session, ingress, self.sessions)

    def event_subscribers(self, event: BrokerEvent) -> tuple[BridgeSession, ...]:
        """Return the currently registered bridges allowed to receive an admitted event.

        Args:
            event: Event associated with the operation.

        Returns:
            The `tuple[BridgeSession, ...]` result produced by the operation.
        """

        return self.ledger.event_subscribers(event, self.sessions)

    def route_action(self, peer_identity: bytes, action: ActionRequest) -> RoutedAction:
        """Route one decoded portable action to its currently registered target.

        Args:
            peer_identity: The peer identity value used by the operation.
            action: Action request being processed.

        Returns:
            The `RoutedAction` result produced by the operation.
        """

        session = self._sessions_by_identity.get(peer_identity)
        if session is None:
            raise BridgeRegistrationError("broker rejected action from an unregistered peer")
        return self.ledger.route_action(session, action, self.sessions)

    def route_tool(self, peer_identity: bytes, request: ToolInvoke) -> RoutedTool:
        """Route tool.

        Args:
            peer_identity: The peer identity value used by the operation.
            request: Validated request object to process.

        Returns:
            The `RoutedTool` result produced by the operation.
        """
        session = self._sessions_by_identity.get(peer_identity)
        if session is None:
            raise BridgeRegistrationError("broker rejected Tool invocation from an unregistered peer")
        return self.ledger.route_tool(session, request, self.sessions)

    def handle_business(self, peer_identity: bytes, frame: LyipFrame) -> tuple[BusinessDispatch, ...]:
        """Apply one authenticated business message and return its direct deliveries.

        Args:
            peer_identity: Transport identity that must already own a live bridge session.
            frame: Business-lane LYIP frame to authenticate, decode, and route.

        Returns:
            Direct broker-to-bridge messages produced by the state transition.

        Security:
            The method binds the frame to an authenticated session before decoding business intent. Delivery-bound
            messages additionally require a constant-time lease match, and all ownership/replay checks remain in
            `BrokerLedger` rather than trusting caller-supplied identifiers.
        """

        from .business import decode_business_message
        from .routing import (
            ActionRequest,
            ActionResult,
            BridgeControlInvoke,
            BridgeControlResult,
            BrokerAdmissionError,
            EventAccepted,
            EventCompleted,
            EventIngress,
            EventMessage,
            RuntimeApiInvoke,
            RuntimeApiResult,
            ToolInvoke,
            ToolResult,
        )

        session = self.require_business_peer(peer_identity, frame)
        message = decode_business_message(frame)
        if isinstance(message, EventIngress):
            event = self.admit_event(peer_identity, message)
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
        if isinstance(message, ToolInvoke):
            if message.invocation_id is not None:
                raise BrokerAdmissionError("unexpected_tool_invocation_id", "bridges must not assign invocation IDs")
            self._require_frame_lease(frame, message.lease_id)
            tool_routed = self.ledger.route_tool(session, message, self.sessions)
            if tool_routed.replayed:
                tool_result = self.ledger.tool_result(tool_routed.invocation_id, session)
                if tool_result is None:
                    return ()
                return (BusinessDispatch(target=tool_routed.origin, message=tool_result),)
            return (
                BusinessDispatch(
                    target=tool_routed.target,
                    message=message.model_copy(update={"invocation_id": tool_routed.invocation_id}),
                ),
            )
        if isinstance(message, BridgeControlInvoke):
            if message.invocation_id is not None:
                raise BrokerAdmissionError(
                    "unexpected_control_invocation_id", "bridges must not assign control invocation IDs"
                )
            self._require_frame_lease(frame, message.lease_id)
            control_routed = self.ledger.route_control(session, message, self.sessions)
            if control_routed.replayed:
                control_result = self.ledger.control_result(control_routed.invocation_id, session)
                if control_result is None:
                    return ()
                return (BusinessDispatch(target=control_routed.origin, message=control_result),)
            return (
                BusinessDispatch(
                    target=control_routed.target,
                    message=message.model_copy(update={"invocation_id": control_routed.invocation_id}),
                ),
            )
        if isinstance(message, RuntimeApiInvoke):
            if message.invocation_id is not None:
                raise BrokerAdmissionError(
                    "unexpected_runtime_api_invocation_id",
                    "bridges must not assign runtime API invocation IDs",
                )
            self._require_frame_lease(frame, message.lease_id)
            runtime_api_routed = self.ledger.route_runtime_api(session, message, self.sessions)
            if runtime_api_routed.replayed:
                runtime_api_result = self.ledger.runtime_api_result(runtime_api_routed.invocation_id, session)
                if runtime_api_result is None:
                    return ()
                return (BusinessDispatch(target=runtime_api_routed.origin, message=runtime_api_result),)
            return (
                BusinessDispatch(
                    target=runtime_api_routed.target,
                    message=message.model_copy(update={"invocation_id": runtime_api_routed.invocation_id}),
                ),
            )
        if isinstance(message, ToolResult):
            tool_routed = self.ledger.tool_route(message.invocation_id)
            tool_result = self.ledger.complete_tool(
                session,
                message.invocation_id,
                success=message.success,
                result=message.result,
                error_code=message.error_code,
                error_details=message.error_details,
            )
            return (BusinessDispatch(target=tool_routed.origin, message=tool_result),)
        if isinstance(message, BridgeControlResult):
            control_routed = self.ledger.control_route(message.invocation_id)
            control_result = self.ledger.complete_control(
                session,
                message.invocation_id,
                success=message.success,
                result=message.result,
                error_code=message.error_code,
                error_details=message.error_details,
            )
            return (BusinessDispatch(target=control_routed.origin, message=control_result),)
        if isinstance(message, RuntimeApiResult):
            runtime_api_routed = self.ledger.runtime_api_route(message.invocation_id)
            runtime_api_result = self.ledger.complete_runtime_api(
                session,
                message.invocation_id,
                success=message.success,
                result=message.result,
                error_code=message.error_code,
                error_details=message.error_details,
            )
            return (BusinessDispatch(target=runtime_api_routed.origin, message=runtime_api_result),)
        if isinstance(message, EventMessage):
            raise BrokerAdmissionError("unexpected_message", "bridges must not send broker event deliveries")
        raise BrokerAdmissionError("unexpected_message", "broker does not accept this business message from a bridge")

    def _session_for_delivery(self, bridge_id: str) -> BridgeSession:
        """Implement the session for delivery operation for the broker peer service.

        Args:
            bridge_id: Stable identifier for the bridge.

        Returns:
            The `BridgeSession` result produced by the operation.

        Notes:
            Internal implementation detail for `BrokerPeerService._session_for_delivery`. It delegates to
            `get` while keeping intermediate state local to the owning operation.
        """
        from .routing import BrokerAdmissionError

        session = self._sessions_by_bridge.get(bridge_id)
        if session is None:
            raise BrokerAdmissionError("delivery_target_missing", "delivery target is no longer registered")
        return session

    @staticmethod
    def _require_frame_lease(frame: LyipFrame, lease_id: str) -> None:
        """Return frame lease, failing when it is unavailable.

        Args:
            frame: The frame value used by the operation.
            lease_id: Stable identifier for the lease.

        Returns:
            None.

        Notes:
            Internal implementation detail for `BrokerPeerService._require_frame_lease`. It delegates to
            `compare_digest` while keeping intermediate state local to the owning operation.
        """
        from .routing import BrokerAdmissionError

        if not hmac.compare_digest(frame.lease_id, lease_id):
            raise BrokerAdmissionError("invalid_lease", "business frame lease does not match its delivery lease")

    def _register(self, peer_identity: bytes, frame: LyipFrame, message: BridgeRegister) -> LyipFrame:
        """Authenticate a configured bridge and reserve its declared ownership surface.

        Args:
            peer_identity: Unique transport identity to bind to the new session.
            frame: Registration frame whose stream metadata is mirrored in the reply.
            message: Bridge identity, instance token, and capability manifest.

        Returns:
            A new opaque session identifier or a stable rejection frame.

        Notes:
            Tool IDs and controls are globally unique. Exact action resources may coexist only across different
            access classes; routing precedence then remains deterministic.

        Security:
            The configured instance token is compared in constant time before capability claims are accepted.
            Both bridge ID and transport identity are single-session bindings, preventing a second peer from
            inheriting an authenticated bridge's ownership declarations.
        """
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
            current_tools = {tool.id for tool in current.manifest.tools}
            requested_tools = {tool.id for tool in message.manifest.tools}
            if current_tools & requested_tools:
                return self._reply(
                    peer_identity,
                    frame,
                    BridgeRejected(code="tool_conflict", message="a live bridge already owns this Tool ID"),
                )
            if set(current.manifest.controls) & set(message.manifest.controls):
                return self._reply(
                    peer_identity,
                    frame,
                    BridgeRejected(code="control_conflict", message="a live bridge already owns this control"),
                )
            if current.manifest.access is not message.manifest.access:
                continue
            current_resources = {
                (resource.kind, resource.resource, resource.resource_prefix)
                for resource in current.manifest.action_resources
            }
            requested_resources = {
                (resource.kind, resource.resource, resource.resource_prefix)
                for resource in message.manifest.action_resources
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
        """Close the session bound to a peer after validating its opaque session ID.

        Args:
            peer_identity: Transport identity currently bound to the session.
            frame: Unregistration frame whose stream metadata is mirrored in the reply.
            message: Unregistration request carrying the issued session ID.

        Returns:
            Confirmation containing the closed session ID or a stable rejection frame.

        Notes:
            Disconnecting also releases routing ownership and fails outstanding deliveries targeting the bridge.

        Security:
            Both transport identity and constant-time session-ID validation are required; knowing only a bridge ID
            is insufficient to terminate another peer.
        """
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
        """Implement the reply operation for the broker peer service.

        Args:
            peer_identity: The peer identity value used by the operation.
            incoming: The incoming value used by the operation.
            message: Message content associated with the operation.

        Returns:
            The `LyipFrame` result produced by the operation.

        Notes:
            Internal implementation detail for `BrokerPeerService._reply`. It delegates to `get`,
            `encode_broker_message` while keeping intermediate state local to the owning operation.
        """
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
        terminal_capacity: int = 4096,
        terminal_content_bytes_capacity: int = 16 * 1024 * 1024,
        terminal_ttl_seconds: float = 3600.0,
        delivery_timeout_seconds: float = 30.0,
        monotonic: Callable[[], float] | None = None,
        diagnostics_token: str | None = None,
        management_token: str | None = None,
    ) -> None:
        """Initialize the broker peer server.

        Args:
            context: Runtime or authorization context for the operation.
            endpoint: Transport endpoint used for the connection.
            generation: Positive protocol or deployment generation.
            instance_tokens: The instance tokens value used by the operation.
            business_hwm: The business hwm value used by the operation.
            control_hwm: The control hwm value used by the operation.
            active_capacity: Maximum retained active count.
            terminal_capacity: Maximum retained terminal count.
            terminal_content_bytes_capacity: Maximum retained terminal content bytes count.
            terminal_ttl_seconds: Configured terminal ttl duration, in seconds.
            delivery_timeout_seconds: Configured delivery timeout duration, in seconds.
            monotonic: The monotonic value used by the operation.
            diagnostics_token: The diagnostics token value used by the operation.
            management_token: The management token value used by the operation.

        Returns:
            None.
        """
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
            terminal_content_bytes_capacity=terminal_content_bytes_capacity,
            terminal_ttl_seconds=terminal_ttl_seconds,
            delivery_timeout_seconds=delivery_timeout_seconds,
            monotonic=monotonic,
            diagnostics_token=diagnostics_token,
            management_token=management_token,
        )
        self._business_sequences: dict[tuple[bytes, str], int] = {}

    @property
    def endpoints(self) -> dict[LyipLane, str]:
        """Return the broker peer server's endpoints.

        Returns:
            The `dict[LyipLane, str]` result produced by the operation.
        """
        return self.router.endpoints

    async def serve_control_once(self) -> None:
        """Serve control once.

        Returns:
            None.
        """
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
        """Receive business once.

        Returns:
            The `tuple[BridgeSession, LyipFrame]` result produced by the operation.
        """
        peer_identity, frame = await self.router.receive(LyipLane.BUSINESS)
        return self.service.require_business_peer(peer_identity, frame), frame

    async def serve_business_once(self) -> tuple[BridgeSession, BrokerBusinessMessage] | None:
        """Receive one bridge message, apply its lifecycle transition, and send direct outputs.

        Returns:
            The `tuple[BridgeSession, BrokerBusinessMessage] | None` result produced by the operation.
        """

        from .business import BrokerBusinessWireError, decode_business_message
        from .routing import BrokerAdmissionError

        peer_identity, frame = await self.router.receive(LyipLane.BUSINESS)
        try:
            session = self.service.require_business_peer(peer_identity, frame)
            message = decode_business_message(frame)
            dispatches = self.service.handle_business(peer_identity, frame)
        except BrokerBusinessWireError, BrokerAdmissionError:
            return None
        for dispatch in dispatches:
            await self.send_business(dispatch.target, dispatch.message)
        return session, message

    async def send_business(self, target: BridgeSession, message: BrokerBusinessMessage) -> None:
        """Send one catalog message on a target's registered session-bound business stream.

        Args:
            target: Target value or location for the operation.
            message: Message content associated with the operation.

        Returns:
            None.
        """

        from .business import encode_business_message
        from .routing import (
            BridgeControlInvoke,
            BridgeControlResult,
            EventMessage,
            RuntimeApiInvoke,
            RuntimeApiResult,
            ToolInvoke,
            ToolResult,
        )

        if isinstance(message, EventMessage):
            suffix = "delivery"
        elif isinstance(message, (ToolInvoke, ToolResult)):
            suffix = "tool"
        elif isinstance(message, (BridgeControlInvoke, BridgeControlResult)):
            suffix = "control"
        elif isinstance(message, (RuntimeApiInvoke, RuntimeApiResult)):
            suffix = "runtime-api"
        else:
            suffix = "action"
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
        """Close the broker peer server and release its owned resources.

        Returns:
            None.
        """
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
        """Initialize the bridge client.

        Args:
            context: Runtime or authorization context for the operation.
            endpoints: The endpoints value used by the operation.
            generation: Positive protocol or deployment generation.
            identity: The identity value used by the operation.
            manifest: Validated manifest describing the component contract.
            instance_token: The instance token value used by the operation.
            business_hwm: The business hwm value used by the operation.
            control_hwm: The control hwm value used by the operation.

        Returns:
            None.
        """
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
        self._business_send_lock = asyncio.Lock()
        self._delivery_leases: dict[str, str] = {}
        self.session_id: str | None = None

    async def register(self) -> str:
        """Register the bridge client operation.

        Returns:
            The `str` result produced by the operation.
        """
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
        """Unregister the bridge client operation.

        Returns:
            None.
        """
        if self.session_id is None:
            raise BridgeRegistrationError("bridge is not registered")
        response = await self._request(BridgeUnregister(session_id=self.session_id))
        if isinstance(response, BridgeRejected):
            raise BridgeRegistrationError(f"bridge unregistration rejected: {response.code}")
        if not isinstance(response, BridgeUnregistered) or response.session_id != self.session_id:
            raise BridgeRegistrationError("broker returned an unexpected unregistration response")
        self.session_id = None

    def close(self) -> None:
        """Close the bridge client and release its owned resources.

        Returns:
            None.
        """
        self._dealer.close()

    def business_stream_id(self, suffix: str) -> str:
        """Build the session-bound stream identifier required for business admission.

        Args:
            suffix: The suffix value used by the operation.

        Returns:
            The `str` result produced by the operation.
        """

        if self.session_id is None:
            raise BridgeRegistrationError("bridge must register before creating a business stream")
        normalized = suffix.strip()
        if not normalized:
            raise ValueError("business stream suffix must be non-empty")
        return f"bridge:{self.manifest.bridge_id}:{self.session_id}:{normalized}"

    async def send_event_ingress(self, message: EventIngress) -> None:
        """Send one bridge-originated event without a cross-process deadline.

        Args:
            message: Message content associated with the operation.

        Returns:
            None.
        """

        await self._send_business(message, suffix="ingress", lease_id="bridge-business")

    async def send_event_accepted(self, message: EventAccepted) -> None:
        """Send event accepted.

        Args:
            message: Message content associated with the operation.

        Returns:
            None.
        """
        self._require_delivery_lease(message.delivery_id, message.lease_id)
        await self._send_business(message, suffix="delivery", lease_id=message.lease_id)

    async def send_event_completed(self, message: EventCompleted) -> None:
        """Send event completed.

        Args:
            message: Message content associated with the operation.

        Returns:
            None.
        """
        self._require_delivery_lease(message.delivery_id, message.lease_id)
        await self._send_business(message, suffix="delivery", lease_id=message.lease_id)
        self._delivery_leases.pop(message.delivery_id, None)

    async def send_action_request(self, message: ActionRequest) -> None:
        """Send action request.

        Args:
            message: Message content associated with the operation.

        Returns:
            None.
        """
        if message.action_id is not None:
            raise BridgeRegistrationError("bridge action requests must not include a broker action ID")
        self._require_delivery_lease(message.delivery_id, message.lease_id)
        await self._send_business(message, suffix="action", lease_id=message.lease_id)

    async def send_action_result(self, message: ActionResult) -> None:
        """Send action result.

        Args:
            message: Message content associated with the operation.

        Returns:
            None.
        """
        await self._send_business(message, suffix="action", lease_id="bridge-business")

    async def send_tool_invoke(self, message: ToolInvoke) -> None:
        """Send tool invoke.

        Args:
            message: Message content associated with the operation.

        Returns:
            None.
        """
        self._require_delivery_lease(message.delivery_id, message.lease_id)
        await self._send_business(message, suffix="tool", lease_id=message.lease_id)

    async def send_tool_result(self, message: ToolResult) -> None:
        """Send tool result.

        Args:
            message: Message content associated with the operation.

        Returns:
            None.
        """
        await self._send_business(message, suffix="tool", lease_id="bridge-business")

    async def send_control_invoke(self, message: BridgeControlInvoke) -> None:
        """Send control invoke.

        Args:
            message: Message content associated with the operation.

        Returns:
            None.
        """
        self._require_delivery_lease(message.delivery_id, message.lease_id)
        await self._send_business(message, suffix="control", lease_id=message.lease_id)

    async def send_control_result(self, message: BridgeControlResult) -> None:
        """Send control result.

        Args:
            message: Message content associated with the operation.

        Returns:
            None.
        """
        await self._send_business(message, suffix="control", lease_id="bridge-business")

    async def send_runtime_api_invoke(self, message: RuntimeApiInvoke) -> None:
        """Send runtime api invoke.

        Args:
            message: Message content associated with the operation.

        Returns:
            None.
        """
        self._require_delivery_lease(message.delivery_id, message.lease_id)
        await self._send_business(message, suffix="runtime-api", lease_id=message.lease_id)

    async def send_runtime_api_result(self, message: RuntimeApiResult) -> None:
        """Send runtime api result.

        Args:
            message: Message content associated with the operation.

        Returns:
            None.
        """
        await self._send_business(message, suffix="runtime-api", lease_id="bridge-business")

    async def receive_business(self) -> BrokerBusinessMessage:
        """Receive one broker business message and bind offered leases to this live session.

        Returns:
            The `BrokerBusinessMessage` result produced by the operation.
        """

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
        """Receive event message.

        Returns:
            The `EventMessage` result produced by the operation.
        """
        from .routing import EventMessage

        message = await self.receive_business()
        if not isinstance(message, EventMessage):
            raise BridgeRegistrationError("broker sent a non-event message while an event delivery was expected")
        return message

    async def receive_action_request(self) -> ActionRequest:
        """Receive action request.

        Returns:
            The `ActionRequest` result produced by the operation.
        """
        from .routing import ActionRequest

        message = await self.receive_business()
        if not isinstance(message, ActionRequest) or message.action_id is None:
            raise BridgeRegistrationError("broker sent a non-action request while an action request was expected")
        return message

    async def receive_action_result(self) -> ActionResult:
        """Receive action result.

        Returns:
            The `ActionResult` result produced by the operation.
        """
        from .routing import ActionResult

        message = await self.receive_business()
        if not isinstance(message, ActionResult):
            raise BridgeRegistrationError("broker sent a non-action result while an action result was expected")
        return message

    async def receive_tool_invoke(self) -> ToolInvoke:
        """Receive tool invoke.

        Returns:
            The `ToolInvoke` result produced by the operation.
        """
        from .routing import ToolInvoke

        message = await self.receive_business()
        if not isinstance(message, ToolInvoke) or message.invocation_id is None:
            raise BridgeRegistrationError("broker sent a non-Tool invocation while one was expected")
        return message

    async def receive_tool_result(self) -> ToolResult:
        """Receive tool result.

        Returns:
            The `ToolResult` result produced by the operation.
        """
        from .routing import ToolResult

        message = await self.receive_business()
        if not isinstance(message, ToolResult):
            raise BridgeRegistrationError("broker sent a non-Tool result while one was expected")
        return message

    async def receive_control_invoke(self) -> BridgeControlInvoke:
        """Receive control invoke.

        Returns:
            The `BridgeControlInvoke` result produced by the operation.
        """
        from .routing import BridgeControlInvoke

        message = await self.receive_business()
        if not isinstance(message, BridgeControlInvoke) or message.invocation_id is None:
            raise BridgeRegistrationError("broker sent a non-control invocation while one was expected")
        return message

    async def receive_control_result(self) -> BridgeControlResult:
        """Receive control result.

        Returns:
            The `BridgeControlResult` result produced by the operation.
        """
        from .routing import BridgeControlResult

        message = await self.receive_business()
        if not isinstance(message, BridgeControlResult):
            raise BridgeRegistrationError("broker sent a non-control result while one was expected")
        return message

    async def _send_business(self, message: BrokerBusinessMessage, *, suffix: str, lease_id: str) -> None:
        """Send business.

        Args:
            message: Message content associated with the operation.
            suffix: The suffix value used by the operation.
            lease_id: Stable identifier for the lease.

        Returns:
            None.

        Notes:
            Internal implementation detail for `BridgeClient._send_business`. It delegates to
            `business_stream_id`, `get`, `encode_business_message`, `offer` while keeping intermediate state
            local to the owning operation.
        """
        from .business import encode_business_message

        async with self._business_send_lock:
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
        """Return delivery lease, failing when it is unavailable.

        Args:
            delivery_id: Stable identifier for the delivery.
            lease_id: Stable identifier for the lease.

        Returns:
            None.

        Notes:
            Internal implementation detail for `BridgeClient._require_delivery_lease`. It delegates to
            `get`, `compare_digest` while keeping intermediate state local to the owning operation.
        """
        current = self._delivery_leases.get(delivery_id)
        if current is None or not hmac.compare_digest(current, lease_id):
            raise BridgeRegistrationError("business message does not carry a current broker delivery lease")

    async def _request(self, message: BridgeRegister | BridgeUnregister) -> BrokerWireMessage:
        """Request the bridge client operation.

        Args:
            message: Message content associated with the operation.

        Returns:
            The `BrokerWireMessage` result produced by the operation.

        Notes:
            Internal implementation detail for `BridgeClient._request`. It delegates to
            `encode_broker_message`, `offer`, `decode_broker_message`, `receive` while keeping intermediate
            state local to the owning operation.
        """
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
