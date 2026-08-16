from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import pytest
from liteyukibot_runtime_nonebot.host import MESSAGE_CREATED_TOPIC, NoneBotHost, _broker_endpoints

from liteyukibot.events import ConversationRef, EventEnvelope, Message, Segment
from liteyukibot.lyip import LyipLane


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
