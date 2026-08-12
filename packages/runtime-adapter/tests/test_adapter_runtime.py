from __future__ import annotations

import json
from pathlib import Path

import pytest
from liteyukibot_runtime_adapter.contracts import AdapterConnection, AdapterContext, AdapterPlugin
from liteyukibot_runtime_adapter.host import AdapterHost, managed_adapter_names

from liteyukibot.events import ActionEnvelope, ConversationRef, EventEnvelope, Message, SendMessage
from liteyukibot.runtime.protocol import ActionRequest, EventMessage


class FakeClient:
    runtime_id = "platform"

    def __init__(self) -> None:
        self.sent: list[object] = []

    async def send(self, message: object) -> None:
        self.sent.append(message)


class FakeConnection:
    def __init__(self) -> None:
        self.emitter: object | None = None
        self.actions: list[ActionEnvelope] = []
        self.closed = False

    async def start(self, emit: object) -> None:
        self.emitter = emit

    async def execute(self, action: ActionEnvelope) -> str:
        self.actions.append(action)
        return "sent"

    async def close(self) -> None:
        self.closed = True


def _plugin(connection: FakeConnection) -> AdapterPlugin:
    async def create(_context: AdapterContext) -> AdapterConnection:
        return connection

    return AdapterPlugin("example", create)


@pytest.mark.asyncio
async def test_adapter_host_routes_owned_events_and_actions() -> None:
    client = FakeClient()
    connection = FakeConnection()
    host = AdapterHost(client, {"example": _plugin(connection)})  # type: ignore[arg-type]
    await host.start({"adapters": {"example-main": {"kind": "example", "bot_id": "bot", "config": {}}}})

    event = EventEnvelope(
        id="event-1",
        runtime_id="platform",
        adapter="example",
        bot_id="bot",
        type="message.created",
        conversation=ConversationRef(id="conversation", type="private"),
        message=Message(),
    )
    await host.emit("bot", event)
    response = await host.execute(
        ActionRequest(
            correlation_id="action-1",
            payload=ActionEnvelope(
                action_id="action-1",
                runtime_id="platform",
                bot_id="bot",
                action=SendMessage(
                    message=Message(),
                    conversation=ConversationRef(id="conversation", type="private"),
                ),
            ).model_dump(mode="json"),
        )
    )

    assert isinstance(client.sent[0], EventMessage)
    assert response.ok
    assert response.data == "sent"
    assert connection.actions[0].bot_id == "bot"
    await host.close()
    assert connection.closed


def test_managed_adapter_names_rejects_duplicates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "load-plan.json").write_text(json.dumps({"adapters": ["example", "example"]}), encoding="utf-8")
    monkeypatch.setenv("LITEYUKI_RUNTIME_GENERATION_DIR", str(tmp_path))

    with pytest.raises(RuntimeError, match="repeats"):
        managed_adapter_names()


def test_managed_adapter_names_reads_safe_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "load-plan.json").write_text(json.dumps({"adapters": ["onebot-v11"]}), encoding="utf-8")
    monkeypatch.setenv("LITEYUKI_RUNTIME_GENERATION_DIR", str(tmp_path))

    assert managed_adapter_names() == ("onebot-v11",)
