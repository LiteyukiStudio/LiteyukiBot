from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from liteyukibot.config import ConfigWorkspace, DaemonSettings, WebUISettings
from liteyukibot.config.models import DevelopmentSettings
from liteyukibot.control import ControlServer, request_control
from liteyukibot.daemon import InstanceDaemon
from liteyukibot.instance_daemon import InstanceDaemonService
from liteyukibot.instances import InstancePaths
from liteyukibot.managed_graph import ProcessSpec
from liteyukibot.plugin_sources import PluginSourceStore
from liteyukibot.plugin_store import (
    PLUGIN_GENERATION_ENV,
    PlatformTarget,
    PluginIndex,
    RuntimeGeneration,
    RuntimeGenerationStore,
)


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


def test_daemon_selects_generation_python_and_environment_per_bridge(tmp_path: Path) -> None:
    paths = InstancePaths.from_workspace(ConfigWorkspace(tmp_path), "managed")
    generations = RuntimeGenerationStore(tmp_path)
    generation = RuntimeGeneration(
        "candidate",
        "chat",
        "nonebot",
        "2026-08-22T00:00:00+00:00",
        PlatformTarget("windows", "amd64", "3.14"),
        ("example.echo",),
        ("a" * 64,),
        {"plugins": ["example.echo"], "directories": []},
    )
    generation_path = generations.write(generation)
    generation_python = generations.python_path(generation_path)
    generation_python.parent.mkdir(parents=True)
    generation_python.write_text("", encoding="utf-8")
    generations.activate("chat", generation.id)

    daemon = InstanceDaemon(
        paths,
        DaemonSettings(),
        (sys.executable, "-m", "liteyukibot.cli", "run"),
        {},
        bridge_commands={"chat": (sys.executable, "-m", "liteyukibot.cli", "bridge", "run", "chat")},
        bridge_kinds={"chat": "nonebot"},
    )

    bridge = next(spec for spec in daemon._graph.specs if spec.name == "bridge:chat")
    assert bridge.command[0] == str(generation_python)
    assert bridge.environment[PLUGIN_GENERATION_ENV] == str(generation_path)


@pytest.mark.asyncio
async def test_daemon_rolls_back_plugin_generation_when_candidate_bridge_fails_startup(tmp_path: Path) -> None:
    class FakeProcess:
        def __init__(self, pid: int, returncode: int | None = None) -> None:
            self.pid = pid
            self.returncode = returncode
            self._exited = asyncio.Event()
            if returncode is not None:
                self._exited.set()

        def terminate(self) -> None:
            self.returncode = 0
            self._exited.set()

        def kill(self) -> None:
            self.terminate()

        async def wait(self) -> int:
            await self._exited.wait()
            assert self.returncode is not None
            return self.returncode

    paths = InstancePaths.from_workspace(ConfigWorkspace(tmp_path), "rollback")
    generations = RuntimeGenerationStore(tmp_path)

    def write_generation(generation_id: str, digest: str) -> Path:
        generation = RuntimeGeneration(
            generation_id,
            "chat",
            "nonebot",
            "2026-08-22T00:00:00+00:00",
            PlatformTarget("windows", "amd64", "3.14"),
            (f"example.{generation_id}",),
            (digest,),
            {"plugins": [f"example.{generation_id}"], "directories": []},
        )
        path = generations.write(generation)
        python = generations.python_path(path)
        python.parent.mkdir(parents=True)
        python.write_text("", encoding="utf-8")
        return path

    previous_path = write_generation("previous", "a" * 64)
    candidate_path = write_generation("candidate", "b" * 64)
    generations.activate("chat", "previous")
    next_pid = 100

    async def launch(spec: ProcessSpec) -> FakeProcess:
        nonlocal next_pid
        next_pid += 1
        failed = spec.name == "bridge:chat" and spec.environment.get(PLUGIN_GENERATION_ENV) == str(candidate_path)
        return FakeProcess(next_pid, 7 if failed else None)

    daemon = InstanceDaemon(
        paths,
        DaemonSettings(),
        (sys.executable, "-m", "liteyukibot.cli", "run"),
        {},
        bridge_commands={"chat": (sys.executable, "-m", "liteyukibot.cli", "bridge", "run", "chat")},
        bridge_kinds={"chat": "nonebot"},
        process_launcher=launch,
    )
    await daemon._start_worker()
    generations.activate("chat", "candidate")
    daemon._restart_plugin_target = "chat"

    await daemon._restart_worker_graph()

    assert generations.active().runtime_generations == {"chat": "previous"}
    assert daemon.worker is not None
    assert "failed startup and was rolled back" in str(daemon.status()["last_restart_reason"])
    bridge = next(spec for spec in daemon._graph.specs if spec.name == "bridge:chat")
    assert bridge.environment[PLUGIN_GENERATION_ENV] == str(previous_path)
    await daemon._terminate_worker()
    await daemon.operations.close()


@pytest.mark.asyncio
async def test_daemon_deactivates_first_plugin_generation_when_candidate_fails_startup(tmp_path: Path) -> None:
    class FakeProcess:
        def __init__(self, pid: int, returncode: int | None = None) -> None:
            self.pid = pid
            self.returncode = returncode
            self._exited = asyncio.Event()
            if returncode is not None:
                self._exited.set()

        def terminate(self) -> None:
            self.returncode = 0
            self._exited.set()

        def kill(self) -> None:
            self.terminate()

        async def wait(self) -> int:
            await self._exited.wait()
            assert self.returncode is not None
            return self.returncode

    paths = InstancePaths.from_workspace(ConfigWorkspace(tmp_path), "first-install")
    generations = RuntimeGenerationStore(tmp_path)
    candidate = RuntimeGeneration(
        "candidate",
        "chat",
        "nonebot",
        "2026-08-22T00:00:00+00:00",
        PlatformTarget("windows", "amd64", "3.14"),
        ("example.candidate",),
        ("a" * 64,),
        {"plugins": ["example.candidate"], "directories": []},
    )
    candidate_path = generations.write(candidate)
    generation_python = generations.python_path(candidate_path)
    generation_python.parent.mkdir(parents=True)
    generation_python.write_text("", encoding="utf-8")
    next_pid = 200

    async def launch(spec: ProcessSpec) -> FakeProcess:
        nonlocal next_pid
        next_pid += 1
        failed = spec.name == "bridge:chat" and spec.environment.get(PLUGIN_GENERATION_ENV) == str(candidate_path)
        return FakeProcess(next_pid, 7 if failed else None)

    daemon = InstanceDaemon(
        paths,
        DaemonSettings(),
        (sys.executable, "-m", "liteyukibot.cli", "run"),
        {},
        bridge_commands={"chat": (sys.executable, "-m", "liteyukibot.cli", "bridge", "run", "chat")},
        bridge_kinds={"chat": "nonebot"},
        process_launcher=launch,
    )
    await daemon._start_worker()
    generations.activate("chat", "candidate")
    daemon._restart_plugin_target = "chat"

    await daemon._restart_worker_graph()

    assert generations.active().runtime_generations == {}
    assert daemon.worker is not None
    bridge = next(spec for spec in daemon._graph.specs if spec.name == "bridge:chat")
    assert bridge.environment.get(PLUGIN_GENERATION_ENV) != str(candidate_path)
    assert "failed startup and was rolled back" in str(daemon.status()["last_restart_reason"])
    await daemon._terminate_worker()
    await daemon.operations.close()


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
                    "id": "management.plugin.update",
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

    async def presentation(request: object) -> object:
        assert isinstance(request, dict)
        assert request["locale"] == "zh-CN"
        return {"locale": "zh-CN", "locales": ["en-US", "zh-CN"], "messages": {"webui.app.name": "Liteyuki"}}

    worker = ControlServer(
        worker_descriptor,
        status_provider=lambda: {"state": "ready", "runtime_health": {}},
        handlers={
            "daemon.webui.operation_catalog": catalog,
            "daemon.webui.operation.execute": execute,
            "daemon.webui.presentation": presentation,
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
        assert catalog_entries[0]["id"] == "management.plugin.update"
        assert await daemon.presentation(principal, "zh-CN") == {
            "locale": "zh-CN",
            "locales": ["en-US", "zh-CN"],
            "messages": {"webui.app.name": "Liteyuki"},
        }

        submitted = await daemon.submit_operation(
            principal,
            {
                "operation_id": "management.plugin.update",
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
        assert executed[0]["operation_id"] == "management.plugin.update"
        assert paths.root.joinpath("operations.sqlite3").is_file()
        ledger = await daemon.ledger(principal, None, 20)
        assert ledger["items"] == [
            {
                "id": submitted["id"],
                "at": current["updated_at"],
                "category": "operation",
                "title": "management.plugin.update",
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
async def test_daemon_webui_plugin_reads_are_bounded_and_metadata_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = InstancePaths.from_workspace(ConfigWorkspace(tmp_path), "plugin-ui")
    worker_descriptor = tmp_path / "worker.json"
    index = PluginIndex.parse(
        {
            "schema": 2,
            "bundles": [
                {
                    "id": "example.echo",
                    "version": "1.0.0",
                    "display_name": "Example Echo",
                    "summary": "A bounded fixture.",
                    "publisher": {
                        "id": "example",
                        "name": "Example Publisher",
                        "url": "https://example.invalid/publisher",
                    },
                    "license": {"expression": "MIT"},
                    "repository": "https://example.invalid/repository",
                    "homepage": "https://example.invalid/home",
                    "status": "active",
                    "dependencies": [],
                    "facets": [
                        {
                            "runtime_kind": "v6",
                            "artifacts": [
                                {
                                    "url": "https://example.invalid/echo.zip",
                                    "sha256": "a" * 64,
                                    "bytes": 12,
                                }
                            ],
                            "wheels": [],
                            "platform": {"systems": [], "machines": [], "pythons": []},
                            "load": {"modules": ["example_echo"]},
                            "capabilities": ["runtime.events.receive"],
                        }
                    ],
                }
            ],
        }
    )
    monkeypatch.setattr(PluginSourceStore, "fetch", lambda _self, _source, refresh: index)
    monkeypatch.setattr(
        "liteyukibot.daemon.BridgeCatalog.discover",
        lambda _self: {"v6": SimpleNamespace(grade=SimpleNamespace(value="stable"))},
    )

    async def snapshot(_request: object) -> dict[str, object]:
        return {
            "topology": {
                "bridges": [
                    {"id": "v6-primary", "kind": "v6", "state": "configured"},
                ]
            }
        }

    worker = ControlServer(
        worker_descriptor,
        status_provider=lambda: {"state": "ready"},
        handlers={"daemon.webui.snapshot": snapshot},
    )
    await worker.start()
    daemon = InstanceDaemon(
        paths,
        DaemonSettings(),
        (sys.executable, "-c", "pass"),
        {},
        worker_descriptor=worker_descriptor,
        webui=WebUISettings(mode="on_demand"),
    )
    daemon._bridge_kinds = {"v6-primary": "v6"}
    try:
        principal = await daemon.redeem_ticket(await daemon.issue_ticket())
        assert principal is not None
        bootstrap = cast(dict[str, Any], await daemon.bootstrap(principal))
        assert bootstrap["first_run"] is False
        graph = cast(dict[str, Any], await daemon.topology_graph(principal))
        assert graph["nodes"][1] == {
            "id": "bridge:v6-primary",
            "kind": "bridge",
            "label": "v6-primary",
            "state": "configured",
            "metadata": {"kind": "v6"},
        }
        discovery = cast(
            dict[str, Any],
            await daemon.plugin_discovery(principal, "echo", None, "v6", "active", False, None, 20),
        )
        assert discovery["items"][0]["bundle_id"] == "example.echo"
        assert discovery["items"][0]["download_bytes"] == 12
        assert discovery["sources"][0]["official"] is True

        targets = cast(dict[str, Any], await daemon.plugin_targets(principal))
        assert targets["items"][0]["id"] == "v6-primary"
        assert targets["items"][0]["state"] == "configured"
        preview = cast(
            dict[str, Any],
            await daemon.plugin_preview(principal, "example.echo", "liteyukibot-v7-plugins", "v6-primary"),
        )
        assert preview["selected_target"]["kind"] == "v6"
        assert preview["requested_capabilities"] == ["runtime.events.receive"]
        assert preview["download_bytes"] == 12
        assert "artifacts" not in preview["bundle"]
        assert "load_plan" not in preview
        assert "credentials_exposed" in preview["security"]
    finally:
        await daemon.operations.close()
        await worker.stop()


@pytest.mark.asyncio
async def test_daemon_projects_broker_diagnostics_without_exposing_broker_wire_fields(tmp_path: Path) -> None:
    paths = InstancePaths.from_workspace(ConfigWorkspace(tmp_path), "broker-ui")
    daemon = InstanceDaemon(paths, DaemonSettings(), (sys.executable, "-c", "pass"), {})

    class Diagnostics:
        async def status(self) -> object:
            return SimpleNamespace(
                generation=3,
                active_events=1,
                active_capacity=16,
                terminal_events=2,
                terminal_capacity=64,
                terminal_content_bytes=1_024,
                terminal_content_bytes_capacity=4_096,
                sessions=("astrbot",),
            )

        async def list_events(self, **_kwargs: object) -> object:
            return SimpleNamespace(
                events=(
                    SimpleNamespace(
                        event_id="event-1",
                        topic="message.created",
                        source_bridge_id="astrbot",
                        ordering_key="hmac:order",
                        status="active",
                        delivery_count=1,
                        failure_count=0,
                        failure_codes=(),
                    ),
                ),
                next_cursor=None,
            )

        async def detail(self, _event_id: str) -> object:
            return SimpleNamespace(
                event=SimpleNamespace(
                    event_id="event-1",
                    topic="message.created",
                    source_bridge_id="astrbot",
                    ordering_key="hmac:order",
                    status="settled",
                    delivery_count=1,
                    failure_count=1,
                    failure_codes=("bridge_failed",),
                    targets=("nonebot",),
                ),
                transitions=(
                    SimpleNamespace(
                        elapsed_ms=5,
                        kind="delivery.completed",
                        state="failed",
                        success=False,
                        target_bridge_id="nonebot",
                        failure_code="bridge_failed",
                    ),
                ),
            )

    daemon._broker_diagnostics = Diagnostics()  # type: ignore[assignment]
    page = await daemon.event_deliveries(None, {"topic": "message.created"}, None, 20)
    detail = await daemon.event_delivery(None, "event-1")

    assert page["broker"] == {
        "state": "ready",
        "generation": 3,
        "active": 1,
        "active_capacity": 16,
        "terminal": 2,
        "terminal_capacity": 64,
        "terminal_content_bytes": 1_024,
        "terminal_content_bytes_capacity": 4_096,
        "bridges": [{"id": "astrbot", "state": "connected", "session_state": "registered"}],
    }
    assert page["items"] == [
        {
            "id": "event-1",
            "topic": "message.created",
            "source": "astrbot",
            "ordering_key": "hmac:order",
            "status": "active",
            "target_count": 1,
            "failed_count": 0,
            "failure_code": None,
        }
    ]
    assert detail == {
        "id": "event-1",
        "topic": "message.created",
        "source": "astrbot",
        "ordering_key": "hmac:order",
        "status": "settled",
        "target_count": 1,
        "failed_count": 1,
        "failure_code": "bridge_failed",
        "deliveries": [{"target": "nonebot", "state": "settled"}],
        "timeline": [
            {
                "at": "5ms",
                "phase": "delivery.completed",
                "state": "failed",
                "target": "nonebot",
                "code": "bridge_failed",
            }
        ],
    }
    await daemon.operations.close()


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
