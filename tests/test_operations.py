from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from liteyukibot.operations import (
    ManagementPrincipal,
    OperationConfirmation,
    OperationDefinition,
    OperationImpact,
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


@pytest.mark.asyncio
async def test_operation_ledger_exposes_catalog_and_requires_target_confirmation(tmp_path: Path) -> None:
    executed: list[str] = []

    async def handler(_principal: ManagementPrincipal, request: OperationRequest) -> str:
        executed.append(request.target)
        return "done"

    ledger = OperationLedger(tmp_path / "operations.sqlite3", audit_key=b"key")
    ledger.register(
        OperationDefinition(
            "plugin.rollback",
            "plugin.write",
            True,
            api="liteyuki.management",
            version=1,
            input_schema={
                "type": "object",
                "properties": {"runtime_id": {"type": "string", "minLength": 1}},
                "required": ["runtime_id"],
                "additionalProperties": False,
            },
            impact=OperationImpact.HIGH,
            confirmation=OperationConfirmation.TARGET,
            target="runtime_id",
            target_input_field="runtime_id",
        ),
        handler,
    )
    await ledger.start()
    try:
        principal = _principal("plugin.write")
        assert ledger.catalog(principal) == (
            {
                "id": "plugin.rollback",
                "api": "liteyuki.management",
                "version": 1,
                "input_schema": {
                    "type": "object",
                    "properties": {"runtime_id": {"type": "string", "minLength": 1}},
                    "required": ["runtime_id"],
                    "additionalProperties": False,
                },
                "impact": "high",
                "capability": "plugin.write",
                "confirmation": "target",
                "target": "runtime_id",
                "target_input_field": "runtime_id",
                "mutating": True,
                "cancellable": False,
            },
        )
        invalid = await ledger.submit(principal, OperationRequest("plugin.rollback", "runtime-a", {}, "invalid"))
        assert invalid.state is OperationState.REJECTED
        assert invalid.result_code == "invalid_input"
        unconfirmed = await ledger.submit(
            principal,
            OperationRequest("plugin.rollback", "runtime-a", {"runtime_id": "runtime-a"}, "unconfirmed"),
        )
        assert unconfirmed.result_code == "target_confirmation_required"
        mismatched = await ledger.submit(
            principal,
            OperationRequest(
                "plugin.rollback",
                "runtime-b",
                {"runtime_id": "runtime-a"},
                "mismatched",
                confirmed=True,
                confirmation_target="runtime-b",
            ),
        )
        assert mismatched.result_code == "target_mismatch"
        accepted = await ledger.submit(
            principal,
            OperationRequest(
                "plugin.rollback",
                "runtime-a",
                {"runtime_id": "runtime-a"},
                "confirmed",
                confirmed=True,
                confirmation_target="runtime-a",
            ),
        )
        for _ in range(20):
            current = ledger.get(accepted.id)
            if current is not None and current.state is OperationState.SUCCEEDED:
                break
            await asyncio.sleep(0)
        assert executed == ["runtime-a"]
    finally:
        await ledger.close()
