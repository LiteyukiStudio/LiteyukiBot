from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from jsonschema import Draft202012Validator
from liteyukibot_runtime_astrbot import bridge_definition
from liteyukibot_runtime_astrbot.host import (
    MESSAGE_CREATED_TOPIC,
    AstrBotGateway,
    _runtime_api_declarations,
    _workspace_path,
)
from liteyukibot_runtime_astrbot.listener import configure_publisher, forward_native_event
from liteyukibot_runtime_astrbot.translate import to_event_envelope

from liteyukibot.broker import (
    ActionRequest,
    AuthorizationContextWire,
    EventIngress,
    MessageSendPayload,
    RuntimeApiInvoke,
)
from liteyukibot.config import AppSettings
from liteyukibot.events import ConversationRef, JsonValue, Message, Segment


class FakeAstrEvent:
    def __init__(self) -> None:
        self.message_obj = SimpleNamespace(message_id="message-1")
        self.sent: list[object] = []

    def get_platform_id(self) -> str:
        return "qq"

    def get_platform_name(self) -> str:
        return "aiocqhttp"

    def get_self_id(self) -> str:
        return "bot-1"

    def get_group_id(self) -> str:
        return "group-1"

    def get_session_id(self) -> str:
        return "session-1"

    def get_sender_id(self) -> str:
        return "user-1"

    def get_sender_name(self) -> str:
        return "User"

    def get_message_str(self) -> str:
        return "hello"

    def get_messages(self) -> list[object]:
        return [type("Plain", (), {"text": "hello"})()]

    def get_message_type(self) -> str:
        return "group"

    async def send(self, chain: object) -> dict[str, str]:
        self.sent.append(chain)
        return {"message_id": "reply-1"}


class RecordingLogger:
    def bind(self, **_fields: object) -> RecordingLogger:
        return self

    def warning(self, *_args: object) -> None:
        return None


def _settings(data_dir: Path) -> AppSettings:
    return AppSettings.model_validate({"config_version": 6, "core": {"data_dir": str(data_dir)}})


def _runtime_request(api_id: str, arguments: dict[str, JsonValue] | None = None) -> RuntimeApiInvoke:
    return RuntimeApiInvoke(
        delivery_id="delivery-1",
        source_event_id="message-1",
        lease_id="lease-1",
        correlation_id=f"runtime:{api_id}",
        runtime_kind="astrbot",
        version="^1.0",
        api_id=api_id,
        caller_extension_id="example.plugin",
        arguments=arguments or {},
        authorization=AuthorizationContextWire(
            event_id="message-1",
            runtime_id="astrbot",
            bot_id="bot-1",
            actor_id="user-1",
        ),
    )


def test_astrbot_runtime_catalog_contains_alpha9_portable_operations() -> None:
    declarations = _runtime_api_declarations()

    assert {(item.namespace, item.operation) for item in declarations} == {
        ("event", "snapshot"),
        ("event", "send"),
        ("bot", "snapshot"),
        ("bot", "send"),
    }
    assert all(item.version == "1.1" for item in declarations)
    snapshot_schema = next(item for item in declarations if item.api_id == "event.snapshot").output_schema
    Draft202012Validator(dict(snapshot_schema)).validate(AstrBotGateway._event_snapshot(FakeAstrEvent()))


def test_astrbot_bridge_declares_experimental_package_metadata() -> None:
    definition = bridge_definition()

    assert definition.kind == "astrbot"
    assert definition.grade == "experimental"
    assert definition.distribution == "liteyukibot-v7-runtime-astrbot"


def test_astrbot_ingress_projects_native_event_without_suppressing_pipeline() -> None:
    envelope = to_event_envelope(FakeAstrEvent(), reply_token="qq:message-1")

    assert envelope.id == "message-1"
    assert envelope.runtime_id == "astrbot"
    assert envelope.adapter == "aiocqhttp"
    assert envelope.conversation == ConversationRef(id="group-1", type="group")
    assert envelope.message == Message(segments=(Segment(type="text", data={"text": "hello"}),))
    assert envelope.reply_token == "qq:message-1"


def test_astrbot_event_snapshot_includes_portable_message_details() -> None:
    snapshot = AstrBotGateway._event_snapshot(FakeAstrEvent())

    assert snapshot["conversation_id"] == "group-1"
    assert snapshot["conversation_type"] == "group"
    assert cast(object, snapshot["message_segments"]) == [{"type": "text", "data": {"text": "hello"}}]


@pytest.mark.asyncio
async def test_astrbot_gateway_publishes_broker_ingress_and_retains_reply_route() -> None:
    published: list[object] = []

    async def send(ingress: object) -> None:
        published.append(ingress)

    gateway = AstrBotGateway(Path("workspace"), "astrbot", RecordingLogger())
    gateway._ingress_sink = send
    await gateway._publish_ingress(FakeAstrEvent())

    ingress = cast(EventIngress, published[0])
    assert ingress.topic == MESSAGE_CREATED_TOPIC
    assert ingress.ordering_key == "group:group-1"
    assert "qq:message-1" in gateway._reply_events
    assert gateway._bot_platforms == {"bot-1": "qq"}


@pytest.mark.asyncio
async def test_astrbot_public_star_listener_only_observes_native_events() -> None:
    observed: list[object] = []
    configure_publisher(observed.append)
    try:
        await forward_native_event(FakeAstrEvent())
    finally:
        configure_publisher(None)

    assert len(observed) == 1


def test_astrbot_gateway_installs_public_star_bootstrap_without_touching_user_plugins(tmp_path: Path) -> None:
    gateway = AstrBotGateway(tmp_path, "astrbot", RecordingLogger())

    gateway._install_star_plugin()

    plugin = tmp_path / "data" / "plugins" / "liteyuki_broker_ingress"
    source = (plugin / "main.py").read_text(encoding="utf-8")
    assert "@filter.event_message_type(EventMessageType.ALL)" in source
    assert (plugin / "metadata.yaml").is_file()


@pytest.mark.asyncio
async def test_astrbot_gateway_owns_message_send_for_retained_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = FakeAstrEvent()
    gateway = AstrBotGateway(Path("workspace"), "astrbot", RecordingLogger())
    gateway._reply_events["qq:message-1"] = ("bot-1", event)
    monkeypatch.setattr("liteyukibot_runtime_astrbot.host._to_astr_chain", lambda _message: "native-chain")
    request = ActionRequest(
        delivery_id="delivery-1",
        lease_id="lease-1",
        correlation_id="action-1",
        action_id="broker-action-1",
        kind="message.send",
        resource_key="bot:astrbot:bot-1",
        payload=cast(
            dict[str, JsonValue],
            {
                "bot_id": "bot-1",
                "reply_token": "qq:message-1",
                "message": {"segments": [{"type": "text", "data": {"text": "reply"}}]},
            },
        ),
    )

    outcome = await gateway.execute_message_send(request)

    assert outcome.success is True
    assert event.sent == ["native-chain"]


@pytest.mark.asyncio
async def test_astrbot_runtime_api_accepts_portable_message_and_exact_bot_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = FakeAstrEvent()
    gateway = AstrBotGateway(Path("workspace"), "astrbot", RecordingLogger())
    gateway._events_by_source_id["message-1"] = event
    monkeypatch.setattr("liteyukibot_runtime_astrbot.host._to_astr_chain", lambda message: message)

    event_outcome = await gateway.execute_runtime_api(
        _runtime_request(
            "event.send",
            cast(
                dict[str, JsonValue],
                {"message": {"segments": [{"type": "text", "data": {"text": "portable"}}]}},
            ),
        )
    )

    assert event_outcome.success is True
    assert isinstance(event.sent[0], Message)
    assert event.sent[0].plain_text == "portable"

    class FakePlatform:
        def meta(self) -> SimpleNamespace:
            return SimpleNamespace(id="qq", name="aiocqhttp")

    gateway._lifecycle = SimpleNamespace(
        platform_manager=SimpleNamespace(get_insts=lambda: [FakePlatform()]),
    )
    gateway._bot_platforms["bot-1"] = "qq"
    bot_snapshot = await gateway.execute_runtime_api(_runtime_request("bot.snapshot"))

    assert bot_snapshot.success is True
    assert bot_snapshot.result == {
        "bot_id": "bot-1",
        "platform_id": "qq",
        "platform_name": "aiocqhttp",
        "capabilities": [],
    }

    sent_payloads: list[MessageSendPayload] = []

    async def send(payload: MessageSendPayload) -> dict[str, str]:
        sent_payloads.append(payload)
        return {"message_id": "outbound-1"}

    monkeypatch.setattr(gateway, "_send_message", send)
    bot_send = await gateway.execute_runtime_api(
        _runtime_request(
            "bot.send",
            cast(
                dict[str, JsonValue],
                {
                    "bot_id": "bot-1",
                    "message": {"segments": [{"type": "text", "data": {"text": "proactive"}}]},
                    "conversation": {"id": "group-1", "type": "group"},
                },
            ),
        )
    )

    assert bot_send.success is True
    assert sent_payloads[0].conversation == ConversationRef(id="group-1", type="group")


def test_astrbot_workspace_uses_bridge_options_or_the_core_default(tmp_path: Path) -> None:
    settings = _settings(tmp_path / "data")

    assert _workspace_path(settings, "astrbot", {}) == (tmp_path / "data" / "bridges" / "astrbot" / "astrbot").resolve()
    assert _workspace_path(settings, "astrbot", {"workspace": "custom"}) == (Path.cwd() / "custom").resolve()
    with pytest.raises(ValueError, match="workspace"):
        _workspace_path(settings, "astrbot", {"workspace": 1})
