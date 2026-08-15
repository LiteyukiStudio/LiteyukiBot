"""Daemon-owned structured management operations and redacted audit storage."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import sqlite3
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4


class OperationError(RuntimeError):
    pass


class PrincipalKind(StrEnum):
    CLI_SESSION = "cli_session"
    WEB_SESSION = "web_session"
    RUNTIME = "runtime"
    PLUGIN = "plugin"
    SYSTEM = "system"


class OperationState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class ManagementPrincipal:
    kind: PrincipalKind
    subject: str
    authentication_origin: str
    expires_at: datetime | None
    capabilities: frozenset[str]

    def allows(self, capability: str, *, now: datetime | None = None) -> bool:
        current = now or datetime.now(UTC)
        return (self.expires_at is None or self.expires_at > current) and capability in self.capabilities


@dataclass(frozen=True, slots=True)
class OperationDefinition:
    name: str
    capability: str
    mutating: bool
    cancellable: bool = False


@dataclass(frozen=True, slots=True)
class OperationRequest:
    operation: str
    target: str
    input: Mapping[str, Any]
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class OperationRecord:
    id: str
    operation: str
    target: str
    state: OperationState
    result_code: str | None
    created_at: datetime
    updated_at: datetime


type OperationHandler = Callable[[ManagementPrincipal, OperationRequest], Awaitable[str | None]]


class OperationLedger:
    """Single-instance FIFO executor whose database never stores raw user input."""

    def __init__(
        self, path: str | Path, *, audit_key: bytes, retention_days: int = 30, retention_rows: int = 100_000
    ) -> None:
        if not audit_key or retention_days < 1 or retention_rows < 1:
            raise ValueError("operation audit configuration is invalid")
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._key = audit_key
        self._retention_days = retention_days
        self._retention_rows = retention_rows
        self._definitions: dict[str, tuple[OperationDefinition, OperationHandler]] = {}
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
        if definition.name in self._definitions:
            raise OperationError(f"operation already registered: {definition.name}")
        self._definitions[definition.name] = (definition, handler)

    def has_definition(self, name: str) -> bool:
        return name in self._definitions

    async def start(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._run(), name="operation-ledger")

    async def close(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)
            self._worker = None
        self._connection.close()

    async def submit(self, principal: ManagementPrincipal, request: OperationRequest) -> OperationRecord:
        selected = self._definitions.get(request.operation)
        now = datetime.now(UTC)
        if selected is None or not principal.allows(selected[0].capability, now=now):
            return self._write(principal, request, OperationState.REJECTED, "unauthorized", now)
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
        row = self._connection.execute("SELECT operation, state FROM operations WHERE id = ?", (record_id,)).fetchone()
        if row is None or row[1] != OperationState.QUEUED or not self._definitions[row[0]][0].cancellable:
            return False
        self._cancelled.add(record_id)
        return True

    def get(self, record_id: str) -> OperationRecord | None:
        row = self._connection.execute(
            "SELECT id, operation, target, state, result_code, created_at, updated_at FROM operations WHERE id = ?",
            (record_id,),
        ).fetchone()
        return self._record(row) if row else None

    async def _run(self) -> None:
        while True:
            principal, request, record_id = await self._queue.get()
            if record_id in self._cancelled:
                self._transition(record_id, OperationState.CANCELLED, "cancelled")
                continue
            self._transition(record_id, OperationState.RUNNING, None)
            _definition, handler = self._definitions[request.operation]
            try:
                result = await handler(principal, request)
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
        now = datetime.now(UTC).isoformat()
        self._connection.execute(
            "UPDATE operations SET state = ?, result_code = ?, updated_at = ? WHERE id = ?",
            (state, result, now, identifier),
        )
        self._connection.commit()

    def _prune(self, now: datetime) -> None:
        cutoff = (now - timedelta(days=self._retention_days)).isoformat()
        self._connection.execute("DELETE FROM operations WHERE created_at < ?", (cutoff,))
        self._connection.execute(
            "DELETE FROM operations WHERE id IN ("
            "SELECT id FROM operations ORDER BY created_at DESC LIMIT -1 OFFSET ?) ",
            (self._retention_rows,),
        )

    def _principal(self, principal: ManagementPrincipal) -> str:
        return self._hmac("principal", f"{principal.kind}:{principal.subject}")

    def _target(self, target: str) -> str:
        return self._hmac("target", target)

    def _hmac(self, domain: str, value: str) -> str:
        return hmac.new(self._key, f"{domain}:{value}".encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def _digest(value: Mapping[str, Any]) -> str:
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def _idempotency(self, principal: ManagementPrincipal, request: OperationRequest) -> str:
        return hmac.new(
            self._key,
            f"{self._principal(principal)}:{request.operation}:{request.target}:{self._digest(request.input)}:{request.idempotency_key}".encode(),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _record(row: tuple[Any, ...]) -> OperationRecord:
        return OperationRecord(
            row[0],
            row[1],
            row[2],
            OperationState(row[3]),
            row[4],
            datetime.fromisoformat(row[5]),
            datetime.fromisoformat(row[6]),
        )
