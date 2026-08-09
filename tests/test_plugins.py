from __future__ import annotations

import asyncio
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


class RecordingLogger(FakeLogger):
    def __init__(self) -> None:
        self.failures: list[tuple[str, tuple[Any, ...]]] = []
        self.failure_reported = asyncio.Event()

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        self.failures.append((message, args))
        self.failure_reported.set()


class FakeEntryPoint:
    def __init__(self, name: str, candidate: object) -> None:
        self.name = name
        self._candidate = candidate

    def load(self) -> object:
        return self._candidate


def make_manager(tmp_path: Path, *, logger: FakeLogger | None = None) -> PluginManager:
    return PluginManager(
        services=ServiceRegistry(),
        events=cast(EventBus, object()),
        actions=cast(ActionServiceLike, object()),
        logger=logger or FakeLogger(),
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
    )


def test_service_registry_rejects_duplicate_provider() -> None:
    registry = ServiceRegistry()
    key = ServiceKey("example.clock")
    registry.provide(key, object(), provider="first")
    with pytest.raises(ServiceError, match="already provided"):
        registry.provide(key, object(), provider="second")


def test_plugin_manifest_rejects_invalid_identity_and_metadata() -> None:
    with pytest.raises(ValueError, match="plugin id"):
        PluginManifest(id="invalid..id", name="Example", version="1.0.0")
    with pytest.raises(ValueError, match="metadata must not be blank"):
        PluginManifest(id="example", name="   ", version="1.0.0")
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        PluginManifest.model_validate(
            {"id": "example", "name": "Example", "version": "1.0.0", "unknown": True}
        )


def test_plugin_manager_discovers_enabled_entry_point(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def setup(_context: PluginContext) -> None:
        return None

    definition = PluginDefinition(
        PluginManifest(id="entry-point", name="Entry point", version="1.0.0"), setup
    )

    def entry_points(*, group: str) -> tuple[FakeEntryPoint, ...]:
        assert group == PluginManager.ENTRY_POINT_GROUP
        return (FakeEntryPoint("entry-point", definition),)

    monkeypatch.setattr("liteyukibot.plugins.metadata.entry_points", entry_points)

    assert make_manager(tmp_path).discover(("entry-point",)) == {"entry-point": definition}


def test_plugin_manager_reports_local_module_import_failure(tmp_path: Path) -> None:
    with pytest.raises(PluginError, match="local plugin module .* could not be imported"):
        make_manager(tmp_path).discover(("missing",), ("v7_test_missing_plugin",))


@pytest.mark.asyncio
async def test_plugin_setup_failure_removes_its_provided_services(tmp_path: Path) -> None:
    service = ServiceKey("example.transient")
    manager = make_manager(tmp_path)

    async def setup(context: PluginContext) -> None:
        context.services.provide(service, object())
        raise RuntimeError("setup failed")

    definition = PluginDefinition(
        PluginManifest(id="transient", name="Transient", version="1.0.0", provides=(service,)),
        setup,
    )

    with pytest.raises(PluginError, match="transient setup failed"):
        await manager.setup({"transient": definition}, {})

    assert manager.services.get(service) is None
    assert manager.loaded == {}


@pytest.mark.asyncio
async def test_plugin_managed_task_failure_is_logged(tmp_path: Path) -> None:
    logger = RecordingLogger()
    manager = make_manager(tmp_path, logger=logger)

    async def setup(context: PluginContext) -> PluginHandle:
        async def fail() -> None:
            raise RuntimeError("broken worker")

        context.tasks.start(fail(), name="worker")
        return PluginHandle()

    definition = PluginDefinition(
        PluginManifest(id="worker", name="Worker", version="1.0.0"),
        setup,
    )

    await manager.setup({"worker": definition}, {})
    await asyncio.wait_for(logger.failure_reported.wait(), timeout=1)

    assert logger.failures[0][0] == "task {} failed: {}"
    assert logger.failures[0][1][0] == "worker:worker"
    assert str(logger.failures[0][1][1]) == "broken worker"
    await manager.stop()


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
