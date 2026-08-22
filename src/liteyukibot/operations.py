"""Daemon-owned structured management operations and redacted audit storage."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import sqlite3
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4


class OperationError(RuntimeError):
    """Raised when the operation contract cannot be satisfied."""
    pass


class PrincipalKind(StrEnum):
    """Enumerate the supported principal kind values."""
    CLI_SESSION = "cli_session"
    WEB_SESSION = "web_session"
    RUNTIME = "runtime"
    PLUGIN = "plugin"
    SYSTEM = "system"


class OperationState(StrEnum):
    """Enumerate the supported operation state values."""
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"
    REJECTED = "rejected"


class OperationImpact(StrEnum):
    """The operator-visible consequence class for an operation."""

    NONE = "none"
    STANDARD = "standard"
    HIGH = "high"


class OperationConfirmation(StrEnum):
    """The confirmation evidence required before an operation can run."""

    NONE = "none"
    EXPLICIT = "explicit"
    TARGET = "target"


@dataclass(frozen=True, slots=True)
class ManagementPrincipal:
    """Represent the management principal contract."""
    kind: PrincipalKind
    subject: str
    authentication_origin: str
    expires_at: datetime | None
    capabilities: frozenset[str]

    def allows(self, capability: str, *, now: datetime | None = None) -> bool:
        """Determine whether the management principal operation is allowed.

        Args:
            capability: The capability value used by the operation.
            now: The now value used by the operation.

        Returns:
            Whether the requested condition is satisfied.
        """
        current = now or datetime.now(UTC)
        return (self.expires_at is None or self.expires_at > current) and capability in self.capabilities


@dataclass(frozen=True, slots=True)
class OperationDefinition:
    """Represent the operation definition contract."""
    name: str
    capability: str
    mutating: bool
    cancellable: bool = False
    api: str = "liteyuki.management"
    version: int = 1
    input_schema: Mapping[str, Any] = field(default_factory=lambda: {"type": "object"})
    impact: OperationImpact = OperationImpact.STANDARD
    confirmation: OperationConfirmation = OperationConfirmation.NONE
    target: str = "kernel"
    target_input_field: str | None = None

    def __post_init__(self) -> None:
        """Validate and normalize the operation definition after initialization.

        Returns:
            None.
        """
        if not self.name or self.name != self.name.strip():
            raise ValueError("operation name must be non-empty and trimmed")
        if not self.api or self.api != self.api.strip() or self.version < 1:
            raise ValueError("operation API metadata is invalid")
        if not self.capability or self.capability != self.capability.strip():
            raise ValueError("operation capability must be non-empty and trimmed")
        if not isinstance(self.input_schema, Mapping):
            raise ValueError("operation input schema must be a mapping")
        if not self.target or self.target != self.target.strip():
            raise ValueError("operation target metadata must be non-empty and trimmed")
        if self.target_input_field is not None and (
            not self.target_input_field or self.target_input_field != self.target_input_field.strip()
        ):
            raise ValueError("operation target input field must be non-empty and trimmed")

    @property
    def id(self) -> str:
        """Stable catalog identifier. ``name`` remains for beta CLI compatibility.

        Returns:
            The `str` result produced by the operation.
        """

        return self.name

    def catalog_entry(self) -> dict[str, Any]:
        """Return the JSON-safe metadata projected to management clients.

        Returns:
            The `dict[str, Any]` result produced by the operation.
        """

        return {
            "id": self.id,
            "api": self.api,
            "version": self.version,
            "input_schema": dict(self.input_schema),
            "impact": self.impact.value,
            "capability": self.capability,
            "confirmation": self.confirmation.value,
            "target": self.target,
            "target_input_field": self.target_input_field,
            "mutating": self.mutating,
            "cancellable": self.cancellable,
        }


@dataclass(frozen=True, slots=True)
class OperationRequest:
    """Represent the validated operation request contract."""
    operation: str
    target: str
    input: Mapping[str, Any]
    idempotency_key: str
    confirmed: bool = False
    confirmation_target: str | None = None


@dataclass(frozen=True, slots=True)
class OperationRecord:
    """Represent the operation record contract."""
    id: str
    operation: str
    target: str
    state: OperationState
    result_code: str | None
    created_at: datetime
    updated_at: datetime


type OperationHandler = Callable[[ManagementPrincipal, OperationRequest], Awaitable[str | None]]


class WorkerOperationBridge:
    """Typed worker-side execution bridge for a daemon-owned operation ledger.

    The ledger owns state transitions and audit persistence. A worker bridge owns
    only execution of an already-authorized, schema-validated request.
    """

    def __init__(self, handler: OperationHandler) -> None:
        """Initialize the worker operation bridge.

        Args:
            handler: Callable that handles the dispatched value.

        Returns:
            None.
        """
        self._handler = handler

    async def execute(self, principal: ManagementPrincipal, request: OperationRequest) -> str | None:
        """Execute one request through the worker operation bridge.

        Args:
            principal: Authenticated principal requesting the operation.
            request: Validated request object to process.

        Returns:
            The `str | None` result produced by the operation.
        """
        return await self._handler(principal, request)


class OperationLedger:
    """Single-instance FIFO executor whose database never stores raw user input."""

    def __init__(
        self, path: str | Path, *, audit_key: bytes, retention_days: int = 30, retention_rows: int = 100_000
    ) -> None:
        """Initialize the operation ledger.

        Args:
            path: Filesystem or logical resource path.
            audit_key: The audit key value used by the operation.
            retention_days: The retention days value used by the operation.
            retention_rows: The retention rows value used by the operation.

        Returns:
            None.
        """
        if not audit_key or retention_days < 1 or retention_rows < 1:
            raise ValueError("operation audit configuration is invalid")
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._key = audit_key
        self._retention_days = retention_days
        self._retention_rows = retention_rows
        self._definitions: dict[str, tuple[OperationDefinition, WorkerOperationBridge]] = {}
        self._queue: asyncio.Queue[tuple[ManagementPrincipal, OperationRequest, str]] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self._cancelled: set[str] = set()
        self._connection = sqlite3.connect(self._path)
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS operations ("
            "id TEXT PRIMARY KEY, operation TEXT NOT NULL, target TEXT NOT NULL, principal TEXT NOT NULL, "
            "input_digest TEXT NOT NULL, state TEXT NOT NULL, result_code TEXT, created_at TEXT NOT NULL, "
            "updated_at TEXT NOT NULL, idempotency TEXT NOT NULL UNIQUE)"
        )
        self._connection.execute(
            "UPDATE operations SET state = ?, result_code = ?, updated_at = ? "
            "WHERE state IN (?, ?)",
            (
                OperationState.UNKNOWN,
                "worker_restarted",
                datetime.now(UTC).isoformat(),
                OperationState.QUEUED,
                OperationState.RUNNING,
            ),
        )
        self._connection.commit()

    def register(self, definition: OperationDefinition, handler: OperationHandler) -> None:
        """Register the operation ledger operation.

        Args:
            definition: The definition value used by the operation.
            handler: Callable that handles the dispatched value.

        Returns:
            None.
        """
        if definition.name in self._definitions:
            raise OperationError(f"operation already registered: {definition.name}")
        self._definitions[definition.name] = (definition, WorkerOperationBridge(handler))

    def has_definition(self, name: str) -> bool:
        """Implement the has definition operation for the operation ledger.

        Args:
            name: Stable name used to identify the value.

        Returns:
            Whether the requested condition is satisfied.
        """
        return name in self._definitions

    def catalog(self, principal: ManagementPrincipal) -> tuple[dict[str, Any], ...]:
        """Return only operations the principal may discover and submit.

        Args:
            principal: Authenticated principal requesting the operation.

        Returns:
            The `tuple[dict[str, Any], ...]` result produced by the operation.
        """

        now = datetime.now(UTC)
        return tuple(
            definition.catalog_entry()
            for definition, _bridge in sorted(self._definitions.values(), key=lambda item: item[0].id)
            if principal.allows(definition.capability, now=now)
        )

    async def start(self) -> None:
        """Start the operation ledger.

        Returns:
            None.
        """
        if self._worker is None:
            self._worker = asyncio.create_task(self._run(), name="operation-ledger")

    async def close(self) -> None:
        """Close the operation ledger and release its owned resources.

        Returns:
            None.
        """
        if self._worker is not None:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)
            self._worker = None
        self._connection.close()

    async def submit(self, principal: ManagementPrincipal, request: OperationRequest) -> OperationRecord:
        """Implement the submit operation for the operation ledger.

        Args:
            principal: Authenticated principal requesting the operation.
            request: Validated request object to process.

        Returns:
            The `OperationRecord` result produced by the operation.
        """
        selected = self._definitions.get(request.operation)
        now = datetime.now(UTC)
        if selected is None or not principal.allows(selected[0].capability, now=now):
            return self._write(principal, request, OperationState.REJECTED, "unauthorized", now)
        validation_error = self.validate_request(selected[0], request)
        if validation_error is not None:
            return self._write(principal, request, OperationState.REJECTED, validation_error, now)
        existing = self._connection.execute(
            "SELECT id, operation, target, state, result_code, created_at, updated_at "
            "FROM operations WHERE idempotency = ?",
            (self._idempotency(principal, request),),
        ).fetchone()
        if existing is not None:
            return self._record(existing)
        record = self._write(principal, request, OperationState.QUEUED, None, now)
        await self._queue.put((principal, request, record.id))
        return record

    def cancel(self, record_id: str) -> bool:
        """Implement the cancel operation for the operation ledger.

        Args:
            record_id: Stable identifier for the record.

        Returns:
            Whether the requested condition is satisfied.
        """
        row = self._connection.execute("SELECT operation, state FROM operations WHERE id = ?", (record_id,)).fetchone()
        if row is None or row[1] != OperationState.QUEUED or not self._definitions[row[0]][0].cancellable:
            return False
        self._cancelled.add(record_id)
        return True

    def get(self, record_id: str) -> OperationRecord | None:
        """Return the operation ledger operation.

        Args:
            record_id: Stable identifier for the record.

        Returns:
            The `OperationRecord | None` result produced by the operation.
        """
        row = self._connection.execute(
            "SELECT id, operation, target, state, result_code, created_at, updated_at FROM operations WHERE id = ?",
            (record_id,),
        ).fetchone()
        return self._record(row) if row else None

    def records(self, limit: int) -> tuple[OperationRecord, ...]:
        """Implement the records operation for the operation ledger.

        Args:
            limit: Maximum number of records to return.

        Returns:
            The `tuple[OperationRecord, ...]` result produced by the operation.
        """
        if not 1 <= limit <= 500:
            raise ValueError("operation record limit must be between 1 and 500")
        rows = self._connection.execute(
            "SELECT id, operation, target, state, result_code, created_at, updated_at "
            "FROM operations ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return tuple(self._record(row) for row in rows)

    async def _run(self) -> None:
        """Run the operation ledger operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `OperationLedger._run`. It delegates to `get`, `_transition`,
            `execute` while keeping intermediate state local to the owning operation.
        """
        while True:
            principal, request, record_id = await self._queue.get()
            if record_id in self._cancelled:
                self._transition(record_id, OperationState.CANCELLED, "cancelled")
                continue
            self._transition(record_id, OperationState.RUNNING, None)
            _definition, bridge = self._definitions[request.operation]
            try:
                result = await bridge.execute(principal, request)
            except Exception:
                self._transition(record_id, OperationState.FAILED, "operation_failed")
            else:
                self._transition(record_id, OperationState.SUCCEEDED, result or "ok")

    def _write(
        self,
        principal: ManagementPrincipal,
        request: OperationRequest,
        state: OperationState,
        result: str | None,
        now: datetime,
    ) -> OperationRecord:
        """Write the operation ledger operation.

        Args:
            principal: Authenticated principal requesting the operation.
            request: Validated request object to process.
            state: The state value used by the operation.
            result: Result value produced by the preceding operation.
            now: The now value used by the operation.

        Returns:
            The `OperationRecord` result produced by the operation.

        Notes:
            Internal implementation detail for `OperationLedger._write`. It delegates to `uuid4`,
            `isoformat`, `execute`, `_target` while keeping intermediate state local to the owning
            operation.
        """
        identifier = str(uuid4())
        timestamp = now.isoformat()
        self._connection.execute(
            "INSERT INTO operations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                identifier,
                request.operation,
                self._target(request.target),
                self._principal(principal),
                self._digest(request.input),
                state,
                result,
                timestamp,
                timestamp,
                self._idempotency(principal, request),
            ),
        )
        self._prune(now)
        self._connection.commit()
        return OperationRecord(identifier, request.operation, self._target(request.target), state, result, now, now)

    def _transition(self, identifier: str, state: OperationState, result: str | None) -> None:
        """Implement the transition operation for the operation ledger.

        Args:
            identifier: The identifier value used by the operation.
            state: The state value used by the operation.
            result: Result value produced by the preceding operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `OperationLedger._transition`. It delegates to `isoformat`,
            `now`, `execute`, `commit` while keeping intermediate state local to the owning operation.
        """
        now = datetime.now(UTC).isoformat()
        self._connection.execute(
            "UPDATE operations SET state = ?, result_code = ?, updated_at = ? WHERE id = ?",
            (state, result, now, identifier),
        )
        self._connection.commit()

    def _prune(self, now: datetime) -> None:
        """Implement the prune operation for the operation ledger.

        Args:
            now: The now value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `OperationLedger._prune`. It delegates to `isoformat`,
            `timedelta`, `execute` while keeping intermediate state local to the owning operation.
        """
        cutoff = (now - timedelta(days=self._retention_days)).isoformat()
        self._connection.execute("DELETE FROM operations WHERE created_at < ?", (cutoff,))
        self._connection.execute(
            "DELETE FROM operations WHERE id IN ("
            "SELECT id FROM operations ORDER BY created_at DESC LIMIT -1 OFFSET ?) ",
            (self._retention_rows,),
        )

    def _principal(self, principal: ManagementPrincipal) -> str:
        """Implement the principal operation for the operation ledger.

        Args:
            principal: Authenticated principal requesting the operation.

        Returns:
            The `str` result produced by the operation.

        Notes:
            Internal implementation detail for `OperationLedger._principal`. It delegates to `_hmac` while
            keeping intermediate state local to the owning operation.
        """
        return self._hmac("principal", f"{principal.kind}:{principal.subject}")

    def _target(self, target: str) -> str:
        """Implement the target operation for the operation ledger.

        Args:
            target: Target value or location for the operation.

        Returns:
            The `str` result produced by the operation.

        Notes:
            Internal implementation detail for `OperationLedger._target`. It delegates to `_hmac` while
            keeping intermediate state local to the owning operation.
        """
        return self._hmac("target", target)

    def _hmac(self, domain: str, value: str) -> str:
        """Implement the hmac operation for the operation ledger.

        Args:
            domain: The domain value used by the operation.
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.

        Notes:
            Internal implementation detail for `OperationLedger._hmac`. It delegates to `hexdigest`, `new`,
            `encode` while keeping intermediate state local to the owning operation.
        """
        return hmac.new(self._key, f"{domain}:{value}".encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def _digest(value: Mapping[str, Any]) -> str:
        """Implement the digest operation for the operation ledger.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.

        Notes:
            Internal implementation detail for `OperationLedger._digest`. It delegates to `hexdigest`,
            `sha256`, `encode`, `dumps` while keeping intermediate state local to the owning operation.
        """
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def _idempotency(self, principal: ManagementPrincipal, request: OperationRequest) -> str:
        """Implement the idempotency operation for the operation ledger.

        Args:
            principal: Authenticated principal requesting the operation.
            request: Validated request object to process.

        Returns:
            The `str` result produced by the operation.

        Notes:
            Internal implementation detail for `OperationLedger._idempotency`. It delegates to `hexdigest`,
            `new`, `encode`, `_principal` while keeping intermediate state local to the owning operation.
        """
        return hmac.new(
            self._key,
            f"{self._principal(principal)}:{request.operation}:{request.target}:{self._digest(request.input)}:{request.idempotency_key}".encode(),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def validate_request(definition: OperationDefinition, request: OperationRequest) -> str | None:
        """Validate request.

        Args:
            definition: The definition value used by the operation.
            request: Validated request object to process.

        Returns:
            The `str | None` result produced by the operation.
        """
        if not request.idempotency_key or request.idempotency_key != request.idempotency_key.strip():
            return "invalid_idempotency_key"
        if not request.target or request.target != request.target.strip():
            return "invalid_target"
        try:
            json.dumps(request.input, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError):
            return "invalid_input"
        try:
            from jsonschema import Draft202012Validator

            Draft202012Validator(definition.input_schema).validate(dict(request.input))
        except Exception:
            return "invalid_input"
        if (
            definition.target_input_field is not None
            and request.input.get(definition.target_input_field) != request.target
        ):
            return "target_mismatch"
        if definition.confirmation is OperationConfirmation.EXPLICIT and not request.confirmed:
            return "confirmation_required"
        if definition.confirmation is OperationConfirmation.TARGET and (
            not request.confirmed or request.confirmation_target != request.target
        ):
            return "target_confirmation_required"
        return None

    @staticmethod
    def _record(row: tuple[Any, ...]) -> OperationRecord:
        """Record the operation ledger operation.

        Args:
            row: The row value used by the operation.

        Returns:
            The `OperationRecord` result produced by the operation.

        Notes:
            Internal implementation detail for `OperationLedger._record`. It delegates to `fromisoformat`
            while keeping intermediate state local to the owning operation.
        """
        return OperationRecord(
            row[0],
            row[1],
            row[2],
            OperationState(row[3]),
            row[4],
            datetime.fromisoformat(row[5]),
            datetime.fromisoformat(row[6]),
        )
