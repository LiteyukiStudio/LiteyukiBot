from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import pytest
from liteyukibot_broker import (
    AuthorizationContextWire,
    MessageSendPayload,
    RuntimeApiInvoke,
)
from liteyukibot_broker.lyip import LyipLane
from liteyukibot_runtime_nonebot import bridge_definition
from liteyukibot_runtime_nonebot.host import (
    MESSAGE_CREATED_TOPIC,
    NoneBotHost,
    _broker_endpoints,
    _managed_load_plan,
    _runtime_api_declarations,
)

from liteyukibot.events import ConversationRef, EventEnvelope, JsonValue, Message, Segment


def test_nonebot_bridge_declares_stable_package_metadata() -> None:
    definition = bridge_definition()

    assert definition.kind == "nonebot"
    assert definition.grade == "stable"
    assert definition.facet_installer is not None
    assert definition.probe_module == "liteyukibot_runtime_nonebot"
    assert definition.distribution == "liteyukibot-v7-runtime-nonebot"


def test_managed_load_plan_resolves_only_generation_payload_directories(tmp_path: Path) -> None:
    generation = tmp_path / "generation"
    directory = generation / "payload" / ("a" * 64) / "plugins"
    directory.mkdir(parents=True)
    (generation / "load-plan.json").write_text(
        json.dumps({"plugins": ["example.plugin"], "directories": [f"{'a' * 64}/plugins"]}),
        encoding="utf-8",
    )
    (generation / "manifest.json").write_text(
        json.dumps(
            {
                "load_plan": {"plugins": ["example.plugin"], "directories": [f"{'a' * 64}/plugins"]}
            }
        ),
        encoding="utf-8",
    )

    plugins, directories = _managed_load_plan(str(generation.resolve()))

    assert plugins == ("example.plugin",)
    assert directories == (str(directory.resolve()),)


def test_managed_load_plan_rejects_payload_traversal(tmp_path: Path) -> None:
    generation = tmp_path / "generation"
    generation.mkdir()
    (generation / "payload").mkdir()
    (generation / "load-plan.json").write_text(
        json.dumps({"plugins": [], "directories": ["../outside"]}),
        encoding="utf-8",
    )
    (generation / "manifest.json").write_text(
        json.dumps({"load_plan": {"plugins": [], "directories": ["../outside"]}}),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="safe relative path"):
        _managed_load_plan(str(generation.resolve()))


def test_managed_load_plan_rejects_manifest_mismatch(tmp_path: Path) -> None:
    generation = tmp_path / "generation"
    generation.mkdir()
    (generation / "load-plan.json").write_text(
        json.dumps({"plugins": ["example.plugin"], "directories": []}),
        encoding="utf-8",
    )
    (generation / "manifest.json").write_text(
        json.dumps({"load_plan": {"plugins": [], "directories": []}}),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="does not match its manifest"):
        _managed_load_plan(str(generation.resolve()))


def test_nonebot_runtime_catalog_contains_alpha9_portable_operations() -> None:
    declarations = _runtime_api_declarations()

    assert {(item.namespace, item.operation) for item in declarations} == {
        ("event", "snapshot"),
        ("event", "send"),
        ("bot", "snapshot"),
        ("bot", "send"),
    }
    assert all(item.version == "1.2" for item in declarations)


def test_nonebot_ingress_is_json_safe_and_ordered_by_conversation() -> None:
    envelope = EventEnvelope(
        runtime_id="nonebot",
        adapter="onebot-v11",
        bot_id="42",
        type="message.group.normal",
        conversation=ConversationRef(id="2002", type="group"),
        message=Message(segments=(Segment(type="text", data={"text": "hello"}),)),
        raw={"group_id": 2002},
    )

    ingress = NoneBotHost.event_ingress(envelope)

    assert ingress.topic == MESSAGE_CREATED_TOPIC
    assert ingress.source_event_id == envelope.id
    assert ingress.ordering_key == "group:2002"
    assert ingress.model_dump(mode="json")["payload"]["message"] == {
        "segments": [{"type": "text", "data": {"text": "hello"}}]
    }


def test_nonebot_bridge_uses_the_broker_control_and_business_ports() -> None:
    endpoints = _broker_endpoints("tcp://127.0.0.1:20217")

    assert endpoints == {
        LyipLane.CONTROL: "tcp://127.0.0.1:20217",
        LyipLane.BUSINESS: "tcp://127.0.0.1:20218",
    }


def test_nonebot_host_wires_bridge_local_options_into_nonebot(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeDriver:
        def __init__(self) -> None:
            self.adapters: list[Any] = []
            self.startup: list[Any] = []
            self.shutdown: list[Any] = []

        def register_adapter(self, adapter: Any) -> None:
            self.adapters.append(adapter)

        def on_startup(self, callback: Any) -> None:
            self.startup.append(callback)

        def on_shutdown(self, callback: Any) -> None:
            self.shutdown.append(callback)

    class FakeNoneBot:
        def __init__(self, driver: FakeDriver) -> None:
            self.driver = driver
            self.init_options: dict[str, Any] | None = None
            self.plugins: list[str] = []
            self.directories: list[str] = []

        def init(self, **options: Any) -> None:
            self.init_options = options

        def get_driver(self) -> FakeDriver:
            return self.driver

        def load_plugin(self, name: str) -> object:
            self.plugins.append(name)
            return object()

        def load_plugins(self, directory: str) -> list[object]:
            self.directories.append(directory)
            return [object()]

    adapter_module = ModuleType("test_nonebot_adapter")
    adapter = object()
    adapter_module.Adapter = adapter  # type: ignore[attr-defined]
    nonebot_adapters = ModuleType("nonebot.adapters")
    nonebot_adapters.Bot = object  # type: ignore[attr-defined]
    nonebot_adapters.Event = object  # type: ignore[attr-defined]
    nonebot_message = ModuleType("nonebot.message")
    nonebot_message.event_preprocessor = lambda callback: callback  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "test_nonebot_adapter", adapter_module)
    monkeypatch.setitem(sys.modules, "nonebot.adapters", nonebot_adapters)
    monkeypatch.setitem(sys.modules, "nonebot.message", nonebot_message)

    driver = FakeDriver()
    nonebot = FakeNoneBot(driver)
    host = NoneBotHost(
        nonebot,
        cast(Any, SimpleNamespace(client=SimpleNamespace())),
        "nonebot",
        {
            "config": {"driver": "~fastapi"},
            "adapters": ["test_nonebot_adapter:Adapter"],
            "plugins": ["example.plugin"],
            "plugin_dirs": ["plugins"],
        },
    )

    host.install()

    assert nonebot.init_options == {"driver": "~fastapi"}
    assert driver.adapters == [adapter]
    assert nonebot.plugins == ["example.plugin"]
    assert nonebot.directories == ["plugins"]


@pytest.mark.asyncio
async def test_nonebot_host_passes_configured_bridge_id_to_event_normalizer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeDriver:
        def on_startup(self, _callback: Any) -> None:
            return None

        def on_shutdown(self, _callback: Any) -> None:
            return None

    class FakeNoneBot:
        def __init__(self) -> None:
            self.driver = FakeDriver()

        def init(self, **_options: Any) -> None:
            return None

        def get_driver(self) -> FakeDriver:
            return self.driver

        def load_plugin(self, _name: str) -> object:
            return object()

        def load_plugins(self, _directory: str) -> list[object]:
            return [object()]

    callbacks: list[Any] = []
    adapters_module = ModuleType("nonebot.adapters")
    adapters_module.Bot = object  # type: ignore[attr-defined]
    adapters_module.Event = object  # type: ignore[attr-defined]
    message_module = ModuleType("nonebot.message")

    def register_callback(callback: Any) -> Any:
        callbacks.append(callback)
        return callback

    message_module.event_preprocessor = register_callback  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "nonebot.adapters", adapters_module)
    monkeypatch.setitem(sys.modules, "nonebot.message", message_module)

    envelope = EventEnvelope(
        id="source-event",
        runtime_id="nonebot-prod",
        adapter="test",
        bot_id="bot",
        type="message.created",
        conversation=ConversationRef(id="conversation"),
    )
    runtime_ids: list[str | None] = []

    def normalize(_bot: object, _event: object, *, runtime_id: str | None = None) -> EventEnvelope:
        runtime_ids.append(runtime_id)
        return envelope

    monkeypatch.setattr("liteyukibot_runtime_nonebot.host.normalize_event", normalize)
    host = NoneBotHost(
        FakeNoneBot(),
        cast(Any, SimpleNamespace(client=SimpleNamespace())),
        "nonebot-prod",
    )
    host.install()

    await callbacks[0](object(), object())

    assert runtime_ids == ["nonebot-prod"]


@pytest.mark.asyncio
async def test_nonebot_runtime_api_uses_portable_dtos_and_exact_bot_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeAdapter:
        def get_name(self) -> str:
            return "OneBot V11"

    class FakeBot:
        self_id = "42"
        adapter = FakeAdapter()

        async def send(self, _event: object, message: object) -> dict[str, str]:
            assert message == "native-message"
            return {"message_id": "reply-1"}

    bot = FakeBot()
    event = object()
    envelope = EventEnvelope(
        id="event-1",
        runtime_id="nonebot",
        adapter="onebot-v11",
        bot_id="42",
        type="message.created",
        conversation=ConversationRef(id="2002", type="group"),
        message=Message(segments=(Segment(type="text", data={"text": "hello"}),)),
    )
    host = NoneBotHost(SimpleNamespace(), None, "nonebot")
    host._events_by_source_id[envelope.id] = (bot, event, envelope)
    monkeypatch.setattr(
        "liteyukibot_runtime_nonebot.host.to_native_message",
        lambda _adapter, _message: "native-message",
    )

    def request(api_id: str, arguments: dict[str, JsonValue] | None = None) -> RuntimeApiInvoke:
        return RuntimeApiInvoke(
            delivery_id="delivery-1",
            source_event_id="event-1",
            lease_id="lease-1",
            correlation_id=f"runtime:{api_id}",
            runtime_kind="nonebot",
            version="^1.0",
            api_id=api_id,
            caller_extension_id="example.plugin",
            arguments=arguments or {},
            authorization=AuthorizationContextWire(
                event_id="event-1",
                runtime_id="nonebot",
                bot_id="42",
            ),
        )

    snapshot = await host.execute_runtime_api(request("event.snapshot"))
    event_send = await host.execute_runtime_api(
        request("event.send", {"message": "hello"}),
    )
    bot_snapshot = await host.execute_runtime_api(request("bot.snapshot"))

    assert snapshot.success is True
    assert isinstance(snapshot.result, Mapping)
    assert snapshot.result["conversation"] == {"id": "2002", "type": "group", "parent_id": None}
    assert event_send.success is True
    assert bot_snapshot.result == {
        "bot_id": "42",
        "adapter": "onebot-v11",
        "capabilities": ["message.send"],
        "extensions": {},
    }

    sent_payloads: list[MessageSendPayload] = []

    async def send(payload: MessageSendPayload) -> dict[str, str]:
        sent_payloads.append(payload)
        return {"message_id": "proactive-1"}

    monkeypatch.setattr(host, "_send_message", send)
    bot_send = await host.execute_runtime_api(
        request(
            "bot.send",
            cast(
                dict[str, JsonValue],
                {
                    "bot_id": "42",
                    "message": {"segments": [{"type": "text", "data": {"text": "proactive"}}]},
                    "conversation": {"id": "2002", "type": "group"},
                },
            ),
        )
    )

    assert bot_send.success is True
    assert sent_payloads[0].conversation == ConversationRef(id="2002", type="group")
