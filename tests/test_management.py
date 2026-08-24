from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from liteyukibot.management import (
    MANAGEMENT_ADMIN,
    KernelManagement,
    ManagementCaller,
    ManagementCommand,
    ManagementDanger,
    ManagementError,
    ManagementRegistry,
    ManagementResult,
)
from liteyukibot.operations import ManagementPrincipal, OperationLedger, OperationState, PrincipalKind


async def _result(_caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
    return ManagementResult(" ".join(arguments))


@pytest.mark.asyncio
async def test_management_registry_resolves_and_executes_quoted_arguments() -> None:
    registry = ManagementRegistry()
    command = ManagementCommand(("plugin", "install"), "Install a plugin")
    registry.register(command, _result)

    caller = ManagementCaller.local_terminal()
    selected, result = await registry.execute(caller, 'plugin install runtime "example plugin"')

    assert selected == command
    assert result.text == "runtime example plugin"


@pytest.mark.asyncio
async def test_management_registry_rejects_unauthorized_extension_callers() -> None:
    registry = ManagementRegistry()
    registry.register(ManagementCommand(("status",), "Show status"), _result)
    caller = ManagementCaller("plugin.example", "plugin", frozenset({MANAGEMENT_ADMIN}))

    with pytest.raises(ManagementError, match="not authorized"):
        await registry.execute(caller, "status")

    registry.set_authorizer(lambda actual, capability: actual.id == "plugin.example" and capability == MANAGEMENT_ADMIN)
    _command, result = await registry.execute(caller, "status")
    assert result.text == ""


def test_management_registry_lists_only_authorized_commands() -> None:
    registry = ManagementRegistry()
    registry.register(ManagementCommand(("status",), "Show status"), _result)
    registry.register(
        ManagementCommand(("stop",), "Stop", danger=ManagementDanger.CONFIRM),
        _result,
    )
    caller = ManagementCaller.local_terminal()

    assert tuple(command.name for command in registry.commands(caller)) == (("status",), ("stop",))


@pytest.mark.asyncio
async def test_kernel_management_queues_a_structured_command_without_storing_arguments(tmp_path: Path) -> None:
    app = type("App", (), {"status": lambda _self: {"ready": True}})()
    management = KernelManagement(app, str(tmp_path), lambda: None)
    await management.start_operations(tmp_path)
    received: list[tuple[str, ...]] = []

    async def echo(_caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        received.append(arguments)
        return ManagementResult("ok")

    management.registry.register(ManagementCommand(("echo",), "Echo input"), echo)
    management.registry.set_authorizer(lambda _caller, capability: capability == MANAGEMENT_ADMIN)
    principal = ManagementPrincipal(
        PrincipalKind.WEB_SESSION,
        "web-session-1",
        "loopback-ticket",
        datetime.now(UTC) + timedelta(minutes=1),
        frozenset({MANAGEMENT_ADMIN}),
    )
    try:
        record = await management.submit_operation(
            principal,
            ("echo",),
            ("sensitive-argument",),
            confirmed=False,
            idempotency_key="status-1",
        )
        for _ in range(20):
            current = management.operations.get(record.id) if management.operations else None
            if current is not None and current.result_code == "ok":
                break
            await asyncio.sleep(0)
        assert current is not None and current.result_code == "ok"
        assert received == [("sensitive-argument",)]
        assert b"sensitive-argument" not in (tmp_path / "operations.sqlite3").read_bytes()
    finally:
        await management.close_operations()


@pytest.mark.asyncio
async def test_kernel_management_catalog_submits_structured_operation_without_command_line(tmp_path: Path) -> None:
    restarted: list[str] = []

    class Runtimes:
        async def start_runtime(self, runtime_id: str) -> None:
            restarted.append(f"started:{runtime_id}")

        async def stop_runtime(self, runtime_id: str) -> None:
            restarted.append(f"stopped:{runtime_id}")

        async def restart(self, runtime_id: str) -> None:
            restarted.append(runtime_id)

    app = type("App", (), {"runtimes": Runtimes()})()
    management = KernelManagement(app, str(tmp_path), lambda: None)
    management.registry.set_authorizer(lambda _caller, capability: capability == MANAGEMENT_ADMIN)
    principal = ManagementPrincipal(
        PrincipalKind.WEB_SESSION,
        "web-session-1",
        "loopback-ticket",
        datetime.now(UTC) + timedelta(minutes=1),
        frozenset({MANAGEMENT_ADMIN}),
    )
    ledger = OperationLedger(tmp_path / "operations.sqlite3", audit_key=b"key")
    try:
        catalog = management.operation_catalog(principal)
        restart = next(item for item in catalog if item["id"] == "management.runtime.restart")
        assert restart["input_schema"]["required"] == ["runtime_id"]
        assert restart["target"] == "runtime_id"
        assert restart["confirmation"] == "explicit"
        install = next(item for item in catalog if item["id"] == "management.plugin.install")
        assert "expected_index_digest" in install["input_schema"]["properties"]
        assert {item["id"] for item in catalog} >= {
            "management.plugin.uninstall",
            "management.plugin.gc",
        }
        management.bind_operations(ledger)
        await ledger.start()
        record = await management.submit_structured_operation(
            principal,
            "management.runtime.restart",
            "runtime-a",
            {"runtime_id": "runtime-a"},
            confirmed=True,
            confirmation_target=None,
            idempotency_key="restart-1",
        )
        for _ in range(20):
            current = management.operations.get(record.id) if management.operations else None
            if current is not None and current.state is OperationState.SUCCEEDED:
                break
            await asyncio.sleep(0)
        assert current is not None and current.result_code == "ok"
        assert restarted == ["runtime-a"]
        with pytest.raises(ManagementError, match="target does not match"):
            await management.submit_structured_operation(
                principal,
                "management.runtime.restart",
                "runtime-b",
                {"runtime_id": "runtime-a"},
                confirmed=True,
                confirmation_target=None,
                idempotency_key="restart-2",
            )
    finally:
        await management.close_operations()
        await ledger.close()
