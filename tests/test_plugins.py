from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import Any, cast

import pytest

from liteyukibot.events import EventBus
from liteyukibot.exceptions import PluginError, ServiceError
from liteyukibot.plugins import (
    ActionServiceLike,
    PluginContext,
    PluginDefinition,
    PluginHandle,
    PluginManager,
    PluginManifest,
)
from liteyukibot.services import ServiceKey, ServiceRegistry, ServiceRequirement


class FakeLogger:
    def bind(self, **fields: Any) -> FakeLogger:
        return self

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        pass

    def contextualize(self, **fields: Any) -> AbstractContextManager[None]:
        return nullcontext()

    def trace(self, message: str, *args: Any, **kwargs: Any) -> None:
        pass

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        pass

    def success(self, message: str, *args: Any, **kwargs: Any) -> None:
        pass

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        pass

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        pass

    def critical(self, message: str, *args: Any, **kwargs: Any) -> None:
        pass

    def exception(self, message: str, *args: Any, **kwargs: Any) -> None:
        pass


def test_service_registry_rejects_duplicate_provider() -> None:
    registry = ServiceRegistry()
    key = ServiceKey("example.clock")
    registry.provide(key, object(), provider="first")
    with pytest.raises(ServiceError, match="already provided"):
        registry.provide(key, object(), provider="second")


@pytest.mark.asyncio
async def test_plugin_manager_resolves_services_and_stops_in_reverse_order(tmp_path: Path) -> None:
    service = ServiceKey("example.message")
    calls: list[str] = []

    async def provider_setup(context: PluginContext) -> PluginHandle:
        context.services.provide(service, "ready")
        calls.append("provider.setup")

        async def stop() -> None:
            calls.append("provider.stop")

        return PluginHandle(stop=stop)

    async def consumer_setup(context: PluginContext) -> PluginHandle:
        assert context.services.require(service) == "ready"
        assert context.paths is not None
        calls.append("consumer.setup")

        async def stop() -> None:
            calls.append("consumer.stop")

        return PluginHandle(stop=stop)

    definitions = {
        "consumer": PluginDefinition(
            PluginManifest(
                id="consumer",
                name="Consumer",
                version="1.0.0",
                requires=(ServiceRequirement(service),),
                storage="private",
            ),
            consumer_setup,
        ),
        "provider": PluginDefinition(
            PluginManifest(
                id="provider",
                name="Provider",
                version="1.0.0",
                provides=(service,),
            ),
            provider_setup,
        ),
    }
    manager = PluginManager(
        services=ServiceRegistry(),
        events=cast(EventBus, object()),
        actions=cast(ActionServiceLike, object()),
        logger=FakeLogger(),
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
    )

    await manager.setup(definitions, {})
    await manager.start()
    await manager.stop()

    assert calls == ["provider.setup", "consumer.setup", "consumer.stop", "provider.stop"]
    assert (tmp_path / "data" / "plugins" / "consumer").is_dir()
    assert (tmp_path / "cache" / "plugins" / "consumer").is_dir()


def test_plugin_manager_rejects_service_cycle(tmp_path: Path) -> None:
    left = ServiceKey("cycle.left")
    right = ServiceKey("cycle.right")

    async def setup(context: PluginContext) -> None:
        return None

    definitions = {
        "left": PluginDefinition(
            PluginManifest(
                id="left",
                name="Left",
                version="1",
                provides=(left,),
                requires=(ServiceRequirement(right),),
            ),
            setup,
        ),
        "right": PluginDefinition(
            PluginManifest(
                id="right",
                name="Right",
                version="1",
                provides=(right,),
                requires=(ServiceRequirement(left),),
            ),
            setup,
        ),
    }
    manager = PluginManager(
        services=ServiceRegistry(),
        events=cast(EventBus, object()),
        actions=cast(ActionServiceLike, object()),
        logger=FakeLogger(),
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
    )

    with pytest.raises(PluginError, match="dependency cycle"):
        manager.resolve_order(definitions)
