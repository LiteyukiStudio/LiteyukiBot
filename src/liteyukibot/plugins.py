"""Native v7 plugin definitions and lifecycle management."""

from __future__ import annotations

import asyncio
import inspect
import json
import re
from collections.abc import Awaitable, Callable, Mapping, MutableMapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from enum import StrEnum
from functools import partial
from importlib import import_module, metadata
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Protocol, cast

from jsonschema import Draft202012Validator, SchemaError, ValidationError
from pydantic import BaseModel, ConfigDict, field_validator

from .authorization import AuthorizationContext
from .events import ActionEnvelope, ActionResult, EventBus, EventEnvelope
from .exceptions import PluginError, ServiceError
from .init_specs import PluginInitSpec
from .resource_packs import ResourcePackDeclaration
from .services import ServiceKey, ServiceRegistry, ServiceRequirement
from .tasks import ManagedTasks

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
type ToolCallback = Callable[[AuthorizationContext, Mapping[str, JsonValue]], Awaitable[JsonValue]]

WEBUI_API_VERSION = 1
WEBUI_SCHEMA_DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"
WEBUI_SNAPSHOT_TIMEOUT_SECONDS = 0.25
WEBUI_SNAPSHOT_MAX_BYTES = 64 * 1024
WEBUI_TABLE_MAX_ROWS = 200
_WEBUI_TOKEN = re.compile(r"^[a-z][a-z0-9-]*$")
_WEBUI_PATH_TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_WEBUI_ICON_NAMES = frozenset(
    {
        "Activity",
        "Archive",
        "Bell",
        "Bot",
        "Box",
        "ChartBar",
        "CheckCircle",
        "CircleHelp",
        "Clock",
        "Cloud",
        "Cog",
        "Database",
        "Eye",
        "FileText",
        "Gauge",
        "Globe",
        "HeartPulse",
        "Info",
        "KeyRound",
        "LayoutDashboard",
        "List",
        "Lock",
        "MessageSquare",
        "Network",
        "Package",
        "Plug",
        "RefreshCw",
        "Search",
        "Server",
        "Settings",
        "ShieldCheck",
        "Sparkles",
        "Table",
        "Terminal",
        "TriangleAlert",
        "Users",
        "Wrench",
    }
)


def _validate_webui_token(value: str, field: str) -> str:
    if not _WEBUI_TOKEN.fullmatch(value):
        raise ValueError(f"{field} must use lowercase ASCII letters, digits, or '-'")
    return value


def _validate_webui_key(value: str, field: str) -> str:
    if not value or value != value.strip() or any(part == "" for part in value.split(".")):
        raise ValueError(f"{field} must be a non-empty i18n key")
    return value


class WebUiComponent(BaseModel):
    """One declarative, host-rendered plugin WebUI component."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: Literal[
        "navigation",
        "status",
        "metric",
        "detail",
        "table",
        "table_row_drawer",
        "operation_form",
        "operation_result",
    ]
    title_key: str | None = None
    summary_key: str | None = None
    data_path: tuple[str, ...] = ()
    operation_id: str | None = None
    children: tuple[WebUiComponent, ...] = ()

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return _validate_webui_token(value, "webui component id")

    @field_validator("title_key", "summary_key")
    @classmethod
    def validate_i18n_key(cls, value: str | None, info: Any) -> str | None:
        return _validate_webui_key(value, info.field_name) if value is not None else value

    @field_validator("data_path")
    @classmethod
    def validate_data_path(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not _WEBUI_PATH_TOKEN.fullmatch(part) for part in value):
            raise ValueError("webui data_path must contain object field names")
        return value

    @field_validator("operation_id")
    @classmethod
    def validate_operation_id(cls, value: str | None) -> str | None:
        if value is not None and (not value or value != value.strip() or " " in value):
            raise ValueError("webui operation_id must be a non-empty operation identifier")
        return value

    def model_post_init(self, __context: Any) -> None:
        child_ids = [child.id for child in self.children]
        if len(child_ids) != len(set(child_ids)):
            raise ValueError("webui component children must have unique ids")
        if self.kind == "operation_form" and self.operation_id is None:
            raise ValueError("webui operation_form requires operation_id")
        if self.kind != "operation_form" and self.operation_id is not None:
            raise ValueError("webui operation_id is only valid for operation_form")


class WebUiSurfaceManifest(BaseModel):
    """A bounded plugin contribution rendered by the host Plugins workspace."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    title_key: str
    summary_key: str | None = None
    icon: str
    read_capability: str
    data_schema: dict[str, JsonValue]
    operation_ids: tuple[str, ...] = ()
    components: tuple[WebUiComponent, ...]

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return _validate_webui_token(value, "webui surface id")

    @field_validator("title_key", "summary_key")
    @classmethod
    def validate_i18n_key(cls, value: str | None, info: Any) -> str | None:
        return _validate_webui_key(value, info.field_name) if value is not None else value

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, value: str) -> str:
        if value not in _WEBUI_ICON_NAMES:
            raise ValueError("webui icon is not host-approved")
        return value

    @field_validator("read_capability")
    @classmethod
    def validate_read_capability(cls, value: str) -> str:
        if not value or value != value.strip() or " " in value:
            raise ValueError("webui read_capability must be a non-empty capability identifier")
        return value

    @field_validator("operation_ids")
    @classmethod
    def validate_operation_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("webui operation_ids must be unique")
        for operation_id in value:
            if not operation_id or operation_id != operation_id.strip() or " " in operation_id:
                raise ValueError("webui operation_ids must contain operation identifiers")
        return value

    def model_post_init(self, __context: Any) -> None:
        if self.data_schema.get("$schema") != WEBUI_SCHEMA_DRAFT_2020_12:
            raise ValueError("webui data_schema must declare Draft 2020-12")
        try:
            Draft202012Validator.check_schema(self.data_schema)
        except SchemaError as error:
            raise ValueError(f"webui data_schema is invalid: {error.message}") from error
        if not self.components:
            raise ValueError("webui surface requires at least one component")
        component_ids = _component_ids(self.components)
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("webui surface component ids must be unique")
        for component in _walk_components(self.components):
            if component.kind == "operation_form" and component.operation_id not in self.operation_ids:
                raise ValueError("webui operation_form must reference an allowlisted operation_id")

    def route(self, plugin_id: str) -> str:
        return f"/plugins/{plugin_id}/{self.id}"


class WebUiContributionManifest(BaseModel):
    """Versioned declarative Plugin WebUI contribution contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    api_version: int = WEBUI_API_VERSION
    surfaces: tuple[WebUiSurfaceManifest, ...] = ()
    i18n_keys: tuple[str, ...] = ()

    @field_validator("api_version")
    @classmethod
    def validate_api_version(cls, value: int) -> int:
        if value < 1:
            raise ValueError("webui api_version must be positive")
        return value

    @field_validator("i18n_keys")
    @classmethod
    def validate_i18n_keys(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("webui i18n_keys must be unique")
        return tuple(_validate_webui_key(key, "webui i18n key") for key in value)

    def model_post_init(self, __context: Any) -> None:
        if len(self.surfaces) > 16:
            raise ValueError("webui contribution supports at most 16 surfaces")
        ids = [surface.id for surface in self.surfaces]
        if len(ids) != len(set(ids)):
            raise ValueError("webui surface ids must be unique")


def _walk_components(components: Sequence[WebUiComponent]) -> tuple[WebUiComponent, ...]:
    values: list[WebUiComponent] = []
    for component in components:
        values.append(component)
        values.extend(_walk_components(component.children))
    return tuple(values)


def _component_ids(components: Sequence[WebUiComponent]) -> tuple[str, ...]:
    return tuple(component.id for component in _walk_components(components))


class WebUiProvider(Protocol):
    def snapshot(self, surface_id: str) -> Mapping[str, object] | Awaitable[Mapping[str, object]]: ...


class WebUiSnapshotState(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class WebUiSnapshot:
    plugin_id: str
    surface_id: str
    state: WebUiSnapshotState
    data: Mapping[str, JsonValue] | None = None
    code: str | None = None


@dataclass(frozen=True, slots=True)
class WebUiDiagnostic:
    plugin_id: str
    code: str


class LoggerLike(Protocol):
    def bind(self, **fields: Any) -> LoggerLike: ...

    def contextualize(self, **fields: Any) -> AbstractContextManager[None]: ...

    def trace(self, message: str, *args: Any, **kwargs: Any) -> None: ...

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None: ...

    def info(self, message: str, *args: Any, **kwargs: Any) -> None: ...

    def success(self, message: str, *args: Any, **kwargs: Any) -> None: ...

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None: ...

    def error(self, message: str, *args: Any, **kwargs: Any) -> None: ...

    def critical(self, message: str, *args: Any, **kwargs: Any) -> None: ...

    def exception(self, message: str, *args: Any, **kwargs: Any) -> None: ...


class ActionServiceLike(Protocol):
    async def execute(self, action: ActionEnvelope, *, event: EventEnvelope | None = None) -> ActionResult: ...


def _log_task_failure(logger: LoggerLike, name: str, error: BaseException) -> None:
    logger.error("task {} failed: {}", name, error)


class ExtensionCoexistence(StrEnum):
    """Whether the same extension identity may run in both plugin hosts."""

    EXCLUSIVE = "exclusive"
    INFRASTRUCTURE = "infrastructure"


class ToolDeclaration(BaseModel):
    """One immutable, schema-validated Tool exposed by an Extension API v2 host."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    description: str
    input_schema: Mapping[str, JsonValue]
    output_schema: Mapping[str, JsonValue]
    capabilities: tuple[str, ...] = ()

    @field_validator("id", "description")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("tool metadata must be non-empty and trimmed")
        return value

    @field_validator("input_schema", "output_schema")
    @classmethod
    def validate_schema(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        try:
            Draft202012Validator.check_schema(dict(value))
        except SchemaError as error:
            raise ValueError("tool schema must be Draft 2020-12 compatible") from error
        return MappingProxyType(dict(value))

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("tool capabilities must not contain duplicates")
        for capability in value:
            _validate_capability(capability)
        return value


class ExtensionManifest(BaseModel):
    """Shared Native/Cordis Extension API v2 declaration."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    id: str
    name: str
    version: str
    api_version: Literal[2] = 2
    coexistence: ExtensionCoexistence = ExtensionCoexistence.EXCLUSIVE
    provides: tuple[ServiceKey, ...] = ()
    requires: tuple[ServiceRequirement, ...] = ()
    storage: Literal["none", "private"] = "none"
    resource_packs: tuple[ResourcePackDeclaration, ...] = ()
    capabilities: tuple[str, ...] = ()
    tools: tuple[ToolDeclaration, ...] = ()
    webui: WebUiContributionManifest | None = None

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return _validate_extension_id(value)

    @field_validator("name", "version")
    @classmethod
    def validate_required_metadata(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("plugin manifest metadata must not be blank")
        return value

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("extension capabilities must not contain duplicates")
        for capability in value:
            _validate_capability(capability)
        return value

    @field_validator("tools")
    @classmethod
    def validate_tools(cls, value: tuple[ToolDeclaration, ...], info: Any) -> tuple[ToolDeclaration, ...]:
        extension_id = info.data.get("id")
        if not isinstance(extension_id, str):
            return value
        if len({tool.id for tool in value}) != len(value):
            raise ValueError("extension tools must not contain duplicate IDs")
        prefix = f"{extension_id}."
        if any(not tool.id.startswith(prefix) for tool in value):
            raise ValueError("tool IDs must be prefixed by their extension ID")
        return value


# Deprecated source alias. It constructs Extension API v2 values, while an
# explicit api_version=1 is rejected by the v2 literal above.
PluginManifest = ExtensionManifest


@dataclass(frozen=True, slots=True)
class ExtensionIdentity:
    """Host-neutral extension identity exposed during startup topology resolution."""

    id: str
    coexistence: ExtensionCoexistence = ExtensionCoexistence.EXCLUSIVE

    def __post_init__(self) -> None:
        _validate_extension_id(self.id)
        if not isinstance(self.coexistence, ExtensionCoexistence):
            raise TypeError("extension coexistence must be ExtensionCoexistence")


def _validate_extension_id(value: str) -> str:
    if (
        not value
        or value.strip("abcdefghijklmnopqrstuvwxyz0123456789-_.")
        or any(not part for part in value.split("."))
    ):
        raise ValueError("plugin id must use lowercase ASCII letters, digits, '-', '_' or '.'")
    return value


def _validate_capability(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character.isspace() for character in value)
    ):
        raise ValueError("capability must be a non-empty token without whitespace")
    return value


PluginCallback = Callable[[], Awaitable[None]]
type CleanupCallback = Callable[[], object]


class _PluginCleanup:
    def __init__(self) -> None:
        self._callbacks: list[CleanupCallback] = []
        self._closed = False

    def defer(self, callback: CleanupCallback) -> None:
        if self._closed:
            raise RuntimeError("plugin cleanup is already closed")
        if not callable(callback):
            raise TypeError("plugin cleanup callback must be callable")
        self._callbacks.append(callback)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        errors: list[BaseException] = []
        while self._callbacks:
            callback = self._callbacks.pop()
            try:
                result = callback()
                if inspect.isawaitable(result):
                    await result
            except BaseException as error:
                errors.append(error)
        if errors:
            raise BaseExceptionGroup("plugin cleanup failed", errors)


@dataclass(frozen=True, slots=True)
class PluginHandle:
    start: PluginCallback | None = None
    stop: PluginCallback | None = None
    webui_provider: WebUiProvider | None = None


PluginSetup = Callable[["PluginContext"], Awaitable[PluginHandle | None]]


@dataclass(frozen=True, slots=True)
class ExtensionDefinition:
    manifest: ExtensionManifest
    setup: PluginSetup
    init_spec: PluginInitSpec | None = None

    @property
    def identity(self) -> ExtensionIdentity:
        return ExtensionIdentity(self.manifest.id, self.manifest.coexistence)


# Deprecated source alias for ExtensionDefinition.
PluginDefinition = ExtensionDefinition


@dataclass(frozen=True, slots=True)
class PluginPaths:
    data: Path
    cache: Path


class PluginServices:
    def __init__(self, manifest: PluginManifest, registry: ServiceRegistry) -> None:
        self._manifest = manifest
        self._registry = registry
        self._provided: set[ServiceKey] = set()

    def provide(self, key: ServiceKey, value: Any) -> None:
        if key not in self._manifest.provides:
            raise ServiceError(f"plugin {self._manifest.id} did not declare provided service {key}")
        self._registry.provide(key, value, provider=self._manifest.id)
        self._provided.add(key)

    def require(self, key: ServiceKey) -> Any:
        declared = {requirement.key for requirement in self._manifest.requires}
        if key not in declared:
            raise ServiceError(f"plugin {self._manifest.id} did not declare required service {key}")
        return self._registry.require(key)

    def get_optional(self, key: ServiceKey) -> Any | None:
        requirement = next((item for item in self._manifest.requires if item.key == key), None)
        if requirement is None or not requirement.optional:
            raise ServiceError(f"plugin {self._manifest.id} did not declare optional service {key}")
        return self._registry.get(key)

    def validate_provided(self) -> None:
        missing = set(self._manifest.provides) - self._provided
        if missing:
            rendered = ", ".join(str(key) for key in sorted(missing))
            raise ServiceError(f"plugin {self._manifest.id} did not provide declared services: {rendered}")


@dataclass(frozen=True, slots=True)
class PluginContext:
    id: str
    config: Mapping[str, Any]
    logger: LoggerLike
    services: PluginServices
    tasks: ManagedTasks
    events: EventBus
    actions: ActionServiceLike
    paths: PluginPaths | None
    _manifest: ExtensionManifest = field(repr=False, compare=False)
    _cleanup: _PluginCleanup = field(repr=False, compare=False)
    _tool_handlers: MutableMapping[str, ToolCallback] = field(default_factory=dict, repr=False, compare=False)

    def defer_cleanup(self, callback: CleanupCallback) -> None:
        """Run a synchronous or asynchronous callback during plugin cleanup."""

        self._cleanup.defer(callback)

    def register_tool(self, tool_id: str, handler: ToolCallback) -> None:
        """Register exactly one handler for a Tool declared by this extension."""

        if not isinstance(tool_id, str) or not tool_id.strip():
            raise ValueError("Tool ID must be non-empty")
        declaration = next((tool for tool in self._manifest.tools if tool.id == tool_id), None)
        if declaration is None:
            raise PluginError(f"extension {self.id} did not declare Tool {tool_id!r}")
        del declaration
        if tool_id in self._tool_handlers:
            raise PluginError(f"extension {self.id} registered Tool {tool_id!r} more than once")
        self._tool_handlers[tool_id] = handler


class PluginState(StrEnum):
    DISCOVERED = "discovered"
    SETUP = "setup"
    READY = "ready"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass(slots=True)
class LoadedPlugin:
    definition: PluginDefinition
    context: PluginContext
    handle: PluginHandle
    state: PluginState = PluginState.SETUP


class PluginManager:
    ENTRY_POINT_GROUP = "liteyukibot.plugins"

    def __init__(
        self,
        *,
        services: ServiceRegistry,
        events: EventBus,
        actions: ActionServiceLike,
        logger: LoggerLike,
        data_dir: Path,
        cache_dir: Path,
    ) -> None:
        self.services = services
        self.events = events
        self.actions = actions
        self.logger = logger
        self.data_dir = data_dir
        self.cache_dir = cache_dir
        self.loaded: dict[str, LoadedPlugin] = {}
        self._webui_providers: dict[str, WebUiProvider] = {}
        self._webui_diagnostics: dict[str, WebUiDiagnostic] = {}
        self._webui_generation = 0
        self._tool_handlers: dict[str, tuple[str, ToolDeclaration, ToolCallback]] = {}

    @property
    def tool_handlers(self) -> Mapping[str, tuple[str, ToolDeclaration, ToolCallback]]:
        return dict(self._tool_handlers)

    @property
    def webui_generation(self) -> int:
        """Monotonic provider revision for an owning WebUI bridge to emit reset."""

        return self._webui_generation

    @property
    def webui_diagnostics(self) -> tuple[WebUiDiagnostic, ...]:
        return tuple(self._webui_diagnostics[plugin_id] for plugin_id in sorted(self._webui_diagnostics))

    def webui_surfaces(self) -> tuple[tuple[str, WebUiSurfaceManifest], ...]:
        """Return only active, host-derived Plugin workspace surfaces."""

        values: list[tuple[str, WebUiSurfaceManifest]] = []
        for plugin_id in sorted(self._webui_providers):
            manifest = self.loaded[plugin_id].definition.manifest.webui
            if manifest is not None:
                values.extend((plugin_id, surface) for surface in manifest.surfaces)
        return tuple(values)

    async def webui_snapshot(
        self,
        plugin_id: str,
        surface_id: str,
        capabilities: frozenset[str],
    ) -> WebUiSnapshot:
        """Read one authorized bounded provider snapshot without leaking provider failures."""

        provider = self._webui_providers.get(plugin_id)
        loaded = self.loaded.get(plugin_id)
        manifest = loaded.definition.manifest.webui if loaded is not None else None
        surface = next((item for item in manifest.surfaces if item.id == surface_id), None) if manifest else None
        if provider is None or surface is None:
            return WebUiSnapshot(plugin_id, surface_id, WebUiSnapshotState.UNAVAILABLE, code="surface_unavailable")
        if surface.read_capability not in capabilities:
            return WebUiSnapshot(plugin_id, surface_id, WebUiSnapshotState.UNAVAILABLE, code="not_authorized")
        try:
            result = provider.snapshot(surface_id)
            if inspect.isawaitable(result):
                data = await asyncio.wait_for(result, timeout=WEBUI_SNAPSHOT_TIMEOUT_SECONDS)
            else:
                data = result
            if not isinstance(data, Mapping):
                raise TypeError("snapshot must return a mapping")
            normalized = _normalize_json_mapping(data)
            encoded = json.dumps(normalized, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode()
            if len(encoded) > WEBUI_SNAPSHOT_MAX_BYTES:
                return WebUiSnapshot(plugin_id, surface_id, WebUiSnapshotState.UNAVAILABLE, code="snapshot_too_large")
            Draft202012Validator(surface.data_schema).validate(normalized)
            if _table_rows_exceed_limit(normalized, surface.components):
                return WebUiSnapshot(plugin_id, surface_id, WebUiSnapshotState.UNAVAILABLE, code="table_row_limit")
        except TimeoutError:
            return WebUiSnapshot(plugin_id, surface_id, WebUiSnapshotState.UNAVAILABLE, code="snapshot_timeout")
        except TypeError, ValueError, ValidationError:
            return WebUiSnapshot(plugin_id, surface_id, WebUiSnapshotState.UNAVAILABLE, code="invalid_snapshot")
        except Exception:
            return WebUiSnapshot(plugin_id, surface_id, WebUiSnapshotState.UNAVAILABLE, code="provider_failed")
        return WebUiSnapshot(plugin_id, surface_id, WebUiSnapshotState.AVAILABLE, data=normalized)

    def _register_webui_provider(self, plugin_id: str, plugin: LoadedPlugin) -> None:
        manifest = plugin.definition.manifest.webui
        provider = plugin.handle.webui_provider
        if manifest is None:
            return
        if manifest.api_version != WEBUI_API_VERSION:
            self._webui_diagnostics[plugin_id] = WebUiDiagnostic(plugin_id, "unsupported_webui_api")
            return
        if provider is None:
            self._webui_diagnostics[plugin_id] = WebUiDiagnostic(plugin_id, "webui_provider_missing")
            return
        active_keys: set[str] = set()
        for active_id in self._webui_providers:
            active_manifest = self.loaded[active_id].definition.manifest.webui
            if active_manifest is not None:
                active_keys.update(active_manifest.i18n_keys)
        if active_keys.intersection(manifest.i18n_keys):
            self._webui_diagnostics[plugin_id] = WebUiDiagnostic(plugin_id, "webui_i18n_duplicate")
            return
        if not _contribution_i18n_is_owned(plugin_id, manifest):
            self._webui_diagnostics[plugin_id] = WebUiDiagnostic(plugin_id, "webui_i18n_namespace")
            return
        self._webui_providers[plugin_id] = provider
        self._webui_diagnostics.pop(plugin_id, None)
        self._webui_generation += 1

    def _withdraw_webui_provider(self, plugin_id: str) -> None:
        self._webui_diagnostics.pop(plugin_id, None)
        if self._webui_providers.pop(plugin_id, None) is not None:
            self._webui_generation += 1

    def discover(self, enabled: Sequence[str], local_modules: Sequence[str] = ()) -> dict[str, PluginDefinition]:
        wanted = set(enabled)
        definitions: dict[str, PluginDefinition] = {}
        entry_points = {item.name: item for item in metadata.entry_points(group=self.ENTRY_POINT_GROUP)}
        for plugin_id in sorted(wanted):
            entry_point = entry_points.get(plugin_id)
            if entry_point is None:
                continue
            try:
                candidate = entry_point.load()
            except Exception as error:
                raise PluginError(f"plugin {plugin_id} entry point could not be imported") from error
            self._insert_definition(definitions, self._coerce_definition(candidate), plugin_id)
        for module_name in local_modules:
            try:
                module = import_module(module_name)
                candidate = getattr(module, "plugin", None)
                if candidate is None and callable(getattr(module, "get_plugin", None)):
                    candidate = module.get_plugin()
            except Exception as error:
                raise PluginError(f"local plugin module {module_name} could not be imported") from error
            definition = self._coerce_definition(candidate)
            if definition.manifest.id not in wanted:
                raise PluginError(f"local plugin {definition.manifest.id} is not present in the enabled plugin list")
            self._insert_definition(definitions, definition, definition.manifest.id)
        missing = wanted - definitions.keys()
        if missing:
            raise PluginError(f"enabled plugins were not found: {', '.join(sorted(missing))}")
        return definitions

    @classmethod
    def discover_installed(cls) -> tuple[dict[str, PluginDefinition], tuple[str, ...]]:
        """Discover entry-point plugins for setup clients without failing on unrelated packages."""

        definitions: dict[str, PluginDefinition] = {}
        diagnostics: list[str] = []
        for entry_point in sorted(metadata.entry_points(group=cls.ENTRY_POINT_GROUP), key=lambda item: item.name):
            try:
                candidate = entry_point.load()
                definition = cls._coerce_definition(candidate)
                cls._insert_definition(definitions, definition, entry_point.name)
            except Exception as error:
                diagnostics.append(f"plugin {entry_point.name!r} is unavailable: {type(error).__name__}: {error}")
        return definitions, tuple(diagnostics)

    @staticmethod
    def _coerce_definition(candidate: Any) -> PluginDefinition:
        if not isinstance(candidate, PluginDefinition):
            raise PluginError("plugin entry point must resolve to PluginDefinition")
        if not inspect.iscoroutinefunction(candidate.setup):
            raise PluginError(f"plugin {candidate.manifest.id} setup must be async")
        return candidate

    @staticmethod
    def _insert_definition(
        definitions: dict[str, PluginDefinition], definition: PluginDefinition, expected_id: str
    ) -> None:
        plugin_id = definition.manifest.id
        if plugin_id != expected_id:
            raise PluginError(f"plugin entry point {expected_id} declared mismatched id {plugin_id}")
        if plugin_id in definitions:
            raise PluginError(f"duplicate plugin id: {plugin_id}")
        definitions[plugin_id] = definition

    def resolve_order(self, definitions: Mapping[str, PluginDefinition]) -> tuple[str, ...]:
        provided_services = {registration.key: registration.provider for registration in self.services.snapshot()}
        return self.resolve_definitions(definitions, provided_services)

    @staticmethod
    def identities(definitions: Mapping[str, PluginDefinition]) -> tuple[ExtensionIdentity, ...]:
        """Return native extension identities for cross-host topology validation."""

        return tuple(definitions[plugin_id].identity for plugin_id in sorted(definitions))

    @staticmethod
    def resolve_definitions(
        definitions: Mapping[str, PluginDefinition],
        provided_services: Mapping[ServiceKey, str] | None = None,
    ) -> tuple[str, ...]:
        """Resolve a plugin topology from package metadata without loading plugins."""

        existing_providers = provided_services or {}
        providers: dict[ServiceKey, str] = {}
        for plugin_id, definition in definitions.items():
            for key in definition.manifest.provides:
                existing = providers.get(key) or existing_providers.get(key)
                if existing is not None:
                    raise PluginError(f"service {key} has multiple providers: {existing}, {plugin_id}")
                providers[key] = plugin_id

        dependencies: dict[str, set[str]] = {plugin_id: set() for plugin_id in definitions}
        for plugin_id, definition in definitions.items():
            for requirement in definition.manifest.requires:
                provider = providers.get(requirement.key) or existing_providers.get(requirement.key)
                if provider is None:
                    if requirement.optional:
                        continue
                    raise PluginError(f"plugin {plugin_id} requires unavailable service {requirement.key}")
                if provider in definitions and provider != plugin_id:
                    dependencies[plugin_id].add(provider)

        order: list[str] = []
        pending = {plugin_id: set(required) for plugin_id, required in dependencies.items()}
        while pending:
            ready = sorted(plugin_id for plugin_id, required in pending.items() if not required)
            if not ready:
                cycle = ", ".join(sorted(pending))
                raise PluginError(f"plugin service dependency cycle: {cycle}")
            for plugin_id in ready:
                order.append(plugin_id)
                del pending[plugin_id]
                for required in pending.values():
                    required.discard(plugin_id)
        return tuple(order)

    async def setup(
        self,
        definitions: Mapping[str, PluginDefinition],
        configs: Mapping[str, Mapping[str, Any]],
    ) -> None:
        for plugin_id in self.resolve_order(definitions):
            definition = definitions[plugin_id]
            manifest = definition.manifest
            authorizer = self.services.get(ServiceKey("liteyukibot.permissions", 2))
            activation_allowed = getattr(authorizer, "activation_allowed", None)
            if manifest.capabilities and (
                not callable(activation_allowed)
                or not activation_allowed(manifest.id, frozenset(manifest.capabilities))
            ):
                raise PluginError(f"extension {manifest.id} requested capabilities outside its configured ceiling")
            logger = self.logger.bind(plugin=plugin_id, component="plugin")
            tasks = ManagedTasks(
                plugin_id,
                partial(_log_task_failure, logger),
            )
            paths = self._create_paths(plugin_id) if manifest.storage == "private" else None
            plugin_services = PluginServices(manifest, self.services)
            cleanup = _PluginCleanup()
            tool_handlers: dict[str, ToolCallback] = {}
            context = PluginContext(
                id=plugin_id,
                config=MappingProxyType(dict(configs.get(plugin_id, {}))),
                logger=logger,
                services=plugin_services,
                tasks=tasks,
                events=self.events,
                actions=self.actions,
                paths=paths,
                _manifest=manifest,
                _cleanup=cleanup,
                _tool_handlers=tool_handlers,
            )
            handle = PluginHandle()
            try:
                handle = await definition.setup(context) or handle
                plugin_services.validate_provided()
                declared_tools = {tool.id: tool for tool in manifest.tools}
                if set(tool_handlers) != set(declared_tools):
                    raise PluginError(
                        f"extension {manifest.id} must register exactly one handler for each declared Tool"
                    )
                self._tool_handlers.update(
                    (tool_id, (manifest.id, declared_tools[tool_id], callback))
                    for tool_id, callback in tool_handlers.items()
                )
            except Exception as exc:
                try:
                    if handle.stop is not None:
                        await handle.stop()
                except BaseException:
                    logger.exception("plugin {} stop after setup failure failed", plugin_id)
                finally:
                    try:
                        await cleanup.close()
                    except BaseException:
                        logger.exception("plugin {} cleanup after setup failure failed", plugin_id)
                    finally:
                        try:
                            await tasks.stop()
                        finally:
                            self.services.remove_provider(plugin_id)
                raise PluginError(f"plugin {plugin_id} setup failed") from exc
            self.loaded[plugin_id] = LoadedPlugin(definition, context, handle)

    async def start(self) -> None:
        for plugin in self.loaded.values():
            if plugin.handle.start is not None:
                await plugin.handle.start()
            plugin.state = PluginState.READY
            self._register_webui_provider(plugin.definition.manifest.id, plugin)

    async def stop(self) -> None:
        errors: list[BaseException] = []
        for plugin in reversed(tuple(self.loaded.values())):
            self._withdraw_webui_provider(plugin.definition.manifest.id)
            try:
                if plugin.handle.stop is not None:
                    await plugin.handle.stop()
            except BaseException as error:
                errors.append(error)
            finally:
                try:
                    await plugin.context._cleanup.close()
                except BaseException as error:
                    errors.append(error)
                try:
                    await plugin.context.tasks.stop()
                except BaseException as error:
                    errors.append(error)
                self.services.remove_provider(plugin.definition.manifest.id)
                plugin.state = PluginState.STOPPED
        if errors:
            raise BaseExceptionGroup("plugin shutdown failed", errors)

    def _create_paths(self, plugin_id: str) -> PluginPaths:
        data = self.data_dir / "plugins" / plugin_id
        cache = self.cache_dir / "plugins" / plugin_id
        data.mkdir(parents=True, exist_ok=True)
        cache.mkdir(parents=True, exist_ok=True)
        return PluginPaths(data=data, cache=cache)


def _contribution_i18n_is_owned(plugin_id: str, manifest: WebUiContributionManifest) -> bool:
    prefix = f"webui.plugin.{plugin_id}."
    keys = set(manifest.i18n_keys)
    referenced = {
        key
        for surface in manifest.surfaces
        for component in _walk_components(surface.components)
        for key in (surface.title_key, surface.summary_key, component.title_key, component.summary_key)
        if key is not None
    }
    return all(key.startswith(prefix) for key in keys | referenced) and referenced.issubset(keys)


def _normalize_json_mapping(value: Mapping[str, object]) -> dict[str, JsonValue]:
    encoded = json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise TypeError("snapshot must serialize as a JSON object")
    return cast(dict[str, JsonValue], decoded)


def _table_rows_exceed_limit(data: Mapping[str, JsonValue], components: Sequence[WebUiComponent]) -> bool:
    for component in _walk_components(components):
        if component.kind != "table":
            continue
        value: object = data
        for part in component.data_path:
            if not isinstance(value, dict):
                return True
            value = value.get(part)
        if not isinstance(value, list) or len(value) > WEBUI_TABLE_MAX_ROWS:
            return True
    return False
