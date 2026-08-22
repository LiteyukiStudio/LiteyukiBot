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
from typing import TYPE_CHECKING, Any, Literal, Protocol, cast

from jsonschema import Draft202012Validator, SchemaError, ValidationError
from pydantic import BaseModel, ConfigDict, field_validator

from .authorization import AuthorizationContext
from .events import ActionEnvelope, ActionResult, EventBus, EventEnvelope
from .exceptions import PluginError, ServiceError
from .init_specs import PluginInitSpec
from .resource_packs import ResourcePackDeclaration
from .runtime_api import (
    RuntimeCallContext,
    RuntimeContextFactory,
    RuntimeNamespaceProxy,
    RuntimeRequirement,
    RuntimeResolver,
    runtime_handler,
    validate_runtime_bindings,
)
from .services import ServiceKey, ServiceRegistry, ServiceRequirement
from .tasks import ManagedTasks

if TYPE_CHECKING:
    from .functions import FunctionHost

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
    """Validate webui token.

    Args:
        value: Value to validate, transform, or store.
        field: The field value used by the operation.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_validate_webui_token`. It delegates to `fullmatch` while
        keeping intermediate state local to the owning operation.
    """
    if not _WEBUI_TOKEN.fullmatch(value):
        raise ValueError(f"{field} must use lowercase ASCII letters, digits, or '-'")
    return value


def _validate_webui_key(value: str, field: str) -> str:
    """Validate webui key.

    Args:
        value: Value to validate, transform, or store.
        field: The field value used by the operation.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_validate_webui_key`. It delegates to `strip`, `any`,
        `split` while keeping intermediate state local to the owning operation.
    """
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
        """Validate id.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.
        """
        return _validate_webui_token(value, "webui component id")

    @field_validator("title_key", "summary_key")
    @classmethod
    def validate_i18n_key(cls, value: str | None, info: Any) -> str | None:
        """Validate i18n key.

        Args:
            value: Value to validate, transform, or store.
            info: The info value used by the operation.

        Returns:
            The `str | None` result produced by the operation.
        """
        return _validate_webui_key(value, info.field_name) if value is not None else value

    @field_validator("data_path")
    @classmethod
    def validate_data_path(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Validate data path.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `tuple[str, ...]` result produced by the operation.
        """
        if any(not _WEBUI_PATH_TOKEN.fullmatch(part) for part in value):
            raise ValueError("webui data_path must contain object field names")
        return value

    @field_validator("operation_id")
    @classmethod
    def validate_operation_id(cls, value: str | None) -> str | None:
        """Validate operation id.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str | None` result produced by the operation.
        """
        if value is not None and (not value or value != value.strip() or " " in value):
            raise ValueError("webui operation_id must be a non-empty operation identifier")
        return value

    def model_post_init(self, __context: Any) -> None:
        """Implement the model post init operation for the web ui component.

        Args:
            __context: The context value used by the operation.

        Returns:
            None.
        """
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
        """Validate id.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.
        """
        return _validate_webui_token(value, "webui surface id")

    @field_validator("title_key", "summary_key")
    @classmethod
    def validate_i18n_key(cls, value: str | None, info: Any) -> str | None:
        """Validate i18n key.

        Args:
            value: Value to validate, transform, or store.
            info: The info value used by the operation.

        Returns:
            The `str | None` result produced by the operation.
        """
        return _validate_webui_key(value, info.field_name) if value is not None else value

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, value: str) -> str:
        """Validate icon.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.
        """
        if value not in _WEBUI_ICON_NAMES:
            raise ValueError("webui icon is not host-approved")
        return value

    @field_validator("read_capability")
    @classmethod
    def validate_read_capability(cls, value: str) -> str:
        """Validate read capability.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.
        """
        if not value or value != value.strip() or " " in value:
            raise ValueError("webui read_capability must be a non-empty capability identifier")
        return value

    @field_validator("operation_ids")
    @classmethod
    def validate_operation_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Validate operation ids.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `tuple[str, ...]` result produced by the operation.
        """
        if len(value) != len(set(value)):
            raise ValueError("webui operation_ids must be unique")
        for operation_id in value:
            if not operation_id or operation_id != operation_id.strip() or " " in operation_id:
                raise ValueError("webui operation_ids must contain operation identifiers")
        return value

    def model_post_init(self, __context: Any) -> None:
        """Implement the model post init operation for the web ui surface manifest.

        Args:
            __context: The context value used by the operation.

        Returns:
            None.
        """
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
        """Route the web ui surface manifest operation.

        Args:
            plugin_id: Stable identifier for the plugin.

        Returns:
            The `str` result produced by the operation.
        """
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
        """Validate api version.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `int` result produced by the operation.
        """
        if value < 1:
            raise ValueError("webui api_version must be positive")
        return value

    @field_validator("i18n_keys")
    @classmethod
    def validate_i18n_keys(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Validate i18n keys.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `tuple[str, ...]` result produced by the operation.
        """
        if len(value) != len(set(value)):
            raise ValueError("webui i18n_keys must be unique")
        return tuple(_validate_webui_key(key, "webui i18n key") for key in value)

    def model_post_init(self, __context: Any) -> None:
        """Implement the model post init operation for the web ui contribution manifest.

        Args:
            __context: The context value used by the operation.

        Returns:
            None.
        """
        if len(self.surfaces) > 16:
            raise ValueError("webui contribution supports at most 16 surfaces")
        ids = [surface.id for surface in self.surfaces]
        if len(ids) != len(set(ids)):
            raise ValueError("webui surface ids must be unique")


def _walk_components(components: Sequence[WebUiComponent]) -> tuple[WebUiComponent, ...]:
    """Implement the walk components operation for the component.

    Args:
        components: The components value used by the operation.

    Returns:
        The `tuple[WebUiComponent, ...]` result produced by the operation.

    Notes:
        Internal implementation detail for `_walk_components`. It delegates to `append`, `extend`,
        `_walk_components` while keeping intermediate state local to the owning operation.
    """
    values: list[WebUiComponent] = []
    for component in components:
        values.append(component)
        values.extend(_walk_components(component.children))
    return tuple(values)


def _component_ids(components: Sequence[WebUiComponent]) -> tuple[str, ...]:
    """Implement the component ids operation for the component.

    Args:
        components: The components value used by the operation.

    Returns:
        The `tuple[str, ...]` result produced by the operation.

    Notes:
        Internal implementation detail for `_component_ids`. It delegates to `_walk_components` while
        keeping intermediate state local to the owning operation.
    """
    return tuple(component.id for component in _walk_components(components))


class WebUiProvider(Protocol):
    """Define the structural interface required from a web ui provider."""
    def snapshot(self, surface_id: str) -> Mapping[str, object] | Awaitable[Mapping[str, object]]:
        """Return an immutable snapshot of the web ui provider state.

        Args:
            surface_id: Stable identifier for the surface.

        Returns:
            The requested `Mapping[str, object] | Awaitable[Mapping[str, object]]` value.
        """
        ...


class WebUiSnapshotState(StrEnum):
    """Enumerate the supported web ui snapshot state values."""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class WebUiSnapshot:
    """Represent the validated web ui snapshot contract."""
    plugin_id: str
    surface_id: str
    state: WebUiSnapshotState
    data: Mapping[str, JsonValue] | None = None
    code: str | None = None


@dataclass(frozen=True, slots=True)
class WebUiDiagnostic:
    """Represent the web ui diagnostic contract."""
    plugin_id: str
    code: str


class LoggerLike(Protocol):
    """Define the structural interface required from a logger like."""
    def bind(self, **fields: Any) -> LoggerLike:
        """Bind the logger like operation.

        Args:
            **fields: Structured fields attached to the operation.

        Returns:
            The `LoggerLike` result produced by the operation.
        """
        ...

    def contextualize(self, **fields: Any) -> AbstractContextManager[None]:
        """Implement the contextualize operation for the logger like.

        Args:
            **fields: Structured fields attached to the operation.

        Returns:
            The `AbstractContextManager[None]` result produced by the operation.
        """
        ...

    def trace(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Implement the trace operation for the logger like.

        Args:
            message: Message content associated with the operation.
            *args: The args value used by the operation.
            **kwargs: The kwargs value used by the operation.

        Returns:
            None.
        """
        ...

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Implement the debug operation for the logger like.

        Args:
            message: Message content associated with the operation.
            *args: The args value used by the operation.
            **kwargs: The kwargs value used by the operation.

        Returns:
            None.
        """
        ...

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Implement the info operation for the logger like.

        Args:
            message: Message content associated with the operation.
            *args: The args value used by the operation.
            **kwargs: The kwargs value used by the operation.

        Returns:
            None.
        """
        ...

    def success(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Implement the success operation for the logger like.

        Args:
            message: Message content associated with the operation.
            *args: The args value used by the operation.
            **kwargs: The kwargs value used by the operation.

        Returns:
            None.
        """
        ...

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Implement the warning operation for the logger like.

        Args:
            message: Message content associated with the operation.
            *args: The args value used by the operation.
            **kwargs: The kwargs value used by the operation.

        Returns:
            None.
        """
        ...

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Implement the error operation for the logger like.

        Args:
            message: Message content associated with the operation.
            *args: The args value used by the operation.
            **kwargs: The kwargs value used by the operation.

        Returns:
            None.
        """
        ...

    def critical(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Implement the critical operation for the logger like.

        Args:
            message: Message content associated with the operation.
            *args: The args value used by the operation.
            **kwargs: The kwargs value used by the operation.

        Returns:
            None.
        """
        ...

    def exception(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Implement the exception operation for the logger like.

        Args:
            message: Message content associated with the operation.
            *args: The args value used by the operation.
            **kwargs: The kwargs value used by the operation.

        Returns:
            None.
        """
        ...


class ActionServiceLike(Protocol):
    """Define the structural interface required from a action service like."""
    async def execute(self, action: ActionEnvelope, *, event: EventEnvelope | None = None) -> ActionResult:
        """Execute one request through the action service like.

        Args:
            action: Action request being processed.
            event: Event associated with the operation.

        Returns:
            The `ActionResult` result produced by the operation.
        """
        ...


def _log_task_failure(logger: LoggerLike, name: str, error: BaseException) -> None:
    """Implement the log task failure operation for the component.

    Args:
        logger: Structured logger used for diagnostics.
        name: Stable name used to identify the value.
        error: The error value used by the operation.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_log_task_failure`. It delegates to `error` while keeping
        intermediate state local to the owning operation.
    """
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
        """Validate required text.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.
        """
        if not value or value != value.strip():
            raise ValueError("tool metadata must be non-empty and trimmed")
        return value

    @field_validator("input_schema", "output_schema")
    @classmethod
    def validate_schema(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        """Validate schema.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `Mapping[str, JsonValue]` result produced by the operation.
        """
        try:
            Draft202012Validator.check_schema(dict(value))
        except SchemaError as error:
            raise ValueError("tool schema must be Draft 2020-12 compatible") from error
        return MappingProxyType(dict(value))

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Validate capabilities.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `tuple[str, ...]` result produced by the operation.
        """
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
    runtime_requirements: tuple[RuntimeRequirement, ...] = ()
    tools: tuple[ToolDeclaration, ...] = ()
    webui: WebUiContributionManifest | None = None

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        """Validate id.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.
        """
        return _validate_extension_id(value)

    @field_validator("name", "version")
    @classmethod
    def validate_required_metadata(cls, value: str) -> str:
        """Validate required metadata.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.
        """
        if not value.strip():
            raise ValueError("plugin manifest metadata must not be blank")
        return value

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Validate capabilities.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `tuple[str, ...]` result produced by the operation.
        """
        if len(set(value)) != len(value):
            raise ValueError("extension capabilities must not contain duplicates")
        for capability in value:
            _validate_capability(capability)
        return value

    @field_validator("runtime_requirements")
    @classmethod
    def validate_runtime_requirements(cls, value: tuple[RuntimeRequirement, ...]) -> tuple[RuntimeRequirement, ...]:
        """Validate runtime requirements.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `tuple[RuntimeRequirement, ...]` result produced by the operation.
        """
        keys = tuple((item.runtime, item.api, item.bridge_id) for item in value)
        if len(keys) != len(set(keys)):
            raise ValueError("extension runtime requirements must not contain duplicates")
        return value

    @field_validator("tools")
    @classmethod
    def validate_tools(cls, value: tuple[ToolDeclaration, ...], info: Any) -> tuple[ToolDeclaration, ...]:
        """Validate tools.

        Args:
            value: Value to validate, transform, or store.
            info: The info value used by the operation.

        Returns:
            The `tuple[ToolDeclaration, ...]` result produced by the operation.
        """
        extension_id = info.data.get("id")
        if not isinstance(extension_id, str):
            return value
        if len({tool.id for tool in value}) != len(value):
            raise ValueError("extension tools must not contain duplicate IDs")
        prefix = f"{extension_id}."
        if any(not tool.id.startswith(prefix) for tool in value):
            raise ValueError("tool IDs must be prefixed by their extension ID")
        return value

    @property
    def runtime_capabilities(self) -> frozenset[str]:
        """Return the extension manifest's runtime capabilities.

        Returns:
            The `frozenset[str]` result produced by the operation.
        """
        return frozenset(
            capability
            for requirement in self.runtime_requirements
            for capability in requirement.capability_names
        )


# Deprecated source alias. It constructs Extension API v2 values, while an
# explicit api_version=1 is rejected by the v2 literal above.
PluginManifest = ExtensionManifest


@dataclass(frozen=True, slots=True)
class ExtensionIdentity:
    """Host-neutral extension identity exposed during startup topology resolution."""

    id: str
    coexistence: ExtensionCoexistence = ExtensionCoexistence.EXCLUSIVE

    def __post_init__(self) -> None:
        """Validate and normalize the extension identity after initialization.

        Returns:
            None.
        """
        _validate_extension_id(self.id)
        if not isinstance(self.coexistence, ExtensionCoexistence):
            raise TypeError("extension coexistence must be ExtensionCoexistence")


def _validate_extension_id(value: str) -> str:
    """Validate extension id.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_validate_extension_id`. It delegates to `strip`, `any`,
        `split` while keeping intermediate state local to the owning operation.
    """
    if (
        not value
        or value.strip("abcdefghijklmnopqrstuvwxyz0123456789-_.")
        or any(not part for part in value.split("."))
    ):
        raise ValueError("plugin id must use lowercase ASCII letters, digits, '-', '_' or '.'")
    return value


def _validate_capability(value: str) -> str:
    """Validate capability.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_validate_capability`. It delegates to `strip`, `any`,
        `isspace` while keeping intermediate state local to the owning operation.
    """
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


def _default_runtime_context_factory(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> RuntimeCallContext:
    """Implement the default runtime context factory operation for the component.

    Args:
        args: The args value used by the operation.
        kwargs: The kwargs value used by the operation.

    Returns:
        The `RuntimeCallContext` result produced by the operation.

    Notes:
        Internal implementation detail for `_default_runtime_context_factory`. It delegates to `values`,
        `next` while keeping intermediate state local to the owning operation.
    """
    values = (*args, *kwargs.values())
    event = next((value for value in values if isinstance(value, EventEnvelope)), None)
    if event is None:
        raise RuntimeError("runtime API calls require an active EventEnvelope")
    authorization = next((value for value in values if isinstance(value, AuthorizationContext)), None)
    if authorization is None:
        authorization = AuthorizationContext(
            event_id=event.id,
            runtime_id=event.runtime_id,
            bot_id=event.bot_id,
            actor_id=None if event.actor is None else event.actor.id,
        )
    elif authorization.event_id != event.id:
        raise RuntimeError("runtime API authorization does not match the active event")
    return RuntimeCallContext(extension_id="unknown", event=event, authorization=authorization)


def _unavailable_runtime_resolver(binding: Any, context: RuntimeCallContext) -> RuntimeNamespaceProxy:
    """Implement the unavailable runtime resolver operation for the component.

    Args:
        binding: The binding value used by the operation.
        context: Runtime or authorization context for the operation.

    Returns:
        The `RuntimeNamespaceProxy` result produced by the operation.

    Notes:
        Internal implementation detail for `_unavailable_runtime_resolver`. It performs the local state
        transition directly and is not a stable extension boundary.
    """
    return RuntimeNamespaceProxy(binding, None, context, reason="runtime bridge is not configured")


class PluginEventBus:
    """Plugin-owned EventBus facade that injects declared runtime proxies."""

    def __init__(
        self,
        events: EventBus,
        *,
        context_factory: RuntimeContextFactory,
        resolver: RuntimeResolver,
        requirements: tuple[RuntimeRequirement, ...] = (),
    ) -> None:
        """Initialize the plugin event bus.

        Args:
            events: The events value used by the operation.
            context_factory: The context factory value used by the operation.
            resolver: The resolver value used by the operation.
            requirements: The requirements value used by the operation.

        Returns:
            None.
        """
        self._events = events
        self._context_factory = context_factory
        self._resolver = resolver
        self._requirements = requirements

    @property
    def closed(self) -> bool:
        """Return the plugin event bus's closed.

        Returns:
            Whether the requested condition is satisfied.
        """
        return self._events.closed

    @property
    def outstanding(self) -> int:
        """Return the plugin event bus's outstanding.

        Returns:
            The `int` result produced by the operation.
        """
        return self._events.outstanding

    def subscribe(self, handler: Callable[..., Any], *, order: int = 0, name: str | None = None) -> Any:
        """Register a handler and return its subscription.

        Args:
            handler: Callable that handles the dispatched value.
            order: Relative handler ordering; lower values run first.
            name: Stable name used to identify the value.

        Returns:
            The `Any` result produced by the operation.
        """
        validate_runtime_bindings(handler, self._requirements)
        wrapped = runtime_handler(
            handler,
            context_factory=self._context_factory,
            resolver=self._resolver,
        )
        return self._events.subscribe(cast(Any, wrapped), order=order, name=name)

    def unsubscribe(self, subscription: Any) -> bool:
        """Remove a previously registered subscription.

        Args:
            subscription: Previously returned subscription to remove.

        Returns:
            Whether the requested condition is satisfied.
        """
        return self._events.unsubscribe(subscription)

    def __getattr__(self, name: str) -> Any:
        """Implement the getattr operation for the plugin event bus.

        Args:
            name: Stable name used to identify the value.

        Returns:
            The `Any` result produced by the operation.
        """
        return getattr(self._events, name)


class _PluginCleanup:
    """Represent the plugin cleanup contract."""
    def __init__(self) -> None:
        """Initialize the plugin cleanup.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_PluginCleanup.__init__`. It performs the local state
            transition directly and is not a stable extension boundary.
        """
        self._callbacks: list[CleanupCallback] = []
        self._closed = False

    def defer(self, callback: CleanupCallback) -> None:
        """Implement the defer operation for the plugin cleanup.

        Args:
            callback: Callback invoked by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_PluginCleanup.defer`. It delegates to `callable`, `append`
            while keeping intermediate state local to the owning operation.
        """
        if self._closed:
            raise RuntimeError("plugin cleanup is already closed")
        if not callable(callback):
            raise TypeError("plugin cleanup callback must be callable")
        self._callbacks.append(callback)

    async def close(self) -> None:
        """Close the plugin cleanup and release its owned resources.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_PluginCleanup.close`. It delegates to `pop`, `callback`,
            `isawaitable`, `append` while keeping intermediate state local to the owning operation.
        """
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
    """Represent the plugin handle contract."""
    start: PluginCallback | None = None
    stop: PluginCallback | None = None
    webui_provider: WebUiProvider | None = None


PluginSetup = Callable[["PluginContext"], Awaitable[PluginHandle | None]]


@dataclass(frozen=True, slots=True)
class ExtensionDefinition:
    """Represent the extension definition contract."""
    manifest: ExtensionManifest
    setup: PluginSetup
    init_spec: PluginInitSpec | None = None

    @property
    def identity(self) -> ExtensionIdentity:
        """Return the extension definition's identity.

        Returns:
            The `ExtensionIdentity` result produced by the operation.
        """
        return ExtensionIdentity(self.manifest.id, self.manifest.coexistence)


# Deprecated source alias for ExtensionDefinition.
PluginDefinition = ExtensionDefinition


@dataclass(frozen=True, slots=True)
class PluginPaths:
    """Represent the plugin paths contract."""
    data: Path
    cache: Path


class PluginServices:
    """Represent the plugin services contract."""
    def __init__(self, manifest: PluginManifest, registry: ServiceRegistry) -> None:
        """Initialize the plugin services.

        Args:
            manifest: Validated manifest describing the component contract.
            registry: The registry value used by the operation.

        Returns:
            None.
        """
        self._manifest = manifest
        self._registry = registry
        self._provided: set[ServiceKey] = set()

    def provide(self, key: ServiceKey, value: Any) -> None:
        """Implement the provide operation for the plugin services.

        Args:
            key: Stable FIFO ordering key for the queued work.
            value: Value to validate, transform, or store.

        Returns:
            None.
        """
        if key not in self._manifest.provides:
            raise ServiceError(f"plugin {self._manifest.id} did not declare provided service {key}")
        self._registry.provide(key, value, provider=self._manifest.id)
        self._provided.add(key)

    def require(self, key: ServiceKey) -> Any:
        """Return the plugin services operation, failing when it is unavailable.

        Args:
            key: Stable FIFO ordering key for the queued work.

        Returns:
            The requested `Any` value.
        """
        declared = {requirement.key for requirement in self._manifest.requires}
        if key not in declared:
            raise ServiceError(f"plugin {self._manifest.id} did not declare required service {key}")
        return self._registry.require(key)

    def get_optional(self, key: ServiceKey) -> Any | None:
        """Return optional.

        Args:
            key: Stable FIFO ordering key for the queued work.

        Returns:
            The requested `Any | None` value.
        """
        requirement = next((item for item in self._manifest.requires if item.key == key), None)
        if requirement is None or not requirement.optional:
            raise ServiceError(f"plugin {self._manifest.id} did not declare optional service {key}")
        return self._registry.get(key)

    def validate_provided(self) -> None:
        """Validate provided.

        Returns:
            None.
        """
        missing = set(self._manifest.provides) - self._provided
        if missing:
            rendered = ", ".join(str(key) for key in sorted(missing))
            raise ServiceError(f"plugin {self._manifest.id} did not provide declared services: {rendered}")


@dataclass(frozen=True, slots=True)
class PluginContext:
    """Represent the plugin context contract."""
    id: str
    config: Mapping[str, Any]
    logger: LoggerLike
    services: PluginServices
    tasks: ManagedTasks
    events: PluginEventBus
    actions: ActionServiceLike
    paths: PluginPaths | None
    function_host: FunctionHost | None
    _manifest: ExtensionManifest = field(repr=False, compare=False)
    _cleanup: _PluginCleanup = field(repr=False, compare=False)
    _runtime_context_factory: RuntimeContextFactory = field(
        default=_default_runtime_context_factory, repr=False, compare=False
    )
    _runtime_resolver: RuntimeResolver = field(default=_unavailable_runtime_resolver, repr=False, compare=False)
    _tool_handlers: MutableMapping[str, ToolCallback] = field(default_factory=dict, repr=False, compare=False)

    def defer_cleanup(self, callback: CleanupCallback) -> None:
        """Run a synchronous or asynchronous callback during plugin cleanup.

        Args:
            callback: Callback invoked by the operation.

        Returns:
            None.
        """

        self._cleanup.defer(callback)

    def register_tool(self, tool_id: str, handler: ToolCallback) -> None:
        """Register exactly one handler for a Tool declared by this extension.

        Args:
            tool_id: Stable identifier for the tool.
            handler: Callable that handles the dispatched value.

        Returns:
            None.
        """

        if not isinstance(tool_id, str) or not tool_id.strip():
            raise ValueError("Tool ID must be non-empty")
        declaration = next((tool for tool in self._manifest.tools if tool.id == tool_id), None)
        if declaration is None:
            raise PluginError(f"extension {self.id} did not declare Tool {tool_id!r}")
        del declaration
        if tool_id in self._tool_handlers:
            raise PluginError(f"extension {self.id} registered Tool {tool_id!r} more than once")
        validate_runtime_bindings(handler, self._manifest.runtime_requirements)
        self._tool_handlers[tool_id] = cast(
            ToolCallback,
            runtime_handler(
                handler,
                context_factory=self._runtime_context_factory,
                resolver=self._runtime_resolver,
            ),
        )


class PluginState(StrEnum):
    """Enumerate the supported plugin state values."""
    DISCOVERED = "discovered"
    SETUP = "setup"
    READY = "ready"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass(slots=True)
class LoadedPlugin:
    """Represent the loaded plugin contract."""
    definition: PluginDefinition
    context: PluginContext
    handle: PluginHandle
    state: PluginState = PluginState.SETUP


class PluginManager:
    """Represent the plugin manager contract."""
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
        runtime_context_factory: Callable[[str], RuntimeContextFactory] | None = None,
        runtime_resolver: RuntimeResolver | None = None,
        runtime_targets: Mapping[str, str] | None = None,
    ) -> None:
        """Initialize the plugin manager.

        Args:
            services: The services value used by the operation.
            events: The events value used by the operation.
            actions: The actions value used by the operation.
            logger: Structured logger used for diagnostics.
            data_dir: Filesystem path for the data.
            cache_dir: Filesystem path for the cache.
            runtime_context_factory: The runtime context factory value used by the operation.
            runtime_resolver: The runtime resolver value used by the operation.
            runtime_targets: The runtime targets value used by the operation.

        Returns:
            None.
        """
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
        self._runtime_context_factory_factory = runtime_context_factory or (
            lambda _extension_id: _default_runtime_context_factory
        )
        self._runtime_resolver = runtime_resolver or _unavailable_runtime_resolver
        self._runtime_targets = dict(runtime_targets or {})

    @property
    def tool_handlers(self) -> Mapping[str, tuple[str, ToolDeclaration, ToolCallback]]:
        """Return the plugin manager's tool handlers.

        Returns:
            The `Mapping[str, tuple[str, ToolDeclaration, ToolCallback]]` result produced by the operation.
        """
        return dict(self._tool_handlers)

    @property
    def webui_generation(self) -> int:
        """Monotonic provider revision for an owning WebUI bridge to emit reset.

        Returns:
            The `int` result produced by the operation.
        """

        return self._webui_generation

    @property
    def webui_diagnostics(self) -> tuple[WebUiDiagnostic, ...]:
        """Return the plugin manager's webui diagnostics.

        Returns:
            The `tuple[WebUiDiagnostic, ...]` result produced by the operation.
        """
        return tuple(self._webui_diagnostics[plugin_id] for plugin_id in sorted(self._webui_diagnostics))

    def webui_surfaces(self) -> tuple[tuple[str, WebUiSurfaceManifest], ...]:
        """Return only active, host-derived Plugin workspace surfaces.

        Returns:
            The `tuple[tuple[str, WebUiSurfaceManifest], ...]` result produced by the operation.
        """

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
        """Read one authorized bounded provider snapshot without leaking provider failures.

        Args:
            plugin_id: Stable identifier for the plugin.
            surface_id: Stable identifier for the surface.
            capabilities: The capabilities value used by the operation.

        Returns:
            The `WebUiSnapshot` result produced by the operation.
        """

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
        """Register webui provider.

        Args:
            plugin_id: Stable identifier for the plugin.
            plugin: The plugin value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `PluginManager._register_webui_provider`. It delegates to
            `update`, `intersection`, `_contribution_i18n_is_owned`, `pop` while keeping intermediate state
            local to the owning operation.
        """
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
        """Implement the withdraw webui provider operation for the plugin manager.

        Args:
            plugin_id: Stable identifier for the plugin.

        Returns:
            None.

        Notes:
            Internal implementation detail for `PluginManager._withdraw_webui_provider`. It delegates to
            `pop` while keeping intermediate state local to the owning operation.
        """
        self._webui_diagnostics.pop(plugin_id, None)
        if self._webui_providers.pop(plugin_id, None) is not None:
            self._webui_generation += 1

    def discover(self, enabled: Sequence[str], local_modules: Sequence[str] = ()) -> dict[str, PluginDefinition]:
        """Discover the plugin manager operation.

        Args:
            enabled: The enabled value used by the operation.
            local_modules: The local modules value used by the operation.

        Returns:
            The `dict[str, PluginDefinition]` result produced by the operation.
        """
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
        """Discover entry-point plugins for setup clients without failing on unrelated packages.

        Returns:
            The `tuple[dict[str, PluginDefinition], tuple[str, ...]]` result produced by the operation.
        """

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
        """Implement the coerce definition operation for the plugin manager.

        Args:
            candidate: The candidate value used by the operation.

        Returns:
            The `PluginDefinition` result produced by the operation.

        Notes:
            Internal implementation detail for `PluginManager._coerce_definition`. It delegates to
            `iscoroutinefunction` while keeping intermediate state local to the owning operation.
        """
        if not isinstance(candidate, PluginDefinition):
            raise PluginError("plugin entry point must resolve to PluginDefinition")
        if not inspect.iscoroutinefunction(candidate.setup):
            raise PluginError(f"plugin {candidate.manifest.id} setup must be async")
        return candidate

    @staticmethod
    def _insert_definition(
        definitions: dict[str, PluginDefinition], definition: PluginDefinition, expected_id: str
    ) -> None:
        """Implement the insert definition operation for the plugin manager.

        Args:
            definitions: The definitions value used by the operation.
            definition: The definition value used by the operation.
            expected_id: Stable identifier for the expected.

        Returns:
            None.

        Notes:
            Internal implementation detail for `PluginManager._insert_definition`. It performs the local
            state transition directly and is not a stable extension boundary.
        """
        plugin_id = definition.manifest.id
        if plugin_id != expected_id:
            raise PluginError(f"plugin entry point {expected_id} declared mismatched id {plugin_id}")
        if plugin_id in definitions:
            raise PluginError(f"duplicate plugin id: {plugin_id}")
        definitions[plugin_id] = definition

    def resolve_order(self, definitions: Mapping[str, PluginDefinition]) -> tuple[str, ...]:
        """Resolve order.

        Args:
            definitions: The definitions value used by the operation.

        Returns:
            The requested `tuple[str, ...]` value.
        """
        provided_services = {registration.key: registration.provider for registration in self.services.snapshot()}
        return self.resolve_definitions(definitions, provided_services)

    @staticmethod
    def identities(definitions: Mapping[str, PluginDefinition]) -> tuple[ExtensionIdentity, ...]:
        """Return native extension identities for cross-host topology validation.

        Args:
            definitions: The definitions value used by the operation.

        Returns:
            The `tuple[ExtensionIdentity, ...]` result produced by the operation.
        """

        return tuple(definitions[plugin_id].identity for plugin_id in sorted(definitions))

    @staticmethod
    def resolve_definitions(
        definitions: Mapping[str, PluginDefinition],
        provided_services: Mapping[ServiceKey, str] | None = None,
    ) -> tuple[str, ...]:
        """Resolve a plugin topology from package metadata without loading plugins.

        Args:
            definitions: The definitions value used by the operation.
            provided_services: The provided services value used by the operation.

        Returns:
            The requested `tuple[str, ...]` value.
        """

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
        *,
        function_hosts: Mapping[str, FunctionHost] | None = None,
    ) -> None:
        """Implement the setup operation for the plugin manager.

        Args:
            definitions: The definitions value used by the operation.
            configs: The configs value used by the operation.
            function_hosts: The function hosts value used by the operation.

        Returns:
            None.
        """
        for plugin_id in self.resolve_order(definitions):
            definition = definitions[plugin_id]
            manifest = definition.manifest
            missing_runtime_requirements = tuple(
                requirement
                for requirement in manifest.runtime_requirements
                if not requirement.optional
                and not any(
                    kind == requirement.runtime
                    and (requirement.bridge_id is None or bridge_id == requirement.bridge_id)
                    for bridge_id, kind in self._runtime_targets.items()
                )
            )
            if missing_runtime_requirements:
                names = ", ".join(
                    f"{item.runtime}.{item.api}" for item in missing_runtime_requirements
                )
                raise PluginError(f"extension {manifest.id} requires unavailable runtime APIs: {names}")
            authorizer = self.services.get(ServiceKey("liteyukibot.permissions", 2))
            activation_allowed = getattr(authorizer, "activation_allowed", None)
            requested_capabilities = frozenset((*manifest.capabilities, *manifest.runtime_capabilities))
            if requested_capabilities and (
                not callable(activation_allowed)
                or not activation_allowed(manifest.id, requested_capabilities)
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
            runtime_context_factory = self._runtime_context_factory_factory(manifest.id)
            context = PluginContext(
                id=plugin_id,
                config=MappingProxyType(dict(configs.get(plugin_id, {}))),
                logger=logger,
                services=plugin_services,
                tasks=tasks,
                events=PluginEventBus(
                    self.events,
                    context_factory=runtime_context_factory,
                    resolver=self._runtime_resolver,
                    requirements=manifest.runtime_requirements,
                ),
                actions=self.actions,
                paths=paths,
                function_host=None if function_hosts is None else function_hosts.get(manifest.id),
                _manifest=manifest,
                _cleanup=cleanup,
                _tool_handlers=tool_handlers,
                _runtime_context_factory=runtime_context_factory,
                _runtime_resolver=self._runtime_resolver,
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
                detail = ": migration_required" if str(exc) == "migration_required" else ""
                raise PluginError(f"plugin {plugin_id} setup failed{detail}") from exc
            self.loaded[plugin_id] = LoadedPlugin(definition, context, handle)

    async def start(self) -> None:
        """Start the plugin manager.

        Returns:
            None.
        """
        for plugin in self.loaded.values():
            if plugin.handle.start is not None:
                await plugin.handle.start()
            plugin.state = PluginState.READY
            self._register_webui_provider(plugin.definition.manifest.id, plugin)

    async def stop(self) -> None:
        """Stop the plugin manager and release its owned resources.

        Returns:
            None.
        """
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
        """Create paths.

        Args:
            plugin_id: Stable identifier for the plugin.

        Returns:
            The `PluginPaths` result produced by the operation.

        Notes:
            Internal implementation detail for `PluginManager._create_paths`. It delegates to `mkdir` while
            keeping intermediate state local to the owning operation.
        """
        data = self.data_dir / "plugins" / plugin_id
        cache = self.cache_dir / "plugins" / plugin_id
        data.mkdir(parents=True, exist_ok=True)
        cache.mkdir(parents=True, exist_ok=True)
        return PluginPaths(data=data, cache=cache)


def _contribution_i18n_is_owned(plugin_id: str, manifest: WebUiContributionManifest) -> bool:
    """Implement the contribution i18n is owned operation for the component.

    Args:
        plugin_id: Stable identifier for the plugin.
        manifest: Validated manifest describing the component contract.

    Returns:
        Whether the requested condition is satisfied.

    Notes:
        Internal implementation detail for `_contribution_i18n_is_owned`. It delegates to
        `_walk_components`, `all`, `startswith`, `issubset` while keeping intermediate state local to
        the owning operation.
    """
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
    """Normalize json mapping.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `dict[str, JsonValue]` result produced by the operation.

    Notes:
        Internal implementation detail for `_normalize_json_mapping`. It delegates to `dumps`, `loads`,
        `cast` while keeping intermediate state local to the owning operation.
    """
    encoded = json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise TypeError("snapshot must serialize as a JSON object")
    return cast(dict[str, JsonValue], decoded)


def _table_rows_exceed_limit(data: Mapping[str, JsonValue], components: Sequence[WebUiComponent]) -> bool:
    """Implement the table rows exceed limit operation for the component.

    Args:
        data: The data value used by the operation.
        components: The components value used by the operation.

    Returns:
        Whether the requested condition is satisfied.

    Notes:
        Internal implementation detail for `_table_rows_exceed_limit`. It delegates to
        `_walk_components`, `get` while keeping intermediate state local to the owning operation.
    """
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
