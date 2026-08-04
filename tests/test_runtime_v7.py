from __future__ import annotations

import asyncio
import importlib.util
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

import pytest

from liteyukibot.runtime import RuntimeSpec, RuntimeState, RuntimeSupervisor
from liteyukibot.runtime.protocol import Hello, write_message
from liteyukibot.runtime.supervisor import RuntimeRecord


class FakeLogger:
    def bind(self, **fields: Any) -> FakeLogger:
        return self

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        pass

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        pass

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        pass

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        pass


@pytest.mark.asyncio
async def test_noop_runtime_handshake_action_and_shutdown() -> None:
    supervisor = RuntimeSupervisor(logger=FakeLogger())
    supervisor.add(
        RuntimeSpec(
            id="echo",
            kind="noop",
            ready_timeout=5,
            heartbeat_interval=0.05,
            stale_after=1,
        )
    )

    await supervisor.start()
    assert supervisor.records["echo"].state.value == RuntimeState.READY

    result = await supervisor.execute_action("echo", "action-1", {"message": "hello"})
    assert result.ok is True
    assert result.data == {"echo": {"message": "hello"}}

    await supervisor.restart("echo")
    assert supervisor.records["echo"].state.value == RuntimeState.READY
    assert supervisor.records["echo"].launch_count == 2

    await supervisor.stop()
    assert supervisor.records["echo"].state.value == RuntimeState.STOPPED


@pytest.mark.asyncio
async def test_runtime_rejects_duplicate_ids() -> None:
    supervisor = RuntimeSupervisor(logger=FakeLogger())
    supervisor.add(RuntimeSpec(id="same", kind="noop"))
    with pytest.raises(ValueError, match="duplicate runtime id"):
        supervisor.add(RuntimeSpec(id="same", kind="noop"))


@pytest.mark.asyncio
async def test_runtime_spawn_failure_is_reported_without_waiting_for_ready_timeout() -> None:
    supervisor = RuntimeSupervisor(logger=FakeLogger())
    supervisor.add(
        RuntimeSpec(
            id="missing",
            kind="custom",
            command=("definitely-not-a-real-liteyuki-command",),
            restart_limit=1,
            ready_timeout=10,
        )
    )

    with pytest.raises(RuntimeError, match="failed before becoming ready"):
        await supervisor.start()


@pytest.mark.asyncio
async def test_runtime_rejects_bad_and_duplicate_connections() -> None:
    supervisor = RuntimeSupervisor(logger=FakeLogger())
    supervisor.add(
        RuntimeSpec(
            id="echo",
            kind="noop",
            ready_timeout=5,
            heartbeat_interval=0.05,
            stale_after=1,
        )
    )

    await supervisor.start()
    record = supervisor.records["echo"]
    for token in ("wrong", record.token):
        reader, writer = await asyncio.open_connection("127.0.0.1", supervisor._port)
        await write_message(writer, Hello(runtime_id="echo", kind="noop", token=token))
        assert await asyncio.wait_for(reader.read(), timeout=1) == b""
        writer.close()
        await writer.wait_closed()
        assert record.state is RuntimeState.READY

    await supervisor.stop()


@pytest.mark.asyncio
async def test_heartbeat_timeout_terminates_stale_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProcess:
        terminated = False

        def terminate(self) -> None:
            self.terminated = True

    supervisor = RuntimeSupervisor(logger=FakeLogger())
    record = RuntimeRecord(
        spec=RuntimeSpec(id="stale", kind="noop", heartbeat_interval=0.05, stale_after=0.1),
        token="token",
        state=RuntimeState.READY,
        last_heartbeat=time.monotonic() - 1,
    )
    process = FakeProcess()
    record.process = process  # type: ignore[assignment]
    supervisor.records[record.spec.id] = record
    sleeps = 0

    async def fake_sleep(_seconds: float) -> None:
        nonlocal sleeps
        sleeps += 1
        if sleeps > 1:
            raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    with suppress(asyncio.CancelledError):
        await supervisor._watch_heartbeats()

    assert process.terminated is True


@pytest.mark.asyncio
async def test_runtime_handshake_timeout_closes_unresponsive_client() -> None:
    supervisor = RuntimeSupervisor(logger=FakeLogger())
    supervisor.add(
        RuntimeSpec(
            id="slow",
            kind="custom",
            handshake_timeout=0.05,
            ready_timeout=1,
        )
    )
    server = await asyncio.start_server(supervisor._accept, "127.0.0.1", 0)
    supervisor._server = server
    supervisor._port = int(server.sockets[0].getsockname()[1])
    reader, writer = await asyncio.open_connection("127.0.0.1", supervisor._port)
    try:
        assert await asyncio.wait_for(reader.read(), timeout=1) == b""
    finally:
        writer.close()
        await writer.wait_closed()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_action_timeout_removes_pending_request(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeWriter:
        def write(self, _value: bytes) -> None:
            return None

        async def drain(self) -> None:
            return None

        def close(self) -> None:
            return None

        async def wait_closed(self) -> None:
            return None

    supervisor = RuntimeSupervisor(logger=FakeLogger())
    record = RuntimeRecord(
        spec=RuntimeSpec(id="action", kind="custom"),
        token="token",
        state=RuntimeState.READY,
        writer=FakeWriter(),  # type: ignore[arg-type]
    )
    supervisor.records[record.spec.id] = record

    async def ignore_action(_record: RuntimeRecord, _message: Any) -> None:
        return None

    monkeypatch.setattr(supervisor, "_send", ignore_action)
    with pytest.raises(TimeoutError):
        await supervisor.execute_action("action", "request", {}, timeout_seconds=0.01)

    assert record.pending_actions == {}


@pytest.mark.asyncio
async def test_disconnect_fails_pending_action(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeWriter:
        def write(self, _value: bytes) -> None:
            return None

        async def drain(self) -> None:
            return None

        def close(self) -> None:
            return None

        async def wait_closed(self) -> None:
            return None

    sent = asyncio.Event()
    supervisor = RuntimeSupervisor(logger=FakeLogger())
    record = RuntimeRecord(
        spec=RuntimeSpec(id="action", kind="custom"),
        token="token",
        state=RuntimeState.READY,
        writer=FakeWriter(),  # type: ignore[arg-type]
    )
    supervisor.records[record.spec.id] = record

    async def hold_action(_record: RuntimeRecord, _message: Any) -> None:
        sent.set()

    monkeypatch.setattr(supervisor, "_send", hold_action)
    action = asyncio.create_task(supervisor.execute_action("action", "request", {}))
    await sent.wait()
    await supervisor._disconnect(record)

    with pytest.raises(ConnectionError, match="disconnected"):
        await action
    assert record.pending_actions == {}


def test_runtime_failure_limit_transitions_to_failed() -> None:
    record = RuntimeRecord(
        spec=RuntimeSpec(id="crash", kind="custom", restart_limit=2),
        token="token",
    )

    assert RuntimeSupervisor._register_failure(record) is True
    assert RuntimeSupervisor._register_failure(record) is False
    assert record.state is RuntimeState.FAILED


@pytest.mark.asyncio
@pytest.mark.skipif(importlib.util.find_spec("nonebot") is None, reason="NoneBot extra is not installed")
async def test_nonebot_runtime_loads_an_existing_plugin(tmp_path: Path) -> None:
    (tmp_path / "nonebot_fixture.py").write_text(
        "from nonebot import on_message\nfixture = on_message()\n",
        encoding="utf-8",
    )
    supervisor = RuntimeSupervisor(logger=FakeLogger())
    supervisor.add(
        RuntimeSpec(
            id="nonebot",
            kind="nonebot",
            options={
                "config": {"driver": "~none"},
                "plugins": ["nonebot_fixture"],
            },
            working_directory=tmp_path,
            ready_timeout=10,
            heartbeat_interval=0.1,
            stale_after=2,
        )
    )

    await supervisor.start()
    assert supervisor.records["nonebot"].state.value == RuntimeState.READY
    await supervisor.stop()
    assert supervisor.records["nonebot"].state.value == RuntimeState.STOPPED
