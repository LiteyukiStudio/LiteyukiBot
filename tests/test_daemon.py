from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from liteyukibot.config import ConfigWorkspace, DaemonSettings
from liteyukibot.control import request_control
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
