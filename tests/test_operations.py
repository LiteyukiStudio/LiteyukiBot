from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from liteyukibot.operations import (
    ManagementPrincipal,
    OperationDefinition,
    OperationLedger,
    OperationRequest,
    OperationState,
    PrincipalKind,
)


def _principal(*capabilities: str) -> ManagementPrincipal:
    return ManagementPrincipal(
        PrincipalKind.CLI_SESSION,
        "local",
        "loopback",
        datetime.now(UTC) + timedelta(minutes=1),
        frozenset(capabilities),
    )


@pytest.mark.asyncio
async def test_operation_ledger_authorizes_idempotency_and_fifo(tmp_path: Path) -> None:
    seen: list[str] = []

    async def handler(_principal: ManagementPrincipal, request: OperationRequest) -> str:
        seen.append(request.target)
        return "done"

    ledger = OperationLedger(tmp_path / "operations.sqlite3", audit_key=b"key")
    ledger.register(OperationDefinition("runtime.restart", "restart", True, cancellable=True), handler)
    await ledger.start()
    try:
        rejected = await ledger.submit(_principal(), OperationRequest("runtime.restart", "a", {}, "one"))
        assert rejected.state is OperationState.REJECTED
        first = await ledger.submit(_principal("restart"), OperationRequest("runtime.restart", "a", {"x": 1}, "one"))
        assert (
            await ledger.submit(_principal("restart"), OperationRequest("runtime.restart", "a", {"x": 1}, "one"))
        ).id == first.id
        second = await ledger.submit(_principal("restart"), OperationRequest("runtime.restart", "b", {}, "two"))
        for _ in range(20):
            current = ledger.get(second.id)
            if current is not None and current.state is OperationState.SUCCEEDED:
                break
            await asyncio.sleep(0)
        assert seen == ["a", "b"]
        completed = ledger.get(first.id)
        assert completed is not None and completed.result_code == "done"
        audit = (tmp_path / "operations.sqlite3").read_bytes()
        assert b'"x":1' not in audit
        assert b"local" not in audit
    finally:
        await ledger.close()


@pytest.mark.asyncio
async def test_operation_ledger_marks_interrupted_work_unknown_after_restart(tmp_path: Path) -> None:
    async def handler(_principal: ManagementPrincipal, _request: OperationRequest) -> str:
        return "done"

    path = tmp_path / "operations.sqlite3"
    original = OperationLedger(path, audit_key=b"key")
    original.register(OperationDefinition("runtime.restart", "restart", True), handler)
    record = await original.submit(_principal("restart"), OperationRequest("runtime.restart", "worker", {}, "one"))
    await original.close()

    recovered = OperationLedger(path, audit_key=b"key")
    try:
        current = recovered.get(record.id)
        assert current is not None and current.state is OperationState.UNKNOWN
        assert current.result_code == "worker_restarted"
    finally:
        await recovered.close()
