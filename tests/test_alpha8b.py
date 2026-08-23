from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, cast
from zipfile import ZipFile

import pytest
from liteyuki_devcli.cli import main as devcli_main
from scripts.build_lyf_vsix import GRAMMAR, build

from liteyukibot.broker.peer import BrokerPeerService
from liteyukibot.broker.protocol import (
    BridgeAccess,
    BridgeManifest,
    BridgeRegister,
    BridgeRegistered,
    BrokerLifecycleFreeze,
    BrokerLifecycleStatusResult,
    BrokerLifecycleUnfreeze,
    decode_broker_message,
    encode_broker_message,
)
from liteyukibot.broker.routing import BrokerAdmissionError
from liteyukibot.config import ConfigWorkspace, DaemonSettings
from liteyukibot.daemon import InstanceDaemon
from liteyukibot.instances import InstancePaths
from liteyukibot.managed_graph import ManagedProcessGraph, ProcessLike, ProcessSpec
from liteyukibot.profiles import ProfileManifest, ProfileStore
from liteyukibot.update import UpdateError, UpdateJournal, UpdatePhase


class _FakeProcess:
    def __init__(self, pid: int, events: list[str]) -> None:
        self._pid = pid
        self._events = events
        self._returncode: int | None = None

    @property
    def pid(self) -> int:
        return self._pid

    @property
    def returncode(self) -> int | None:
        return self._returncode

    def terminate(self) -> None:
        self._events.append(f"terminate:{self._pid}")
        self._returncode = 0

    def kill(self) -> None:
        self._events.append(f"kill:{self._pid}")
        self._returncode = -9

    async def wait(self) -> int:
        self._events.append(f"wait:{self._pid}")
        return self._returncode or 0


@pytest.mark.asyncio
async def test_managed_process_graph_starts_and_stops_in_dependency_order() -> None:
    events: list[str] = []
    next_pid = 100

    async def launch(spec: ProcessSpec) -> ProcessLike:
        nonlocal next_pid
        events.append(f"start:{spec.name}")
        next_pid += 1
        return _FakeProcess(next_pid, events)

    graph = ManagedProcessGraph(
        (
            ProcessSpec("broker", ("broker",), {}),
            ProcessSpec("bridge:nonebot", ("bridge",), {}),
            ProcessSpec("kernel", ("kernel",), {}),
        ),
        launcher=launch,
    )

    await graph.start()
    assert graph.start_order == ("broker", "bridge:nonebot", "kernel")
    assert [item for item in events if item.startswith("start:")] == [
        "start:broker",
        "start:bridge:nonebot",
        "start:kernel",
    ]

    await graph.stop()
    assert [item for item in events if item.startswith("terminate:")] == [
        "terminate:103",
        "terminate:102",
        "terminate:101",
    ]


def test_update_journal_is_durable_and_monotonic(tmp_path: Path) -> None:
    journal = UpdateJournal(tmp_path / "update.json", instance="dev")
    operation_id = journal.begin(candidate_profile="candidate", previous_profile="active")

    assert operation_id
    journal.transition(UpdatePhase.STAGED)
    with pytest.raises(UpdateError, match="cannot move"):
        journal.transition(UpdatePhase.VERIFIED)

    recovered = journal.recover(reason="test restart recovery")
    assert recovered["phase"] == UpdatePhase.RECOVERED.value
    assert journal.is_terminal(recovered)
    assert journal.load() == recovered


def test_broker_lifecycle_freeze_blocks_business_admission() -> None:
    service = BrokerPeerService(
        instance_tokens={"bridge": "bridge-token"},
        generation=1,
        management_token="management-token",
    )
    peer = b"bridge-peer"
    freeze_frame = encode_broker_message(
        BrokerLifecycleFreeze(token="management-token", reason="test update"),
        generation=1,
        stream_id="broker:lifecycle:control",
        sequence=0,
        lease_id="lifecycle",
    )
    freeze_reply = decode_broker_message(service.handle_control(b"daemon", freeze_frame))
    assert isinstance(freeze_reply, BrokerLifecycleStatusResult)
    assert freeze_reply.frozen is True

    manifest = BridgeManifest(bridge_id="bridge", access=BridgeAccess.LIMITED)
    register_frame = encode_broker_message(
        BridgeRegister(bridge_id="bridge", instance_token="bridge-token", manifest=manifest),
        generation=1,
        stream_id="bridge:bridge:control",
        sequence=0,
        lease_id="registration",
    )
    registered = decode_broker_message(service.handle_control(peer, register_frame))
    assert isinstance(registered, BridgeRegistered)

    from liteyukibot.broker.business import encode_business_message
    from liteyukibot.broker.routing import EventIngress

    event_frame = encode_business_message(
        EventIngress(source_event_id="source-1", topic="message.created", ordering_key="conversation-1"),
        generation=1,
        stream_id=f"bridge:bridge:{registered.session_id}:business",
        sequence=0,
        lease_id="event",
    )
    with pytest.raises(BrokerAdmissionError) as error:
        service.handle_business(peer, event_frame)
    assert error.value.code == "admission_frozen"

    unfreeze_frame = encode_broker_message(
        BrokerLifecycleUnfreeze(token="management-token"),
        generation=1,
        stream_id="broker:lifecycle:control",
        sequence=1,
        lease_id="lifecycle",
    )
    unfreeze_reply = decode_broker_message(service.handle_control(b"daemon", unfreeze_frame))
    assert isinstance(unfreeze_reply, BrokerLifecycleStatusResult)
    assert unfreeze_reply.frozen is False


def _write_profile(store: ProfileStore, profile_id: str) -> None:
    profile = store.profile_path(profile_id)
    python = ProfileStore.python_path(profile)
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text("", encoding="utf-8")
    store.write_manifest(
        ProfileManifest(
            id=profile_id,
            created_at="2026-08-21T00:00:00+00:00",
            requirements=("liteyukibot-v7==7.0.0a12",),
            python=str(python),
            distributions={"liteyukibot-v7": "7.0.0a12"},
            direct_urls={},
            config_version=6,
            bundle_tag="v7.0.0a12",
            bundle_version="7.0.0a12",
            bundle_manifest_sha256="a" * 64,
            dependency_lock_sha256="b" * 64,
            artifact_filenames=(),
        )
    )


class _Lifecycle:
    def __init__(self, *, active_events: int = 0) -> None:
        self.active_events = active_events
        self.calls: list[str] = []

    async def freeze(self, _reason: str) -> BrokerLifecycleStatusResult:
        self.calls.append("freeze")
        return BrokerLifecycleStatusResult(frozen=True, active_events=self.active_events)

    async def drain(self) -> BrokerLifecycleStatusResult:
        self.calls.append("drain")
        return BrokerLifecycleStatusResult(frozen=True, active_events=self.active_events)

    async def unfreeze(self) -> BrokerLifecycleStatusResult:
        self.calls.append("unfreeze")
        return BrokerLifecycleStatusResult(frozen=False, active_events=self.active_events)


def _daemon_with_profiles(
    tmp_path: Path,
    events: list[str],
    *,
    settings: DaemonSettings | None = None,
    orphan_process_terminator: Any | None = None,
) -> tuple[InstanceDaemon, ProfileStore]:
    paths = InstancePaths.from_workspace(ConfigWorkspace(tmp_path), "dev")
    store = ProfileStore(tmp_path)
    _write_profile(store, "active")
    _write_profile(store, "candidate")
    store.activate("active")

    next_pid = 200

    async def launch(spec: ProcessSpec) -> ProcessLike:
        nonlocal next_pid
        next_pid += 1
        events.append(f"start:{spec.name}")
        return _FakeProcess(next_pid, events)

    daemon = InstanceDaemon(
        paths,
        settings or DaemonSettings(startup_timeout_seconds=1, stop_timeout_seconds=1),
        (sys.executable, "-c", "pass"),
        {},
        broker_command=(sys.executable, "-c", "pass"),
        bridge_commands={"nonebot": (sys.executable, "-c", "pass")},
        process_launcher=launch,
        orphan_process_terminator=orphan_process_terminator,
    )
    return daemon, store


@pytest.mark.asyncio
async def test_daemon_update_commits_after_restarting_the_whole_graph(tmp_path: Path) -> None:
    events: list[str] = []
    daemon, store = _daemon_with_profiles(tmp_path, events)
    lifecycle = _Lifecycle()
    daemon._broker_lifecycle = cast(Any, lifecycle)

    async def freeze_kernel() -> None:
        return None

    async def wait_healthy() -> None:
        return None

    daemon._freeze_kernel = freeze_kernel  # type: ignore[method-assign]
    daemon._wait_kernel_healthy = wait_healthy  # type: ignore[method-assign]
    try:
        await daemon._start_worker()
        result = await daemon._update_profile("candidate")

        assert result["phase"] == UpdatePhase.COMMITTED.value
        assert store.active() == "candidate"
        assert lifecycle.calls[:2] == ["freeze", "drain"]
        assert [item for item in events if item.startswith("terminate:")] == [
            "terminate:203",
            "terminate:202",
            "terminate:201",
        ]
        assert daemon.update_journal.load()["phase"] == UpdatePhase.COMMITTED.value  # type: ignore[index]
    finally:
        await daemon._terminate_worker()
        await daemon.operations.close()


@pytest.mark.asyncio
async def test_daemon_update_rolls_back_when_candidate_health_fails(tmp_path: Path) -> None:
    events: list[str] = []
    daemon, store = _daemon_with_profiles(tmp_path, events)
    lifecycle = _Lifecycle()
    daemon._broker_lifecycle = cast(Any, lifecycle)
    health_calls = 0

    async def freeze_kernel() -> None:
        return None

    async def wait_healthy() -> None:
        nonlocal health_calls
        health_calls += 1
        if health_calls == 1:
            raise UpdateError("candidate health failed")

    daemon._freeze_kernel = freeze_kernel  # type: ignore[method-assign]
    daemon._wait_kernel_healthy = wait_healthy  # type: ignore[method-assign]
    try:
        await daemon._start_worker()
        with pytest.raises(UpdateError, match="candidate health failed"):
            await daemon._update_profile("candidate")

        assert store.active() == "active"
        assert daemon.update_journal.load()["phase"] == UpdatePhase.ROLLED_BACK.value  # type: ignore[index]
        assert lifecycle.calls[-1] == "unfreeze"
    finally:
        await daemon._terminate_worker()
        await daemon.operations.close()


@pytest.mark.asyncio
async def test_daemon_update_aborts_and_unfreezes_when_drain_times_out(tmp_path: Path) -> None:
    events: list[str] = []
    daemon, store = _daemon_with_profiles(
        tmp_path,
        events,
        settings=DaemonSettings(
            startup_timeout_seconds=1,
            stop_timeout_seconds=1,
            drain_timeout_seconds=0.01,
        ),
    )
    lifecycle = _Lifecycle(active_events=1)
    daemon._broker_lifecycle = cast(Any, lifecycle)

    async def freeze_kernel() -> None:
        raise AssertionError("kernel must not freeze before drain completes")

    daemon._freeze_kernel = freeze_kernel  # type: ignore[method-assign]
    try:
        with pytest.raises(UpdateError, match="drain timed out"):
            await daemon._update_profile("candidate")
        assert store.active() == "active"
        assert daemon.update_journal.load()["phase"] == UpdatePhase.ABORTED.value  # type: ignore[index]
        assert "unfreeze" in lifecycle.calls
    finally:
        await daemon.operations.close()


@pytest.mark.asyncio
async def test_daemon_recovers_to_previous_profile_after_restart(tmp_path: Path) -> None:
    daemon, store = _daemon_with_profiles(tmp_path, [])
    try:
        store.activate("candidate")
        daemon.update_journal.begin(candidate_profile="candidate", previous_profile="active")
        daemon.update_journal.transition(UpdatePhase.STAGED)

        await daemon._recover_interrupted_update()

        assert store.active() == "active"
        assert daemon.update_journal.load()["phase"] == UpdatePhase.RECOVERED.value  # type: ignore[index]
    finally:
        await daemon.operations.close()


@pytest.mark.asyncio
async def test_daemon_recovery_stops_journaled_candidate_and_previous_graphs(tmp_path: Path) -> None:
    stopped: list[int] = []

    async def terminate(pid: int) -> None:
        stopped.append(pid)

    daemon, store = _daemon_with_profiles(tmp_path, [], orphan_process_terminator=terminate)

    def graph(pids: tuple[int, int, int]) -> dict[str, object]:
        return {
            "managed": True,
            "start_order": ["broker", "bridge:nonebot", "kernel"],
            "stop_order": ["kernel", "bridge:nonebot", "broker"],
            "processes": {
                "broker": {"pid": pids[0], "returncode": None},
                "bridge:nonebot": {"pid": pids[1], "returncode": None},
                "kernel": {"pid": pids[2], "returncode": None},
            },
        }

    try:
        store.activate("candidate")
        daemon.update_journal.begin(candidate_profile="candidate", previous_profile="active")
        daemon.update_journal.transition(
            UpdatePhase.STAGED,
            detail={"role": "previous", "graph": graph((301, 302, 303))},
        )
        daemon.update_journal.transition(UpdatePhase.PROFILE_SWITCHED, detail={"profile_id": "candidate"})
        daemon.update_journal.transition(
            UpdatePhase.STARTING,
            detail={"role": "candidate", "graph": graph((401, 402, 403))},
        )

        await daemon._recover_interrupted_update()

        assert stopped == [403, 402, 401, 303, 302, 301]
        assert store.active() == "active"
        active_python = str(ProfileStore.python_path(store.profile_path("active")).resolve())
        assert daemon._graph.specs[0].command[0] == active_python
        recovered = daemon.update_journal.load()
        assert recovered is not None
        assert recovered["phase"] == UpdatePhase.RECOVERED.value
        assert "stopped 6 recorded process(es)" in recovered["error"]  # type: ignore[operator]
    finally:
        await daemon.operations.close()


def test_devcli_outputs_read_only_lyf_diagnostics_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "broken.lyf"
    source.write_text("fn {\n", encoding="utf-8")

    assert devcli_main(["lyf", "diagnose", str(source), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["diagnostics"]


def test_vsix_contains_the_shared_lyf_grammar(tmp_path: Path) -> None:
    output = build(tmp_path / "liteyuki-lyf.vsix")

    with ZipFile(output) as archive:
        assert json.loads(archive.read("extension/package.json"))["version"] == "0.8.0"
        assert archive.read("extension/syntaxes/lyf.tmLanguage.json") == GRAMMAR.read_bytes()
        assert "extension/language-configuration.json" in archive.namelist()
