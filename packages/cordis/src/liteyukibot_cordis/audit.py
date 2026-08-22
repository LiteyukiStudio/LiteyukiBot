"""Redacted bounded audit records for Cordis-managed operations."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from time import monotonic
from typing import Protocol


class AuditLogger(Protocol):
    """Define the structural interface required from a audit logger."""
    def bind(self, **values: object) -> AuditLogger:
        """Bind the audit logger operation.

        Args:
            **values: The values value used by the operation.

        Returns:
            The `AuditLogger` result produced by the operation.
        """
        ...

    def info(self, message: str, *args: object) -> None:
        """Implement the info operation for the audit logger.

        Args:
            message: Message content associated with the operation.
            *args: The args value used by the operation.

        Returns:
            None.
        """
        ...


@dataclass(frozen=True, slots=True)
class CordisAuditRecord:
    """Represent the cordis audit record contract."""
    plugin_id: str
    scope_id: str
    event_id: str | None
    operation: str
    outcome: str
    duration_seconds: float
    error_type: str | None = None


class CordisAuditService:
    """Keep a bounded, payload-free view of observable Cordis operations."""

    def __init__(self, capacity: int = 512, *, logger: AuditLogger | None = None) -> None:
        """Initialize the cordis audit service.

        Args:
            capacity: The capacity value used by the operation.
            logger: Structured logger used for diagnostics.

        Returns:
            None.
        """
        if capacity < 1:
            raise ValueError("audit capacity must be positive")
        self._records: deque[CordisAuditRecord] = deque(maxlen=capacity)
        self._logger = logger

    def record(
        self,
        *,
        plugin_id: str,
        scope_id: str,
        event_id: str | None,
        operation: str,
        outcome: str,
        started_at: float | None = None,
        error: BaseException | None = None,
    ) -> CordisAuditRecord:
        """Record the cordis audit service operation.

        Args:
            plugin_id: Stable identifier for the plugin.
            scope_id: Stable identifier for the scope.
            event_id: Stable event identifier.
            operation: The operation value used by the operation.
            outcome: The outcome value used by the operation.
            started_at: The started at value used by the operation.
            error: The error value used by the operation.

        Returns:
            The `CordisAuditRecord` result produced by the operation.
        """
        duration = 0.0 if started_at is None else max(0.0, monotonic() - started_at)
        record = CordisAuditRecord(
            plugin_id=plugin_id,
            scope_id=scope_id,
            event_id=event_id,
            operation=operation,
            outcome=outcome,
            duration_seconds=duration,
            error_type=None if error is None else type(error).__name__,
        )
        self._records.append(record)
        if self._logger is not None:
            self._logger.bind(
                component="cordis",
                plugin_id=plugin_id,
                scope_id=scope_id,
                event_id=event_id,
                operation=operation,
                outcome=outcome,
                duration_seconds=duration,
                error_type=record.error_type,
            ).info("Cordis operation {}", outcome)
        return record

    def snapshot(self, *, limit: int | None = None) -> tuple[CordisAuditRecord, ...]:
        """Return an immutable snapshot of the cordis audit service state.

        Args:
            limit: Maximum number of records to return.

        Returns:
            The requested `tuple[CordisAuditRecord, ...]` value.
        """
        if limit is not None and limit < 0:
            raise ValueError("limit must be non-negative")
        records = tuple(self._records)
        return records if limit is None else records[-limit:] if limit else ()
