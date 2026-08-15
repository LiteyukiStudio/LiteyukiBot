from __future__ import annotations

import asyncio
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import Any, cast

import pytest

from liteyukibot.events import EventBus
from liteyukibot.exceptions import PluginError, ServiceError
from liteyukibot.plugins import (
    WEBUI_SCHEMA_DRAFT_2020_12,
    ActionServiceLike,
    PluginContext,
    PluginDefinition,
    PluginHandle,
    PluginManager,
    PluginManifest,
    WebUiComponent,
    WebUiContributionManifest,
    WebUiDiagnostic,
    WebUiSnapshotState,
    WebUiSurfaceManifest,
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


def webui_manifest(*, plugin_id: str = "example", api_version: int = 1) -> WebUiContributionManifest:
    prefix = f"webui.plugin.{plugin_id}."
    return WebUiContributionManifest(
        api_version=api_version,
        i18n_keys=(f"{prefix}title", f"{prefix}table"),
        surfaces=(
            WebUiSurfaceManifest(
                id="overview",
                title_key=f"{prefix}title",
                icon="Gauge",
                read_capability="example.read",
                data_schema={
                    "$schema": WEBUI_SCHEMA_DRAFT_2020_12,
                    "type": "object",
                    "required": ["rows"],
                    "properties": {"rows": {"type": "array", "items": {"type": "object"}}},
                    "additionalProperties": False,
                },
                operation_ids=("management.example.refresh",),
                components=(
                    WebUiComponent(id="root", kind="status", title_key=f"{prefix}title"),
                    WebUiComponent(id="rows", kind="table", title_key=f"{prefix}table", data_path=("rows",)),
                    WebUiComponent(id="refresh", kind="operation_form", operation_id="management.example.refresh"),
                ),
            ),
        ),
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
    with pytest.raises(ValueError, match="webui.unexpected"):
        PluginManifest.model_validate(
            {
                "id": "example",
                "name": "Example",
                "version": "1.0.0",
                "webui": {"surfaces": [], "unexpected": True},
            }
        )


def test_webui_manifest_is_strict_and_bounded() -> None:
    with pytest.raises(ValueError, match="host-approved"):
        WebUiSurfaceManifest(
            id="overview",
            title_key="webui.plugin.example.title",
            icon="ArbitraryIcon",
            read_capability="example.read",
            data_schema={"$schema": WEBUI_SCHEMA_DRAFT_2020_12},
            components=(WebUiComponent(id="root", kind="status"),),
        )
    with pytest.raises(ValueError, match="allowlisted"):
        WebUiSurfaceManifest(
            id="overview",
            title_key="webui.plugin.example.title",
            icon="Gauge",
            read_capability="example.read",
            data_schema={"$schema": WEBUI_SCHEMA_DRAFT_2020_12},
            components=(WebUiComponent(id="run", kind="operation_form", operation_id="management.example.run"),),
        )
    with pytest.raises(ValueError, match="data_schema is invalid"):
        WebUiSurfaceManifest(
            id="overview",
            title_key="webui.plugin.example.title",
            icon="Gauge",
            read_capability="example.read",
            data_schema={"$schema": WEBUI_SCHEMA_DRAFT_2020_12, "type": "not-a-json-schema-type"},
            components=(WebUiComponent(id="root", kind="status"),),
        )
    with pytest.raises(ValueError, match="Input should be"):
        WebUiComponent.model_validate({"id": "script", "kind": "custom_script"})
    with pytest.raises(ValueError, match="at most 16"):
        WebUiContributionManifest(surfaces=tuple(webui_manifest().surfaces * 17))
    with pytest.raises(ValueError, match="Extra inputs"):
        WebUiContributionManifest.model_validate({"surfaces": [], "unexpected": True})


@pytest.mark.asyncio
async def test_webui_provider_registers_after_start_and_withdraws_before_stop(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    calls: list[str] = []

    class Provider:
        def snapshot(self, surface_id: str) -> dict[str, object]:
            calls.append(f"snapshot:{surface_id}")
            return {"rows": []}

    async def setup(_context: PluginContext) -> PluginHandle:
        async def stop() -> None:
            assert manager.webui_surfaces() == ()
            calls.append("stop")

        return PluginHandle(stop=stop, webui_provider=Provider())

    definition = PluginDefinition(
        PluginManifest(id="example", name="Example", version="1.0.0", webui=webui_manifest()), setup
    )
    await manager.setup({"example": definition}, {})
    assert manager.webui_surfaces() == ()

    await manager.start()
    assert [(plugin_id, surface.route(plugin_id)) for plugin_id, surface in manager.webui_surfaces()] == [
        ("example", "/plugins/example/overview")
    ]
    denied = await manager.webui_snapshot("example", "overview", frozenset())
    assert denied.state is WebUiSnapshotState.UNAVAILABLE
    assert denied.code == "not_authorized"
    assert calls == []

    snapshot = await manager.webui_snapshot("example", "overview", frozenset({"example.read"}))
    assert snapshot.state is WebUiSnapshotState.AVAILABLE
    assert snapshot.data == {"rows": []}
    assert calls == ["snapshot:overview"]
    generation = manager.webui_generation

    await manager.stop()
    assert calls[-1] == "stop"
    assert manager.webui_generation == generation + 1
    withdrawn = await manager.webui_snapshot("example", "overview", frozenset({"example.read"}))
    assert withdrawn.code == "surface_unavailable"


@pytest.mark.asyncio
async def test_webui_provider_failures_are_isolated_and_bounded(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)

    class Provider:
        async def snapshot(self, _surface_id: str) -> dict[str, object]:
            await asyncio.sleep(1)
            return {"rows": []}

    async def setup(_context: PluginContext) -> PluginHandle:
        return PluginHandle(webui_provider=Provider())

    definition = PluginDefinition(
        PluginManifest(id="example", name="Example", version="1.0.0", webui=webui_manifest()), setup
    )
    await manager.setup({"example": definition}, {})
    await manager.start()
    timeout = await manager.webui_snapshot("example", "overview", frozenset({"example.read"}))
    assert timeout.code == "snapshot_timeout"

    class TooManyRows:
        def snapshot(self, _surface_id: str) -> dict[str, object]:
            return {"rows": [{}] * 201}

    manager._webui_providers["example"] = TooManyRows()  # noqa: SLF001 - focused provider limit contract
    table = await manager.webui_snapshot("example", "overview", frozenset({"example.read"}))
    assert table.code == "table_row_limit"

    class InvalidSchemaData:
        def snapshot(self, _surface_id: str) -> dict[str, object]:
            return {"wrong": []}

    manager._webui_providers["example"] = InvalidSchemaData()  # noqa: SLF001 - focused schema failure contract
    invalid = await manager.webui_snapshot("example", "overview", frozenset({"example.read"}))
    assert invalid.code == "invalid_snapshot"
    await manager.stop()


@pytest.mark.asyncio
async def test_webui_contribution_incompatibility_does_not_stop_plugin_core(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    started: list[str] = []

    class Provider:
        def snapshot(self, _surface_id: str) -> dict[str, object]:
            return {"rows": []}

    async def setup(_context: PluginContext) -> PluginHandle:
        async def start() -> None:
            started.append("started")

        return PluginHandle(start=start, webui_provider=Provider())

    unsupported = PluginDefinition(
        PluginManifest(
            id="unsupported",
            name="Unsupported",
            version="1.0.0",
            webui=webui_manifest(plugin_id="unsupported", api_version=2),
        ),
        setup,
    )
    wrong_namespace = PluginDefinition(
        PluginManifest(
            id="wrong",
            name="Wrong",
            version="1.0.0",
            webui=webui_manifest(plugin_id="other"),
        ),
        setup,
    )
    await manager.setup({"unsupported": unsupported, "wrong": wrong_namespace}, {})
    await manager.start()

    assert started == ["started", "started"]
    assert manager.webui_surfaces() == ()
    assert {(item.plugin_id, item.code) for item in manager.webui_diagnostics} == {
        ("unsupported", "unsupported_webui_api"),
        ("wrong", "webui_i18n_namespace"),
    }
    await manager.stop()


@pytest.mark.asyncio
async def test_webui_i18n_duplicate_disables_only_new_plugin_generation(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)

    class Provider:
        def snapshot(self, _surface_id: str) -> dict[str, object]:
            return {"rows": []}

    async def setup(_context: PluginContext) -> PluginHandle:
        return PluginHandle(webui_provider=Provider())

    first = PluginDefinition(
        PluginManifest(id="first", name="First", version="1.0.0", webui=webui_manifest(plugin_id="first")), setup
    )
    duplicate = PluginDefinition(
        PluginManifest(
            id="second",
            name="Second",
            version="1.0.0",
            webui=WebUiContributionManifest.model_construct(
                api_version=1,
                surfaces=webui_manifest(plugin_id="first").surfaces,
                i18n_keys=("webui.plugin.first.title", "webui.plugin.first.table"),
            ),
        ),
        setup,
    )
    await manager.setup({"first": first, "second": duplicate}, {})
    await manager.start()

    assert [plugin_id for plugin_id, _surface in manager.webui_surfaces()] == ["first"]
    assert manager.webui_diagnostics == (WebUiDiagnostic("second", "webui_i18n_duplicate"),)
    await manager.stop()


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
async def test_plugin_setup_failure_runs_deferred_cleanup_in_reverse_order(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    calls: list[str] = []

    async def async_cleanup() -> None:
        calls.append("async")

    async def setup(context: PluginContext) -> None:
        context.defer_cleanup(lambda: calls.append("sync"))
        context.defer_cleanup(async_cleanup)
        raise RuntimeError("setup failed")

    definition = PluginDefinition(
        PluginManifest(id="cleanup", name="Cleanup", version="1.0.0"),
        setup,
    )

    with pytest.raises(PluginError, match="cleanup setup failed"):
        await manager.setup({"cleanup": definition}, {})

    assert calls == ["async", "sync"]


@pytest.mark.asyncio
async def test_plugin_setup_validation_failure_runs_stop_and_deferred_cleanup(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    calls: list[str] = []

    async def setup(context: PluginContext) -> PluginHandle:
        context.defer_cleanup(lambda: calls.append("cleanup"))

        async def stop() -> None:
            calls.append("stop")

        return PluginHandle(stop=stop)

    definition = PluginDefinition(
        PluginManifest(
            id="cleanup-validation",
            name="Cleanup validation",
            version="1.0.0",
            provides=(ServiceKey("example.required"),),
        ),
        setup,
    )

    with pytest.raises(PluginError, match="cleanup-validation setup failed"):
        await manager.setup({"cleanup-validation": definition}, {})

    assert calls == ["stop", "cleanup"]


@pytest.mark.asyncio
async def test_plugin_stop_runs_deferred_cleanup_after_stop_callback(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    calls: list[str] = []

    async def setup(context: PluginContext) -> PluginHandle:
        context.defer_cleanup(lambda: calls.append("cleanup"))

        async def stop() -> None:
            calls.append("stop")

        return PluginHandle(stop=stop)

    definition = PluginDefinition(
        PluginManifest(id="cleanup", name="Cleanup", version="1.0.0"),
        setup,
    )

    await manager.setup({"cleanup": definition}, {})
    await manager.stop()

    assert calls == ["stop", "cleanup"]


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
