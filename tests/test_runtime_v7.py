from __future__ import annotations

import asyncio
import importlib.util
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

import pytest

from liteyukibot.runtime import RuntimeSpec, RuntimeState, RuntimeSupervisor
from liteyukibot.runtime.protocol import (
    ActionRequest,
    ActionResponse,
    ConfigMessage,
    EventAccepted,
    EventMessage,
    Hello,
    ProtocolVersion,
    Ready,
    Welcome,
    read_message,
    write_message,
)
from liteyukibot.runtime.supervisor import ActionSinkResult, RuntimeRecord


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


class NullWriter:
    def write(self, _value: bytes) -> None:
        return None

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None


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

    event_result = await supervisor.dispatch_event("echo", "event-1", {"message": "hello"})
    assert event_result == EventAccepted(correlation_id="event-1", status="accepted")

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
async def test_runtime_negotiates_v1_v2_and_v3_connections_concurrently() -> None:
    supervisor = RuntimeSupervisor(logger=FakeLogger())
    supervisor.add(RuntimeSpec(id="legacy", kind="custom"))
    supervisor.add(RuntimeSpec(id="modern", kind="custom"))
    supervisor.add(RuntimeSpec(id="current", kind="custom"))
    legacy = supervisor.records["legacy"]
    modern = supervisor.records["modern"]
    current = supervisor.records["current"]
    server = await asyncio.start_server(supervisor._accept, "127.0.0.1", 0)
    port = int(server.sockets[0].getsockname()[1])
    legacy_reader, legacy_writer = await asyncio.open_connection("127.0.0.1", port)
    modern_reader, modern_writer = await asyncio.open_connection("127.0.0.1", port)
    current_reader, current_writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        await write_message(
            legacy_writer,
            Hello(protocol=1, runtime_id="legacy", kind="custom", token=legacy.token),
        )
        assert await read_message(legacy_reader) == Welcome(protocol=1)
        assert isinstance(await read_message(legacy_reader), ConfigMessage)
        await write_message(legacy_writer, Ready(capabilities=("runtime.events.receive",)))

        await write_message(
            modern_writer,
            Hello(protocol=2, runtime_id="modern", kind="custom", token=modern.token),
        )
        assert await read_message(modern_reader) == Welcome(protocol=2)
        assert isinstance(await read_message(modern_reader), ConfigMessage)
        await write_message(modern_writer, Ready(capabilities=("runtime.events.receive",)))
        await write_message(
            current_writer,
            Hello(protocol=3, runtime_id="current", kind="custom", token=current.token),
        )
        assert await read_message(current_reader) == Welcome(protocol=3)
        assert isinstance(await read_message(current_reader), ConfigMessage)
        await write_message(current_writer, Ready(capabilities=("runtime.events.receive",)))
        await asyncio.wait_for(
            asyncio.gather(legacy.ready.wait(), modern.ready.wait(), current.ready.wait()),
            timeout=1,
        )

        assert legacy.protocol_version == 1
        assert modern.protocol_version == 2
        assert current.protocol_version == 3
        with pytest.raises(RuntimeError, match="did not negotiate protocol v2 or v3"):
            await supervisor.dispatch_event("legacy", "event-v1", {})

        delivery = asyncio.create_task(
            supervisor.dispatch_event("modern", "event-v2", {"message": "hello"})
        )
        outbound = await asyncio.wait_for(read_message(modern_reader), timeout=1)
        assert outbound == EventMessage(
            correlation_id="event-v2",
            payload={"message": "hello"},
        )
        await write_message(
            modern_writer,
            EventAccepted(correlation_id="event-v2", status="accepted"),
        )
        assert (await delivery).status == "accepted"

        current_delivery = asyncio.create_task(
            supervisor.dispatch_event("current", "event-v3", {"message": "hello"})
        )
        current_outbound = await asyncio.wait_for(read_message(current_reader), timeout=1)
        assert current_outbound == EventMessage(
            correlation_id="event-v3",
            payload={"message": "hello"},
        )
        await write_message(
            current_writer,
            EventAccepted(correlation_id="event-v3", status="accepted"),
        )
        assert (await current_delivery).status == "accepted"
    finally:
        legacy_writer.close()
        modern_writer.close()
        current_writer.close()
        await legacy_writer.wait_closed()
        await modern_writer.wait_closed()
        await current_writer.wait_closed()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_v3_child_action_reaches_core_sink_with_correlation() -> None:
    observed: list[tuple[str, dict[str, Any]]] = []

    async def execute_child_action(
        runtime_id: str, payload: dict[str, Any]
    ) -> ActionSinkResult:
        observed.append((runtime_id, payload))
        return ActionSinkResult(ok=True, data={"message_id": "sent-1"})

    supervisor = RuntimeSupervisor(
        logger=FakeLogger(),
        action_sink=execute_child_action,
    )
    supervisor.add(RuntimeSpec(id="compat", kind="custom"))
    record = supervisor.records["compat"]
    server = await asyncio.start_server(supervisor._accept, "127.0.0.1", 0)
    port = int(server.sockets[0].getsockname()[1])
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        await write_message(
            writer,
            Hello(protocol=3, runtime_id="compat", kind="custom", token=record.token),
        )
        assert await read_message(reader) == Welcome(protocol=3)
        assert isinstance(await read_message(reader), ConfigMessage)
        await write_message(writer, Ready(capabilities=("runtime.actions.send",)))
        await asyncio.wait_for(record.ready.wait(), timeout=1)

        await write_message(
            writer,
            ActionRequest(correlation_id="reply-1", payload={"type": "send_message"}),
        )
        response = await asyncio.wait_for(read_message(reader), timeout=1)

        assert response == ActionResponse(
            correlation_id="reply-1",
            ok=True,
            data={"message_id": "sent-1"},
        )
        assert observed == [("compat", {"type": "send_message"})]
    finally:
        writer.close()
        await writer.wait_closed()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("protocol_version", "capabilities", "with_sink", "error"),
    [
        (1, frozenset({"runtime.actions.send"}), True, "require runtime protocol v3"),
        (2, frozenset({"runtime.actions.send"}), True, "require runtime protocol v3"),
        (3, frozenset(), True, "did not declare runtime.actions.send"),
        (3, frozenset({"runtime.actions.send"}), False, "action sink is unavailable"),
    ],
)
async def test_child_action_requires_v3_capability_and_sink(
    monkeypatch: pytest.MonkeyPatch,
    protocol_version: ProtocolVersion,
    capabilities: frozenset[str],
    with_sink: bool,
    error: str,
) -> None:
    async def sink(_runtime_id: str, _payload: dict[str, Any]) -> ActionSinkResult:
        return ActionSinkResult(ok=True)

    supervisor = RuntimeSupervisor(
        logger=FakeLogger(),
        action_sink=sink if with_sink else None,
    )
    record = RuntimeRecord(
        spec=RuntimeSpec(id="compat", kind="custom"),
        token="token",
        state=RuntimeState.READY,
        writer=NullWriter(),  # type: ignore[arg-type]
        protocol_version=protocol_version,
        capabilities=capabilities,
    )
    responses: list[ActionResponse] = []

    async def capture(_record: RuntimeRecord, message: Any) -> None:
        assert isinstance(message, ActionResponse)
        responses.append(message)

    monkeypatch.setattr(supervisor, "_send", capture)
    await supervisor._handle_message(
        record,
        ActionRequest(correlation_id="reply-1", payload={}),
    )

    assert len(responses) == 1
    assert responses[0].correlation_id == "reply-1"
    assert responses[0].ok is False
    assert responses[0].error is not None and error in responses[0].error
    assert record.inbound_actions == {}


@pytest.mark.asyncio
async def test_child_action_sink_failure_is_isolated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail(_runtime_id: str, _payload: dict[str, Any]) -> ActionSinkResult:
        raise RuntimeError("adapter failed")

    supervisor = RuntimeSupervisor(logger=FakeLogger(), action_sink=fail)
    record = RuntimeRecord(
        spec=RuntimeSpec(id="compat", kind="custom"),
        token="token",
        state=RuntimeState.READY,
        writer=NullWriter(),  # type: ignore[arg-type]
        protocol_version=3,
        capabilities=frozenset({"runtime.actions.send"}),
    )
    response_seen = asyncio.Event()
    responses: list[ActionResponse] = []

    async def capture(_record: RuntimeRecord, message: Any) -> None:
        assert isinstance(message, ActionResponse)
        responses.append(message)
        response_seen.set()

    monkeypatch.setattr(supervisor, "_send", capture)
    await supervisor._handle_message(
        record,
        ActionRequest(correlation_id="reply-1", payload={}),
    )
    await asyncio.wait_for(response_seen.wait(), timeout=1)

    assert responses == [
        ActionResponse(
            correlation_id="reply-1",
            ok=False,
            error="core action sink failed",
        )
    ]
    assert record.inbound_actions == {}


@pytest.mark.asyncio
async def test_duplicate_child_action_is_rejected_and_disconnect_cancels_sink(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def hold(_runtime_id: str, _payload: dict[str, Any]) -> ActionSinkResult:
        started.set()
        try:
            await asyncio.Future()
            return ActionSinkResult(ok=True)
        finally:
            cancelled.set()

    supervisor = RuntimeSupervisor(logger=FakeLogger(), action_sink=hold)
    record = RuntimeRecord(
        spec=RuntimeSpec(id="compat", kind="custom"),
        token="token",
        state=RuntimeState.READY,
        writer=NullWriter(),  # type: ignore[arg-type]
        protocol_version=3,
        capabilities=frozenset({"runtime.actions.send"}),
    )
    responses: list[ActionResponse] = []

    async def capture(_record: RuntimeRecord, message: Any) -> None:
        assert isinstance(message, ActionResponse)
        responses.append(message)

    monkeypatch.setattr(supervisor, "_send", capture)
    request = ActionRequest(correlation_id="duplicate", payload={})
    await supervisor._handle_message(record, request)
    await asyncio.wait_for(started.wait(), timeout=1)
    await supervisor._handle_message(record, request)

    assert len(responses) == 1
    assert responses[0].ok is False
    assert responses[0].error == "duplicate action correlation id: duplicate"

    await supervisor._disconnect(record)

    assert cancelled.is_set()
    assert record.inbound_actions == {}


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
async def test_event_delivery_timeout_removes_pending_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supervisor = RuntimeSupervisor(logger=FakeLogger())
    record = RuntimeRecord(
        spec=RuntimeSpec(id="event", kind="custom"),
        token="token",
        state=RuntimeState.READY,
        writer=NullWriter(),  # type: ignore[arg-type]
        protocol_version=2,
        capabilities=frozenset({"runtime.events.receive"}),
    )
    supervisor.records[record.spec.id] = record

    async def ignore_event(_record: RuntimeRecord, _message: Any) -> None:
        return None

    monkeypatch.setattr(supervisor, "_send", ignore_event)
    with pytest.raises(TimeoutError):
        await supervisor.dispatch_event("event", "request", {}, timeout_seconds=0.01)

    assert record.pending_events == {}


@pytest.mark.asyncio
async def test_v2_event_delivery_requires_receive_capability() -> None:
    supervisor = RuntimeSupervisor(logger=FakeLogger())
    record = RuntimeRecord(
        spec=RuntimeSpec(id="event", kind="custom"),
        token="token",
        state=RuntimeState.READY,
        writer=NullWriter(),  # type: ignore[arg-type]
        protocol_version=2,
    )
    supervisor.records[record.spec.id] = record

    with pytest.raises(RuntimeError, match="does not accept core events"):
        await supervisor.dispatch_event("event", "request", {})

    assert record.pending_events == {}


@pytest.mark.asyncio
async def test_event_delivery_returns_child_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    supervisor = RuntimeSupervisor(logger=FakeLogger())
    record = RuntimeRecord(
        spec=RuntimeSpec(id="event", kind="custom"),
        token="token",
        state=RuntimeState.READY,
        writer=NullWriter(),  # type: ignore[arg-type]
        protocol_version=2,
        capabilities=frozenset({"runtime.events.receive"}),
    )
    supervisor.records[record.spec.id] = record

    async def reject_event(_record: RuntimeRecord, message: Any) -> None:
        await supervisor._handle_message(
            record,
            EventAccepted(
                correlation_id=message.correlation_id,
                status="invalid",
                detail="unsupported event",
            ),
        )

    monkeypatch.setattr(supervisor, "_send", reject_event)
    result = await supervisor.dispatch_event("event", "request", {})

    assert result.status == "invalid"
    assert result.detail == "unsupported event"
    assert record.pending_events == {}


@pytest.mark.asyncio
async def test_duplicate_event_delivery_and_disconnect_are_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = asyncio.Event()
    supervisor = RuntimeSupervisor(logger=FakeLogger())
    record = RuntimeRecord(
        spec=RuntimeSpec(id="event", kind="custom"),
        token="token",
        state=RuntimeState.READY,
        writer=NullWriter(),  # type: ignore[arg-type]
        protocol_version=2,
        capabilities=frozenset({"runtime.events.receive"}),
    )
    supervisor.records[record.spec.id] = record

    async def hold_event(_record: RuntimeRecord, _message: Any) -> None:
        sent.set()

    monkeypatch.setattr(supervisor, "_send", hold_event)
    delivery = asyncio.create_task(supervisor.dispatch_event("event", "duplicate", {}))
    await sent.wait()
    with pytest.raises(ValueError, match="duplicate event correlation id"):
        await supervisor.dispatch_event("event", "duplicate", {})

    await supervisor._disconnect(record)
    with pytest.raises(ConnectionError, match="disconnected"):
        await delivery
    assert record.pending_events == {}


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


@pytest.mark.asyncio
async def test_duplicate_action_request_does_not_replace_pending_future(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = asyncio.Event()
    supervisor = RuntimeSupervisor(logger=FakeLogger())
    record = RuntimeRecord(
        spec=RuntimeSpec(id="action", kind="custom"),
        token="token",
        state=RuntimeState.READY,
        writer=NullWriter(),  # type: ignore[arg-type]
    )
    supervisor.records[record.spec.id] = record

    async def hold_action(_record: RuntimeRecord, _message: Any) -> None:
        sent.set()

    monkeypatch.setattr(supervisor, "_send", hold_action)
    first = asyncio.create_task(supervisor.execute_action("action", "duplicate", {}))
    await sent.wait()
    pending = record.pending_actions["duplicate"]

    with pytest.raises(ValueError, match="duplicate action correlation id"):
        await supervisor.execute_action("action", "duplicate", {})
    assert record.pending_actions["duplicate"] is pending

    await supervisor._disconnect(record)
    with pytest.raises(ConnectionError, match="disconnected"):
        await first
    assert record.pending_actions == {}


@pytest.mark.asyncio
async def test_runtime_dispatch_rejects_non_positive_timeouts_before_lookup() -> None:
    supervisor = RuntimeSupervisor(logger=FakeLogger())

    with pytest.raises(ValueError, match="action timeout must be positive"):
        await supervisor.execute_action("missing", "action", {}, timeout_seconds=0)
    with pytest.raises(ValueError, match="action timeout must be positive"):
        await supervisor.execute_action("missing", "action", {}, timeout_seconds=-1)
    with pytest.raises(ValueError, match="event timeout must be positive"):
        await supervisor.dispatch_event("missing", "event", {}, timeout_seconds=0)
    with pytest.raises(ValueError, match="event timeout must be positive"):
        await supervisor.dispatch_event("missing", "event", {}, timeout_seconds=-1)


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
