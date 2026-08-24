from __future__ import annotations

import asyncio
import importlib
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pytest

from liteyukibot import (
    PluginContext,
    PluginDefinition,
    PluginHandle,
    PluginManifest,
    PluginPaths,
    PluginServices,
    ServiceKey,
    ServiceRequirement,
)
from liteyukibot.events import (
    ActionEnvelope,
    ActorRef,
    ConversationRef,
    EventEnvelope,
    Message,
    Segment,
    SendMessage,
)
from liteyukibot.exceptions import PluginError, ServiceError
from liteyukibot.testing import PluginTestHarness

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SOURCE = ROOT / "examples" / "native-plugin" / "src"


def _event(text: str = "hello") -> EventEnvelope:
    return EventEnvelope(
        id="event-1",
        runtime_id="adapter-runtime",
        adapter="example",
        bot_id="bot-1",
        type="message",
        conversation=ConversationRef(id="conversation-1", type="group"),
        actor=ActorRef(id="user-1"),
        message=Message(segments=(Segment(type="text", data={"text": text}),)),
        reply_token="reply-1",
    )


def _load_example_plugin(monkeypatch: pytest.MonkeyPatch) -> PluginDefinition:
    monkeypatch.syspath_prepend(str(PLUGIN_SOURCE))
    sys.modules.pop("liteyukibot_example_plugin", None)
    module = importlib.import_module("liteyukibot_example_plugin")
    definition = module.plugin
    assert isinstance(definition, PluginDefinition)
    return definition


@pytest.mark.asyncio
async def test_native_plugin_example_uses_real_harness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = PluginTestHarness(
        _load_example_plugin(monkeypatch),
        root=tmp_path,
        config={"prefix": "answer: "},
    )

    async with harness:
        context = harness.context
        assert isinstance(context.paths, PluginPaths)
        assert context.paths.data == tmp_path / "data" / "plugins" / "example.echo"
        assert context.paths.cache == tmp_path / "cache" / "plugins" / "example.echo"
        assert isinstance(context.services, PluginServices)
        with pytest.raises(TypeError):
            cast(dict[str, Any], context.config)["prefix"] = "changed"

        result = await harness.publish(_event())
        assert result.status == "processed"
        assert result.handlers_called == 1
        assert result.failures == ()
        assert len(harness.recorded_actions) == 1
        sent = cast(SendMessage, harness.recorded_actions[0].action)
        assert sent.message.plain_text == "answer: hello"

        direct = ActionEnvelope(
            runtime_id="adapter-runtime",
            bot_id="bot-1",
            action=SendMessage(
                conversation=ConversationRef(id="conversation-1"),
                message=Message(segments=(Segment(type="text", data={"text": "direct"}),)),
            ),
        )
        direct_result = await context.actions.execute(direct)
        assert direct_result.success is True
        assert harness.recorded_actions[-1] == direct

    assert context.events.closed is True
    await harness.stop()
    with pytest.raises(RuntimeError, match="single-use"):
        await harness.start()


@pytest.mark.asyncio
async def test_plugin_harness_exercises_services_tasks_and_lifecycle(tmp_path: Path) -> None:
    dependency = ServiceKey("example.dependency")
    provided = ServiceKey("example.provided")
    worker_started = asyncio.Event()
    cancelled = asyncio.Event()
    lifecycle: list[str] = []

    async def worker() -> None:
        worker_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def setup(context: PluginContext) -> PluginHandle:
        lifecycle.append("setup")
        assert context.services.require(dependency) == "stub"
        context.services.provide(provided, "value")
        context.tasks.start(worker(), name="worker")

        async def start() -> None:
            lifecycle.append("start")

        async def stop() -> None:
            lifecycle.append("stop")

        return PluginHandle(start=start, stop=stop)

    definition = PluginDefinition(
        manifest=PluginManifest(
            id="example.services",
            name="Services",
            version="1.0.0",
            provides=(provided,),
            requires=(ServiceRequirement(dependency),),
        ),
        setup=setup,
    )
    harness = PluginTestHarness(
        definition,
        root=tmp_path,
        dependencies={dependency: "stub"},
    )

    async with harness:
        await worker_started.wait()
        assert harness.require_service(provided) == "value"
        assert lifecycle == ["setup", "start"]

    assert lifecycle == ["setup", "start", "stop"]
    assert cancelled.is_set()
    assert harness.require_service(dependency) == "stub"
    with pytest.raises(ServiceError, match="unavailable"):
        harness.require_service(provided)


@pytest.mark.asyncio
async def test_plugin_harness_cleans_up_failed_setup(tmp_path: Path) -> None:
    provided = ServiceKey("example.failed")
    worker_started = asyncio.Event()
    cancelled = asyncio.Event()

    async def worker() -> None:
        worker_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def setup(context: PluginContext) -> PluginHandle:
        context.services.provide(provided, object())
        context.tasks.start(worker(), name="worker")
        await worker_started.wait()
        raise RuntimeError("setup failed")

    harness = PluginTestHarness(
        PluginDefinition(
            manifest=PluginManifest(
                id="example.failed",
                name="Failed",
                version="1.0.0",
                provides=(provided,),
            ),
            setup=setup,
        ),
        root=tmp_path,
    )

    with pytest.raises(PluginError, match="setup failed"):
        await harness.start()
    assert cancelled.is_set()
    with pytest.raises(ServiceError, match="unavailable"):
        harness.require_service(provided)
    with pytest.raises(RuntimeError, match="single-use"):
        await harness.start()


@pytest.mark.asyncio
async def test_plugin_harness_cleans_up_failed_start(tmp_path: Path) -> None:
    worker_started = asyncio.Event()
    cancelled = asyncio.Event()
    stopped = asyncio.Event()

    async def worker() -> None:
        worker_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def setup(context: PluginContext) -> PluginHandle:
        context.tasks.start(worker(), name="worker")

        async def start() -> None:
            await worker_started.wait()
            raise RuntimeError("start failed")

        async def stop() -> None:
            stopped.set()

        return PluginHandle(start=start, stop=stop)

    harness = PluginTestHarness(
        PluginDefinition(
            manifest=PluginManifest(
                id="example.start-failure",
                name="Start failure",
                version="1.0.0",
            ),
            setup=setup,
        ),
        root=tmp_path,
    )

    with pytest.raises(RuntimeError, match="start failed"):
        await harness.start()
    assert stopped.is_set()
    assert cancelled.is_set()


def test_public_developer_types_are_importable() -> None:
    annotations: Mapping[str, object] = {
        "PluginPaths": PluginPaths,
        "PluginServices": PluginServices,
        "PluginTestHarness": PluginTestHarness,
    }
    assert all(value is not None for value in annotations.values())
