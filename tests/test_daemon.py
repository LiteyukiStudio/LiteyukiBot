from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from liteyukibot.config import ConfigWorkspace, DaemonSettings, WebUISettings
from liteyukibot.config.models import DevelopmentSettings
from liteyukibot.control import ControlServer, request_control
from liteyukibot.daemon import InstanceDaemon
from liteyukibot.instance_daemon import InstanceDaemonService
from liteyukibot.instances import InstancePaths


@pytest.mark.asyncio
async def test_daemon_publishes_status_and_stops_its_worker(tmp_path: Path) -> None:
    paths = InstancePaths.from_workspace(ConfigWorkspace(tmp_path), "dev")
    daemon = InstanceDaemon(
        paths,
        DaemonSettings(),
        (sys.executable, "-c", "import time; time.sleep(60)"),
        {},
    )
    task = asyncio.create_task(daemon.run())
    for _ in range(100):
        if paths.daemon_descriptor.is_file():
            break
        await asyncio.sleep(0.01)
    snapshot = await request_control(paths.daemon_descriptor, "status")
    assert snapshot["instance"] == "dev"
    assert snapshot["worker"]["pid"] is not None

    assert await request_control(paths.daemon_descriptor, "stop") == {"accepted": True}
    assert await asyncio.wait_for(task, timeout=10) == 0
    assert not paths.daemon_descriptor.exists()


@pytest.mark.asyncio
async def test_daemon_bounds_abnormal_worker_restarts(tmp_path: Path) -> None:
    paths = InstancePaths.from_workspace(ConfigWorkspace(tmp_path), "crash")
    daemon = InstanceDaemon(
        paths,
        DaemonSettings(
            auto_restart=True,
            restart_limit=2,
            restart_window_seconds=30,
            restart_backoff_initial_seconds=0.001,
            restart_backoff_max_seconds=0.001,
        ),
        (sys.executable, "-c", "raise SystemExit(7)"),
        {},
    )

    assert await asyncio.wait_for(daemon.run(), timeout=10) == 7
    assert daemon.status()["failures_in_window"] == 3
    assert daemon.status()["last_restart_reason"] == "worker exited with code 7"


@pytest.mark.asyncio
async def test_plugin_daemon_service_requests_one_rate_limited_restart(tmp_path: Path) -> None:
    paths = InstancePaths.from_workspace(ConfigWorkspace(tmp_path), "plugin")
    daemon = InstanceDaemon(
        paths,
        DaemonSettings(),
        (sys.executable, "-c", "import time; time.sleep(60)"),
        {},
    )
    task = asyncio.create_task(daemon.run())
    for _ in range(100):
        if paths.daemon_descriptor.is_file():
            break
        await asyncio.sleep(0.01)
    service = InstanceDaemonService(paths.daemon_descriptor)
    snapshot = await service.snapshot()
    assert snapshot["instance"] == "plugin"
    assert await service.request_restart("plugin update") is True
    assert await service.request_restart("duplicate") is False
    await asyncio.sleep(0.05)
    worker = daemon.status()["worker"]
    assert isinstance(worker, dict)
    assert worker["pid"] is not None
    await request_control(paths.daemon_descriptor, "stop")
    assert await asyncio.wait_for(task, timeout=10) == 0


@pytest.mark.asyncio
async def test_development_daemon_forwards_only_to_the_local_worker(tmp_path: Path) -> None:
    paths = InstancePaths.from_workspace(ConfigWorkspace(tmp_path), "development")
    worker_descriptor = tmp_path / "worker.json"

    async def inject(request: object) -> object:
        assert isinstance(request, dict)
        return {"event": request["event"]}

    worker = ControlServer(
        worker_descriptor,
        status_provider=lambda: {"state": "ready"},
        handlers={"event.inject": inject},
    )
    await worker.start()
    daemon = InstanceDaemon(
        paths,
        DaemonSettings(),
        (sys.executable, "-c", "import time; time.sleep(60)"),
        {},
        worker_descriptor=worker_descriptor,
        development=DevelopmentSettings(enabled=True),
    )
    task = asyncio.create_task(daemon.run())
    for _ in range(100):
        if paths.daemon_descriptor.is_file():
            break
        await asyncio.sleep(0.01)
    assert await request_control(paths.daemon_descriptor, "dev.status") == {"state": "ready"}
    assert await request_control(paths.daemon_descriptor, "dev.event.inject", event={"id": "event"}) == {
        "event": {"id": "event"}
    }
    await request_control(paths.daemon_descriptor, "stop")
    assert await asyncio.wait_for(task, timeout=10) == 0
    await worker.stop()


@pytest.mark.asyncio
async def test_daemon_webui_bridge_owns_tickets_and_operation_ledger(tmp_path: Path) -> None:
    paths = InstancePaths.from_workspace(ConfigWorkspace(tmp_path), "webui")
    worker_descriptor = tmp_path / "worker.json"
    executed: list[dict[str, object]] = []

    async def catalog(_request: object) -> object:
        return {
            "operations": [
                {
                    "id": "management.runtime.restart",
                    "api": "liteyuki.management",
                    "version": 1,
                    "capability": "liteyukibot.management.admin",
                    "input_schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {"runtime_id": {"type": "string", "minLength": 1}},
                        "required": ["runtime_id"],
                    },
                    "impact": "standard",
                    "confirmation": "explicit",
                    "target": "runtime_id",
                    "target_input_field": "runtime_id",
                    "mutating": True,
                    "cancellable": False,
                }
            ]
        }

    async def execute(request: object) -> object:
        assert isinstance(request, dict)
        executed.append(request)
        return {"result_code": "ok"}

    worker = ControlServer(
        worker_descriptor,
        status_provider=lambda: {"state": "ready", "runtime_health": {}},
        handlers={
            "daemon.webui.operation_catalog": catalog,
            "daemon.webui.operation.execute": execute,
        },
    )
    await worker.start()
    daemon = InstanceDaemon(
        paths,
        DaemonSettings(),
        (sys.executable, "-c", "import time; time.sleep(60)"),
        {},
        worker_descriptor=worker_descriptor,
        webui=WebUISettings(mode="on_demand"),
    )
    try:
        ticket = await daemon.issue_ticket()
        principal = await daemon.redeem_ticket(ticket)
        assert principal is not None
        assert await daemon.redeem_ticket(ticket) is None
        operation_catalog = await daemon.operation_catalog(principal)
        catalog_entries = operation_catalog["operations"]
        assert isinstance(catalog_entries, list)
        assert isinstance(catalog_entries[0], dict)
        assert catalog_entries[0]["id"] == "management.runtime.restart"

        submitted = await daemon.submit_operation(
            principal,
            {
                "operation_id": "management.runtime.restart",
                "target": "runtime-id",
                "input": {"runtime_id": "runtime-id"},
                "idempotency_key": "operation-1",
                "confirmed": True,
            },
        )
        for _ in range(100):
            current = await daemon.operation(principal, str(submitted["id"]))
            if current is not None and current["state"] == "succeeded":
                break
            await asyncio.sleep(0.01)
        assert current is not None and current["state"] == "succeeded"
        assert executed[0]["operation_id"] == "management.runtime.restart"
        assert paths.root.joinpath("operations.sqlite3").is_file()
        ledger = await daemon.ledger(principal, None, 20)
        assert ledger["items"] == [
            {
                "id": submitted["id"],
                "at": current["updated_at"],
                "category": "operation",
                "title": "management.runtime.restart",
                "source": current["target"],
                "status": "healthy",
                "trace": submitted["id"],
                "detail": "ok",
            }
        ]
    finally:
        await daemon.operations.close()
        await worker.stop()


@pytest.mark.asyncio
async def test_invalid_watcher_configuration_preserves_the_healthy_worker(tmp_path: Path) -> None:
    paths = InstancePaths.from_workspace(ConfigWorkspace(tmp_path), "watch")
    watched = tmp_path / "plugin.py"
    watched.write_text("first", encoding="utf-8")
    daemon = InstanceDaemon(
        paths,
        DaemonSettings(),
        (sys.executable, "-c", "import time; time.sleep(60)"),
        {},
        development=DevelopmentSettings(enabled=True, watch_auto_restart=True, watch_debounce_seconds=0.01),
        watch_root=tmp_path,
        validate_configuration=lambda: (_ for _ in ()).throw(ValueError("invalid")),
    )
    task = asyncio.create_task(daemon.run())
    for _ in range(100):
        if daemon.worker is not None:
            break
        await asyncio.sleep(0.01)
    initial_pid = daemon.worker.pid if daemon.worker is not None else None
    watched.write_text("changed", encoding="utf-8")
    await asyncio.sleep(0.5)
    assert daemon.worker is not None and daemon.worker.pid == initial_pid
    assert daemon.status()["last_restart_reason"] is None
    await request_control(paths.daemon_descriptor, "stop")
    assert await asyncio.wait_for(task, timeout=10) == 0
