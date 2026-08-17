"""Read-only, redacted broker diagnostics over the existing LYIP control lane."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
from collections.abc import Mapping
from typing import Final
from urllib.parse import urlsplit, urlunsplit

import zmq.asyncio

from ..lyip import LyipLane, LyipOfferResult, ZmqLyipDealer
from .protocol import (
    BridgeRejected,
    BrokerDiagnosticsDetail,
    BrokerDiagnosticsDetailResult,
    BrokerDiagnosticsEventRow,
    BrokerDiagnosticsList,
    BrokerDiagnosticsListResult,
    BrokerDiagnosticsStatus,
    BrokerDiagnosticsStatusResult,
    BrokerDiagnosticsTransition,
    BrokerWireMessage,
    decode_broker_message,
    encode_broker_message,
)
from .routing import BrokerAdmissionError, BrokerLedger, LedgerDiagnosticSnapshot

_CURSOR_CONTEXT: Final = b"liteyuki-broker-diagnostics-cursor-v1"
_PSEUDONYM_CONTEXT: Final = b"liteyuki-broker-diagnostics-pseudonym-v1"
_SAFE_FAILURE_CODES: Final = frozenset({"bridge_disconnected", "bridge_failed", "lease_expired"})


class BrokerDiagnosticsError(RuntimeError):
    """Raised when a local broker diagnostics request is rejected or malformed."""


class BrokerDiagnostics:
    """Project bounded ledger state without exposing broker business data."""

    def __init__(self, *, ledger: BrokerLedger, generation: int, token: str) -> None:
        normalized_token = token.strip()
        if not normalized_token:
            raise ValueError("broker diagnostics token must be non-empty")
        self._ledger = ledger
        self._generation = generation
        self._token = normalized_token
        self._pseudonym_key = hmac.new(
            normalized_token.encode("utf-8"), _PSEUDONYM_CONTEXT, hashlib.sha256
        ).digest()
        self._cursor_key = hmac.new(normalized_token.encode("utf-8"), _CURSOR_CONTEXT, hashlib.sha256).digest()

    def authenticate(self, token: str) -> bool:
        return hmac.compare_digest(self._token, token)

    def status(self, sessions: tuple[str, ...]) -> BrokerDiagnosticsStatusResult:
        terminal_events = self._ledger.terminal_count
        return BrokerDiagnosticsStatusResult(
            generation=self._generation,
            active_events=self._ledger.active_count,
            terminal_events=terminal_events,
            active_capacity=self._ledger.active_capacity,
            terminal_capacity=self._ledger.terminal_capacity,
            terminal_ttl_seconds=self._ledger.terminal_ttl_seconds,
            sessions=tuple(sorted(sessions)),
        )

    def list_events(self, request: BrokerDiagnosticsList) -> BrokerDiagnosticsListResult:
        rows = tuple(
            self._row(snapshot)
            for snapshot in self._ledger.diagnostic_snapshots()
            if self._matches(snapshot, request)
        )
        offset = self._decode_cursor(request.cursor)
        if offset > len(rows):
            raise ValueError("diagnostics cursor is outside the retained event range")
        page = rows[offset : offset + request.limit]
        next_offset = offset + len(page)
        return BrokerDiagnosticsListResult(
            events=page,
            next_cursor=self._encode_cursor(next_offset) if next_offset < len(rows) else None,
        )

    def detail(self, event_id: str) -> BrokerDiagnosticsDetailResult:
        snapshot = next(
            (item for item in self._ledger.diagnostic_snapshots() if item.event.kernel_event_id == event_id),
            None,
        )
        if snapshot is None:
            raise BrokerAdmissionError("unknown_event", "broker event is not retained")
        return BrokerDiagnosticsDetailResult(
            event=self._row(snapshot),
            transitions=tuple(
                BrokerDiagnosticsTransition(
                    order=transition.order,
                    elapsed_ms=transition.elapsed_ms,
                    kind=transition.kind,
                    target_bridge_id=transition.target_bridge_id,
                    state=transition.state.value if transition.state is not None else None,
                    success=transition.success,
                    failure_code=self._failure_code(transition.failure_reason),
                )
                for transition in snapshot.transitions
            ),
        )

    def _row(self, snapshot: LedgerDiagnosticSnapshot) -> BrokerDiagnosticsEventRow:
        failure_codes = tuple(
            sorted(
                {
                    failure_code
                    for delivery in snapshot.deliveries
                    if (failure_code := self._failure_code(delivery.failure_reason)) is not None
                }
            )
        )
        return BrokerDiagnosticsEventRow(
            event_id=snapshot.event.kernel_event_id,
            status=snapshot.status,
            topic=snapshot.event.topic,
            source_bridge_id=snapshot.event.source_bridge_id,
            source_event_id=self._pseudonymize(snapshot.event.source_event_id),
            ordering_key=self._pseudonymize(snapshot.event.ordering_key),
            delivery_count=len(snapshot.deliveries),
            failure_count=sum(delivery.failure_reason is not None for delivery in snapshot.deliveries),
            targets=tuple(sorted({delivery.target_bridge_id for delivery in snapshot.deliveries})),
            failure_codes=failure_codes,
        )

    def _matches(self, snapshot: LedgerDiagnosticSnapshot, request: BrokerDiagnosticsList) -> bool:
        row = self._row(snapshot)
        if request.state is not None and request.state != row.status and all(
            delivery.state.value != request.state for delivery in snapshot.deliveries
        ):
            return False
        if request.topic is not None and request.topic != row.topic:
            return False
        if request.source is not None and request.source != row.source_bridge_id:
            return False
        if request.target is not None and request.target not in row.targets:
            return False
        return request.failure is None or request.failure in row.failure_codes

    def _pseudonymize(self, value: str) -> str:
        digest = hmac.new(self._pseudonym_key, value.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"hmac:{digest[:24]}"

    def _encode_cursor(self, offset: int) -> str:
        value = str(offset).encode("ascii")
        signature = hmac.new(self._cursor_key, value, hashlib.sha256).digest()[:16]
        return base64.urlsafe_b64encode(value + b":" + signature).decode("ascii")

    def _decode_cursor(self, cursor: str | None) -> int:
        if cursor is None:
            return 0
        try:
            raw = base64.b64decode(cursor.encode("ascii"), altchars=b"-_", validate=True)
            value, signature = raw.split(b":", 1)
            expected = hmac.new(self._cursor_key, value, hashlib.sha256).digest()[:16]
            if not hmac.compare_digest(signature, expected):
                raise ValueError
            offset = int(value.decode("ascii"))
        except (UnicodeDecodeError, ValueError) as error:
            raise ValueError("diagnostics cursor is invalid") from error
        if offset < 0:
            raise ValueError("diagnostics cursor is invalid")
        return offset

    @staticmethod
    def _failure_code(reason: str | None) -> str | None:
        if reason is None:
            return None
        return reason if reason in _SAFE_FAILURE_CODES else "bridge_failed"


class BrokerDiagnosticsClient:
    """A host-owned local read-only client for the broker control socket."""

    def __init__(
        self,
        *,
        context: zmq.asyncio.Context,
        endpoints: Mapping[LyipLane, str],
        generation: int,
        identity: bytes,
        diagnostics_token: str,
        control_hwm: int = 100,
    ) -> None:
        token = diagnostics_token.strip()
        if not identity:
            raise ValueError("diagnostics peer identity must be non-empty")
        if not token:
            raise ValueError("broker diagnostics token must be non-empty")
        self._token = token
        self._generation = generation
        self._sequence = 0
        self._dealer = ZmqLyipDealer(
            context=context,
            endpoints=dict(endpoints),
            generation=generation,
            identity=identity,
            business_hwm=1,
            control_hwm=control_hwm,
        )
        self._lock = asyncio.Lock()

    @classmethod
    def from_broker_endpoint(
        cls,
        *,
        context: zmq.asyncio.Context,
        endpoint: str,
        generation: int,
        identity: bytes,
        diagnostics_token: str,
        control_hwm: int = 100,
    ) -> BrokerDiagnosticsClient:
        parsed = urlsplit(endpoint)
        if parsed.scheme != "tcp" or parsed.hostname is None or parsed.port is None or parsed.port >= 65_535:
            raise ValueError("broker diagnostics client requires a TCP endpoint with a free business port")
        host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
        endpoints = {
            LyipLane.CONTROL: endpoint,
            LyipLane.BUSINESS: urlunsplit((parsed.scheme, f"{host}:{parsed.port + 1}", "", "", "")),
        }
        return cls(
            context=context,
            endpoints=endpoints,
            generation=generation,
            identity=identity,
            diagnostics_token=diagnostics_token,
            control_hwm=control_hwm,
        )

    async def status(self) -> BrokerDiagnosticsStatusResult:
        response = await self._request(BrokerDiagnosticsStatus(token=self._token))
        if not isinstance(response, BrokerDiagnosticsStatusResult):
            raise BrokerDiagnosticsError("broker returned an unexpected diagnostics status response")
        return response

    async def list_events(
        self,
        *,
        cursor: str | None = None,
        limit: int = 100,
        state: str | None = None,
        topic: str | None = None,
        source: str | None = None,
        target: str | None = None,
        failure: str | None = None,
    ) -> BrokerDiagnosticsListResult:
        response = await self._request(
            BrokerDiagnosticsList(
                token=self._token,
                cursor=cursor,
                limit=limit,
                state=state,
                topic=topic,
                source=source,
                target=target,
                failure=failure,
            )
        )
        if not isinstance(response, BrokerDiagnosticsListResult):
            raise BrokerDiagnosticsError("broker returned an unexpected diagnostics list response")
        return response

    async def detail(self, event_id: str) -> BrokerDiagnosticsDetailResult:
        response = await self._request(BrokerDiagnosticsDetail(token=self._token, event_id=event_id))
        if not isinstance(response, BrokerDiagnosticsDetailResult):
            raise BrokerDiagnosticsError("broker returned an unexpected diagnostics detail response")
        return response

    def close(self) -> None:
        self._dealer.close()

    async def _request(
        self,
        message: BrokerDiagnosticsStatus | BrokerDiagnosticsList | BrokerDiagnosticsDetail,
    ) -> BrokerWireMessage:
        async with self._lock:
            frame = encode_broker_message(
                message,
                generation=self._generation,
                stream_id="broker:diagnostics:control",
                sequence=self._sequence,
                lease_id="broker-diagnostics",
            )
            if await self._dealer.offer(frame) is not LyipOfferResult.ACCEPTED:
                raise BrokerDiagnosticsError("broker diagnostics control message could not be queued")
            self._sequence += 1
            response = decode_broker_message(await self._dealer.receive(LyipLane.CONTROL))
        if isinstance(response, BridgeRejected):
            raise BrokerDiagnosticsError(f"broker diagnostics rejected: {response.code}")
        return response
