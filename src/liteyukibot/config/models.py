from __future__ import annotations

import math
from collections.abc import Mapping
from importlib import import_module, metadata
from ipaddress import ip_address
from pathlib import Path
from platform import platform
from types import MappingProxyType
from typing import Any, Literal, cast

from jsonschema import Draft202012Validator, SchemaError
from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_serializer, model_validator

from ..topic_patterns import validate_topic_pattern

type JsonValue = str | int | float | bool | None | tuple[JsonValue, ...] | Mapping[str, JsonValue]


def _freeze(value: Any) -> Any:
    """Freeze the component operation.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `Any` result produced by the operation.

    Notes:
        Internal implementation detail for `_freeze`. It delegates to `_freeze`, `items`, `frozenset`
        while keeping intermediate state local to the owning operation.
    """
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    """Implement the thaw operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `Any` result produced by the operation.

    Notes:
        Internal implementation detail for `_thaw`. It delegates to `_thaw`, `items` while keeping
        intermediate state local to the owning operation.
    """
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, frozenset)):
        return [_thaw(item) for item in value]
    return value


def _validate_json(value: Any, path: str = "value") -> None:
    """Validate json.

    Args:
        value: Value to validate, transform, or store.
        path: Filesystem or logical resource path.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_validate_json`. It delegates to `isfinite`, `items`,
        `_validate_json`, `enumerate` while keeping intermediate state local to the owning operation.
    """
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must not contain NaN or infinity")
        return
    if value is None or isinstance(value, (str, int, bool)):
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} must use string object keys")
            _validate_json(item, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_json(item, f"{path}[{index}]")
        return
    raise ValueError(f"{path} contains non-JSON value {type(value).__name__}")


class FrozenSettingsModel(BaseModel):
    """Represent the validated frozen settings model contract."""
    model_config = ConfigDict(frozen=True, extra="forbid", validate_default=True, allow_inf_nan=False)


class CoreSettings(FrozenSettingsModel):
    """Represent the validated core settings contract."""
    data_dir: Path = Field(default_factory=lambda: (Path.cwd() / "data").resolve())
    cache_dir: Path = Field(default_factory=lambda: (Path.cwd() / "cache").resolve())
    queue_capacity: int = Field(default=1024, ge=1)
    enqueue_timeout_seconds: float = Field(default=1.0, gt=0)
    handler_timeout_seconds: float = Field(default=30.0, gt=0)
    max_concurrent_events: int = Field(default=100, ge=1)


class LoggingSettings(FrozenSettingsModel):
    """Represent the validated logging settings contract."""
    level: str = "INFO"
    console: bool = True
    json_lines: bool = False
    file: Path | None = None
    rotation: str | int | None = None
    retention: str | int | None = None
    payload_mode: Literal["metadata", "full"] = "metadata"
    payload_exclude_runtimes: tuple[str, ...] = ()

    @field_validator("level")
    @classmethod
    def normalize_level(cls, value: str) -> str:
        """Normalize level.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.
        """
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("logging level must not be empty")
        return normalized

    @field_validator("payload_exclude_runtimes")
    @classmethod
    def validate_payload_exclude_runtimes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Validate payload exclude runtimes.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `tuple[str, ...]` result produced by the operation.
        """
        if any(not item.strip() or item != item.strip() for item in value):
            raise ValueError("payload exclusion runtime identifiers must be non-empty and trimmed")
        if len(set(value)) != len(value):
            raise ValueError("payload exclusion runtime identifiers must not contain duplicates")
        return value


class I18nSettings(FrozenSettingsModel):
    """Represent the validated i18n settings contract."""
    locale: str = "auto"

    @field_validator("locale")
    @classmethod
    def validate_locale(cls, value: str) -> str:
        """Validate locale.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.
        """
        normalized = value.strip().replace("_", "-")
        aliases = {"en": "en-US", "zh": "zh-CN", "zh-Hans": "zh-CN"}
        normalized = aliases.get(normalized, normalized)
        if normalized not in {"auto", "en-US", "zh-CN"}:
            raise ValueError("i18n locale must be auto, en-US, or zh-CN")
        return normalized


class PluginSettings(FrozenSettingsModel):
    """Represent the validated plugin settings contract."""
    enabled: tuple[str, ...] = ()
    local_modules: tuple[str, ...] = ()
    config: Mapping[str, Any] = Field(default_factory=dict)

    @field_validator("enabled", "local_modules")
    @classmethod
    def validate_unique_names(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Validate unique names.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `tuple[str, ...]` result produced by the operation.
        """
        if any(not item.strip() or item != item.strip() for item in value):
            raise ValueError("plugin names must be non-empty and must not contain surrounding whitespace")
        if len(set(value)) != len(value):
            raise ValueError("plugin names must not contain duplicates")
        return value

    @field_validator("config", mode="after")
    @classmethod
    def freeze_config(cls, value: Mapping[str, Any]) -> Mapping[str, Any]:
        """Freeze config.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `Mapping[str, Any]` result produced by the operation.
        """
        return cast(Mapping[str, Any], _freeze(value))

    @field_serializer("config")
    def serialize_config(self, value: Mapping[str, Any]) -> dict[str, Any]:
        """Implement the serialize config operation for the plugin settings.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `dict[str, Any]` result produced by the operation.
        """
        return cast(dict[str, Any], _thaw(value))


class CordisSettings(FrozenSettingsModel):
    """Configuration owned by the optional Cordis host boundary."""

    enabled: tuple[str, ...] = ()
    config: Mapping[str, Any] = Field(default_factory=dict)
    access: Mapping[str, Literal["limited"]] = Field(default_factory=dict)

    @field_validator("enabled")
    @classmethod
    def validate_unique_names(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Validate unique names.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `tuple[str, ...]` result produced by the operation.
        """
        if any(not item.strip() or item != item.strip() for item in value):
            raise ValueError("Cordis plugin names must be non-empty and must not contain surrounding whitespace")
        if len(set(value)) != len(value):
            raise ValueError("Cordis plugin names must not contain duplicates")
        return value

    @field_validator("config", mode="after")
    @classmethod
    def freeze_config(cls, value: Mapping[str, Any]) -> Mapping[str, Any]:
        """Freeze config.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `Mapping[str, Any]` result produced by the operation.
        """
        _validate_json(value, "cordis.config")
        return cast(Mapping[str, Any], _freeze(value))

    @field_serializer("config")
    def serialize_config(self, value: Mapping[str, Any]) -> dict[str, Any]:
        """Implement the serialize config operation for the cordis settings.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `dict[str, Any]` result produced by the operation.
        """
        return cast(dict[str, Any], _thaw(value))

    @field_validator("access", mode="after")
    @classmethod
    def validate_access(cls, value: Mapping[str, Literal["limited"]]) -> Mapping[str, Literal["limited"]]:
        """Validate access.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `Mapping[str, Literal['limited']]` result produced by the operation.
        """
        if any(not plugin_id.strip() or plugin_id != plugin_id.strip() for plugin_id in value):
            raise ValueError("Cordis access plugin IDs must be non-empty and trimmed")
        return dict(value)

    @model_validator(mode="after")
    def validate_access_targets(self) -> CordisSettings:
        """Validate access targets.

        Returns:
            The `CordisSettings` result produced by the operation.
        """
        unknown = set(self.access) - set(self.enabled)
        if unknown:
            raise ValueError(f"Cordis access targets must be enabled: {', '.join(sorted(unknown))}")
        return self


class AgentSettings(FrozenSettingsModel):
    """Legacy v1 Agent settings retained only to produce a migration error."""

    enabled: bool = False
    agent_harness: str = "native"

    @field_validator("agent_harness")
    @classmethod
    def validate_agent_harness(cls, value: str) -> str:
        """Validate agent harness.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.
        """
        if not value.strip() or value != value.strip():
            raise ValueError("agent_harness must be a non-empty trimmed string")
        return value


class RuntimeSettings(FrozenSettingsModel):
    """Represent the validated runtime settings contract."""
    kind: str
    enabled: bool = True
    command: tuple[str, ...] = ()
    working_directory: Path | None = None
    env: Mapping[str, str] = Field(default_factory=dict)
    secret_env: Mapping[str, str] = Field(default_factory=dict)
    options: Mapping[str, JsonValue] = Field(default_factory=dict)
    handshake_timeout_seconds: float = Field(default=10.0, gt=0)
    ready_timeout_seconds: float = Field(default=30.0, gt=0)
    heartbeat_interval_seconds: float = Field(default=10.0, gt=0)
    stale_after_seconds: float = Field(default=30.0, gt=0)
    max_inbound_events: int = Field(default=100, ge=1)
    max_failures: int = Field(default=5, ge=1)
    failure_window_seconds: float = Field(default=60.0, gt=0)

    @field_validator("command")
    @classmethod
    def validate_command(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Validate command.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `tuple[str, ...]` result produced by the operation.
        """
        if any(not argument for argument in value):
            raise ValueError("runtime command arguments must not be empty")
        return value

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str) -> str:
        """Validate kind.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.
        """
        if not value.strip() or value != value.strip():
            raise ValueError("runtime kind must be a non-empty trimmed string")
        return value

    @field_validator("env", mode="after")
    @classmethod
    def freeze_env(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        """Freeze env.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `Mapping[str, str]` result produced by the operation.
        """
        return MappingProxyType(dict(value))

    @field_validator("secret_env", mode="after")
    @classmethod
    def freeze_secret_env(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        """Freeze secret env.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `Mapping[str, str]` result produced by the operation.
        """
        if any(
            not environment_name
            or environment_name != environment_name.strip()
            or not secret_name
            or secret_name != secret_name.strip()
            for environment_name, secret_name in value.items()
        ):
            raise ValueError("runtime secret environment mappings must use non-empty trimmed names")
        return MappingProxyType(dict(value))

    @field_validator("options", mode="after")
    @classmethod
    def freeze_options(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        """Freeze options.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `Mapping[str, JsonValue]` result produced by the operation.
        """
        return cast(Mapping[str, JsonValue], _freeze(value))

    @field_serializer("env")
    def serialize_env(self, value: Mapping[str, str]) -> dict[str, str]:
        """Implement the serialize env operation for the runtime settings.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `dict[str, str]` result produced by the operation.
        """
        return dict(value)

    @field_serializer("secret_env")
    def serialize_secret_env(self, value: Mapping[str, str]) -> dict[str, str]:
        """Implement the serialize secret env operation for the runtime settings.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `dict[str, str]` result produced by the operation.
        """
        return dict(value)

    @field_serializer("options")
    def serialize_options(self, value: Mapping[str, JsonValue]) -> dict[str, Any]:
        """Implement the serialize options operation for the runtime settings.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `dict[str, Any]` result produced by the operation.
        """
        return cast(dict[str, Any], _thaw(value))

    @model_validator(mode="after")
    def validate_heartbeat(self) -> RuntimeSettings:
        """Validate heartbeat.

        Returns:
            The `RuntimeSettings` result produced by the operation.
        """
        if self.kind == "custom" and not self.command:
            raise ValueError("custom runtimes require an explicit command")
        if self.stale_after_seconds <= self.heartbeat_interval_seconds:
            raise ValueError("stale_after_seconds must exceed heartbeat_interval_seconds")
        return self


class RuntimeEventRoute(FrozenSettingsModel):
    """Forward matching core Events from configured source runtimes to one child."""

    sources: tuple[str, ...]
    target: str
    messages_only: bool = False

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Validate sources.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `tuple[str, ...]` result produced by the operation.
        """
        if not value:
            raise ValueError("runtime event route requires at least one source")
        if any(not source.strip() or source != source.strip() for source in value):
            raise ValueError("runtime event route sources must be non-empty trimmed strings")
        if len(set(value)) != len(value):
            raise ValueError("runtime event route sources must not contain duplicates")
        return value

    @field_validator("target")
    @classmethod
    def validate_target(cls, value: str) -> str:
        """Validate target.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.
        """
        if not value.strip() or value != value.strip():
            raise ValueError("runtime event route target must be a non-empty trimmed string")
        return value

    @model_validator(mode="after")
    def validate_no_self_routes(self) -> RuntimeEventRoute:
        """Validate no self routes.

        Returns:
            The `RuntimeEventRoute` result produced by the operation.
        """
        if self.target in self.sources:
            raise ValueError("runtime event route cannot target one of its sources")
        return self


class HttpSettings(FrozenSettingsModel):
    """Represent the validated http settings contract."""
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = Field(default=20216, ge=1, le=65535)

    @field_validator("host")
    @classmethod
    def normalize_host(cls, value: str) -> str:
        """Normalize host.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str` result produced by the operation.
        """
        return value.strip()

    @model_validator(mode="after")
    def require_loopback_binding(self) -> HttpSettings:
        """Return loopback binding, failing when it is unavailable.

        Returns:
            The requested `HttpSettings` value.
        """
        host = self.host.strip()
        is_loopback = host.lower() == "localhost"
        if not is_loopback:
            try:
                is_loopback = ip_address(host).is_loopback
            except ValueError:
                is_loopback = False
        if not is_loopback:
            raise ValueError("HTTP host must be a loopback address in v7")
        return self


class DaemonSettings(FrozenSettingsModel):
    """Policy for the daemon-owned Broker, bridges, Kernel, and update graph."""

    auto_restart: bool = False
    manage_broker: bool = True
    manage_bridges: bool = True
    restart_limit: int = Field(default=5, ge=1)
    restart_window_seconds: float = Field(default=60.0, gt=0)
    restart_backoff_initial_seconds: float = Field(default=0.5, gt=0)
    restart_backoff_max_seconds: float = Field(default=10.0, gt=0)
    startup_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    stop_timeout_seconds: float = Field(default=10.0, gt=0, le=300)
    drain_timeout_seconds: float = Field(default=30.0, gt=0, le=3_600)
    health_timeout_seconds: float = Field(default=30.0, gt=0, le=300)

    @model_validator(mode="after")
    def validate_backoff(self) -> DaemonSettings:
        """Validate backoff.

        Returns:
            The `DaemonSettings` result produced by the operation.
        """
        if self.restart_backoff_max_seconds < self.restart_backoff_initial_seconds:
            raise ValueError("restart_backoff_max_seconds must not be less than restart_backoff_initial_seconds")
        return self


class LyipLinkCapacitySettings(FrozenSettingsModel):
    """An all-or-nothing link capacity override.

    A partial override would make a capacity profile ambiguous and could give
    the two transport implementations different backpressure limits.
    """

    business_slots: int | None = None
    control_slots: int | None = None
    blob_arena_mib: int | None = None
    zmq_hwm: int | None = None

    @field_validator("business_slots")
    @classmethod
    def validate_business_slots(cls, value: int | None) -> int | None:
        """Validate business slots.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `int | None` result produced by the operation.
        """
        return _validate_power_of_two(value, minimum=256, maximum=65_536, name="business_slots")

    @field_validator("control_slots")
    @classmethod
    def validate_control_slots(cls, value: int | None) -> int | None:
        """Validate control slots.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `int | None` result produced by the operation.
        """
        return _validate_power_of_two(value, minimum=32, maximum=4_096, name="control_slots")

    @field_validator("blob_arena_mib")
    @classmethod
    def validate_blob_arena_mib(cls, value: int | None) -> int | None:
        """Validate blob arena mib.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `int | None` result produced by the operation.
        """
        return _validate_power_of_two(value, minimum=4, maximum=512, name="blob_arena_mib")

    @field_validator("zmq_hwm")
    @classmethod
    def validate_zmq_hwm(cls, value: int | None) -> int | None:
        """Validate zmq hwm.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `int | None` result produced by the operation.
        """
        return _validate_power_of_two(value, minimum=256, maximum=65_536, name="zmq_hwm")

    @model_validator(mode="after")
    def require_complete_override(self) -> LyipLinkCapacitySettings:
        """Return complete override, failing when it is unavailable.

        Returns:
            The requested `LyipLinkCapacitySettings` value.
        """
        values = (self.business_slots, self.control_slots, self.blob_arena_mib, self.zmq_hwm)
        if any(value is not None for value in values) and any(value is None for value in values):
            raise ValueError("LYIP capacity override must provide all four values")
        return self

    @property
    def is_configured(self) -> bool:
        """Return the lyip link capacity settings's is configured.

        Returns:
            Whether the requested condition is satisfied.
        """
        return self.business_slots is not None


class LyipCapacitySettings(FrozenSettingsModel):
    """The concrete limits used by one resolved LYIP link."""

    business_slots: int
    control_slots: int
    blob_arena_mib: int
    zmq_hwm: int


class LyipLinkResolution(FrozenSettingsModel):
    """Configuration-derived, but not availability-derived, link policy."""

    backend: Literal["auto", "shm", "zmq"]
    capacity_profile: Literal["latency", "balanced", "throughput"]
    capacity: LyipCapacitySettings


class LyipNativeDiagnostics(FrozenSettingsModel):
    """Derived native capability state suitable for CLI and WebUI diagnostics."""

    state: Literal["available", "unavailable"]
    wheel_version: str | None = None
    abi: int | None = Field(default=None, ge=1)
    platform: str
    fallback_reason: str | None = None

    @model_validator(mode="after")
    def validate_state(self) -> LyipNativeDiagnostics:
        """Validate state.

        Returns:
            The `LyipNativeDiagnostics` result produced by the operation.
        """
        if self.state == "available":
            if self.wheel_version is None or self.abi is None:
                raise ValueError("available native diagnostics require wheel_version and ABI")
            if self.fallback_reason is not None:
                raise ValueError("available native diagnostics cannot have a fallback reason")
        elif not self.fallback_reason:
            raise ValueError("unavailable native diagnostics require a fallback reason")
        return self


class LyipLinkSettings(FrozenSettingsModel):
    """Represent the validated lyip link settings contract."""
    backend: Literal["shm", "zmq"] | None = None
    capacity_profile: Literal["latency", "balanced", "throughput"] | None = None
    capacity: LyipLinkCapacitySettings = Field(default_factory=LyipLinkCapacitySettings)


class LyipSettings(FrozenSettingsModel):
    """Represent the validated lyip settings contract."""
    default_backend: Literal["auto", "shm", "zmq"] = "auto"
    capacity_profile: Literal["latency", "balanced", "throughput"] = "balanced"
    terminal_capacity: int = Field(default=16_384, ge=1_024, le=262_144)
    terminal_ttl_seconds: int = Field(default=3_600, ge=60, le=86_400)
    dev_summary_ttl_seconds: int = Field(default=900, ge=60, le=3_600)
    zmq_large_payload_fallback: bool = False
    links: Mapping[str, LyipLinkSettings] = Field(default_factory=dict)

    @field_validator("links", mode="after")
    @classmethod
    def freeze_links(cls, value: Mapping[str, LyipLinkSettings]) -> Mapping[str, LyipLinkSettings]:
        """Freeze links.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `Mapping[str, LyipLinkSettings]` result produced by the operation.
        """
        if any(not runtime_id.strip() or runtime_id != runtime_id.strip() for runtime_id in value):
            raise ValueError("LYIP link runtime identifiers must be non-empty and trimmed")
        return MappingProxyType(dict(value))

    @field_serializer("links")
    def serialize_links(self, value: Mapping[str, LyipLinkSettings]) -> dict[str, LyipLinkSettings]:
        """Implement the serialize links operation for the lyip settings.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `dict[str, LyipLinkSettings]` result produced by the operation.
        """
        return dict(value)

    def resolve_link(self, runtime_id: str) -> LyipLinkResolution:
        """Resolve inheritance once before a worker starts.

        Native availability is intentionally excluded here: it is observed at
        startup and converts ``auto`` to a transport without changing this
        immutable requested policy.

        Args:
            runtime_id: Stable runtime identifier.

        Returns:
            The requested `LyipLinkResolution` value.
        """

        link = self.links.get(runtime_id)
        backend = self.default_backend if link is None or link.backend is None else link.backend
        profile = self.capacity_profile if link is None or link.capacity_profile is None else link.capacity_profile
        override = None if link is None else link.capacity
        if override is None or not override.is_configured:
            capacity = _LYIP_CAPACITY_PROFILES[profile]
        else:
            assert override.business_slots is not None
            assert override.control_slots is not None
            assert override.blob_arena_mib is not None
            assert override.zmq_hwm is not None
            capacity = LyipCapacitySettings(
                business_slots=override.business_slots,
                control_slots=override.control_slots,
                blob_arena_mib=override.blob_arena_mib,
                zmq_hwm=override.zmq_hwm,
            )
        return LyipLinkResolution(backend=backend, capacity_profile=profile, capacity=capacity)


class WebUISettings(FrozenSettingsModel):
    """Represent the validated web u i settings contract."""
    mode: Literal["disabled", "on_demand", "always"] = "on_demand"
    port: int = Field(default=0, ge=0, le=65_535)
    idle_shutdown_seconds: int = Field(default=300, ge=30, le=3_600)
    ticket_ttl_seconds: int = Field(default=60, ge=15, le=300)
    session_idle_seconds: int = Field(default=1_800, ge=60, le=14_400)
    session_max_seconds: int = Field(default=28_800, ge=300, le=86_400)
    uploads_enabled: bool = False
    uploads_max_bytes: int = Field(default=67_108_864, ge=1, le=1_073_741_824)
    uploads_extensions: tuple[str, ...] = ()
    uploads_media_types: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_session_windows(self) -> WebUISettings:
        """Validate session windows.

        Returns:
            The `WebUISettings` result produced by the operation.
        """
        if self.session_max_seconds < self.session_idle_seconds:
            raise ValueError("session_max_seconds must not be less than session_idle_seconds")
        return self


class DevelopmentSettings(FrozenSettingsModel):
    """Opt-in local development controls; they never create an HTTP API."""

    enabled: bool = False
    allow_drills: bool = False
    watch_auto_restart: bool = False
    watch_debounce_seconds: float = Field(default=0.75, gt=0)
    webui_require_auth: bool = False


class BrokerActionResourceSettings(FrozenSettingsModel):
    """Represent the validated broker action resource settings contract."""
    kind: str
    resource: str | None = None
    resource_prefix: str | None = None

    @field_validator("kind", "resource", "resource_prefix")
    @classmethod
    def require_trimmed_identifier(cls, value: str | None) -> str | None:
        """Return trimmed identifier, failing when it is unavailable.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The requested `str | None` value.
        """
        if value is None:
            return None
        if not value.strip() or value != value.strip():
            raise ValueError("broker action resource identifiers must be non-empty and trimmed")
        return value

    @model_validator(mode="after")
    def validate_match_mode(self) -> BrokerActionResourceSettings:
        """Validate match mode.

        Returns:
            The `BrokerActionResourceSettings` result produced by the operation.
        """
        if (self.resource is None) == (self.resource_prefix is None):
            raise ValueError("broker action resources must define exactly one of resource or resource_prefix")
        return self

    @model_serializer
    def serialize(self) -> dict[str, str]:
        """Implement the serialize operation for the broker action resource settings.

        Returns:
            The `dict[str, str]` result produced by the operation.
        """
        result = {"kind": self.kind}
        if self.resource is not None:
            result["resource"] = self.resource
        if self.resource_prefix is not None:
            result["resource_prefix"] = self.resource_prefix
        return result


class BrokerToolSettings(FrozenSettingsModel):
    """Configuration-authoritative declaration for one bridge-owned Tool."""

    id: str
    description: str
    input_schema: Mapping[str, JsonValue]
    output_schema: Mapping[str, JsonValue] = Field(default_factory=lambda: {"type": "object"})
    capabilities: tuple[str, ...] = ()

    @field_validator("id", "description")
    @classmethod
    def require_text(cls, value: str) -> str:
        """Return text, failing when it is unavailable.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The requested `str` value.
        """
        if not value.strip() or value != value.strip():
            raise ValueError("broker Tool identifiers and descriptions must be non-empty and trimmed")
        return value

    @field_validator("input_schema", "output_schema", mode="after")
    @classmethod
    def validate_schema(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        """Validate schema.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `Mapping[str, JsonValue]` result produced by the operation.
        """
        _validate_json(value, "broker Tool schema")
        if value.get("type") != "object":
            raise ValueError("broker Tool schemas must describe JSON objects")
        try:
            Draft202012Validator.check_schema(dict(value))
        except SchemaError as error:
            raise ValueError("broker Tool schema is not valid Draft 2020-12") from error
        return cast(Mapping[str, JsonValue], _freeze(value))

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Validate capabilities.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `tuple[str, ...]` result produced by the operation.
        """
        if any(not capability.strip() or capability != capability.strip() for capability in value):
            raise ValueError("broker Tool capabilities must be non-empty and trimmed")
        if len(set(value)) != len(value):
            raise ValueError("broker Tool capabilities must not contain duplicates")
        return value

    @field_serializer("input_schema", "output_schema")
    def serialize_schema(self, value: Mapping[str, JsonValue]) -> dict[str, Any]:
        """Implement the serialize schema operation for the broker tool settings.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `dict[str, Any]` result produced by the operation.
        """
        return cast(dict[str, Any], _thaw(value))


class BrokerBridgeSettings(FrozenSettingsModel):
    """One configuration-authoritative bridge manifest and token reference."""

    kind: str
    token_secret: str
    access: Literal["full", "limited"] = "limited"
    subscriptions: tuple[str, ...] = ()
    action_resources: tuple[BrokerActionResourceSettings, ...] = ()
    tools: tuple[BrokerToolSettings, ...] = ()
    controls: tuple[str, ...] = ()
    options: Mapping[str, JsonValue] = Field(default_factory=dict)

    @field_validator("kind", "token_secret")
    @classmethod
    def require_trimmed_identifier(cls, value: str) -> str:
        """Return trimmed identifier, failing when it is unavailable.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The requested `str` value.
        """
        if not value.strip() or value != value.strip():
            raise ValueError("broker bridge identifiers must be non-empty and trimmed")
        return value

    @field_validator("subscriptions")
    @classmethod
    def validate_subscriptions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Validate subscriptions.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `tuple[str, ...]` result produced by the operation.
        """
        normalized = tuple(validate_topic_pattern(topic, subject="broker subscription") for topic in value)
        if len(normalized) != len(set(normalized)):
            raise ValueError("broker subscriptions must not contain duplicates")
        return normalized

    @field_validator("action_resources")
    @classmethod
    def reject_duplicate_action_resources(
        cls, value: tuple[BrokerActionResourceSettings, ...]
    ) -> tuple[BrokerActionResourceSettings, ...]:
        """Implement the reject duplicate action resources operation for the broker bridge settings.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `tuple[BrokerActionResourceSettings, ...]` result produced by the operation.
        """
        keys = {(resource.kind, resource.resource, resource.resource_prefix) for resource in value}
        if len(keys) != len(value):
            raise ValueError("broker action resources must not contain duplicates")
        return value

    @field_validator("tools")
    @classmethod
    def reject_duplicate_tools(cls, value: tuple[BrokerToolSettings, ...]) -> tuple[BrokerToolSettings, ...]:
        """Implement the reject duplicate tools operation for the broker bridge settings.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `tuple[BrokerToolSettings, ...]` result produced by the operation.
        """
        ids = tuple(tool.id for tool in value)
        if len(ids) != len(set(ids)):
            raise ValueError("broker Tool IDs must not contain duplicates")
        return value

    @field_validator("controls")
    @classmethod
    def reject_duplicate_controls(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Implement the reject duplicate controls operation for the broker bridge settings.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `tuple[str, ...]` result produced by the operation.
        """
        if any(not control.strip() or control != control.strip() for control in value):
            raise ValueError("broker controls must be non-empty and trimmed")
        if len(set(value)) != len(value):
            raise ValueError("broker controls must not contain duplicates")
        return value

    @field_validator("options", mode="after")
    @classmethod
    def freeze_options(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        """Freeze options.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `Mapping[str, JsonValue]` result produced by the operation.
        """
        return cast(Mapping[str, JsonValue], _freeze(value))

    @field_serializer("options")
    def serialize_options(self, value: Mapping[str, JsonValue]) -> dict[str, Any]:
        """Implement the serialize options operation for the broker bridge settings.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `dict[str, Any]` result produced by the operation.
        """
        return cast(dict[str, Any], _thaw(value))


def configured_kernel_bridge_settings(
    bridges: Mapping[str, BrokerBridgeSettings],
) -> tuple[str, BrokerBridgeSettings] | None:
    """Validate and return the reserved in-process kernel bridge, if configured.

    Args:
        bridges: The bridges value used by the operation.

    Returns:
        The `tuple[str, BrokerBridgeSettings] | None` result produced by the operation.
    """

    matches = tuple((bridge_id, bridge) for bridge_id, bridge in bridges.items() if bridge.kind == "kernel")
    if len(matches) > 1:
        raise ValueError("broker configuration must not contain multiple kernel bridges")
    if not matches:
        return None
    bridge_id, bridge = matches[0]
    if bridge.access != "full":
        raise ValueError("kernel bridge must use full access")
    if not bridge.subscriptions:
        raise ValueError("kernel bridge must declare at least one subscription")
    if bridge.action_resources:
        raise ValueError("kernel bridge must not declare action ownership")
    if bridge.tools:
        raise ValueError("kernel bridge must not declare Tools")
    if bridge.controls:
        raise ValueError("kernel bridge must not declare controls")
    return bridge_id, bridge


class BrokerSettings(FrozenSettingsModel):
    """Represent the validated broker settings contract."""
    endpoint: str = "tcp://127.0.0.1:20217"
    generation: int = Field(default=1, ge=1)
    active_capacity: int = Field(default=1_024, ge=1, le=262_144)
    terminal_capacity: int = Field(default=4_096, ge=1_024, le=262_144)
    terminal_content_bytes_capacity: int = Field(default=16 * 1024 * 1024, ge=1024 * 1024, le=1024 * 1024 * 1024)
    terminal_ttl_seconds: int = Field(default=3_600, ge=60, le=86_400)
    delivery_timeout_seconds: int = Field(default=30, ge=1, le=3_600)
    diagnostics_token_secret: str | None = None
    management_token_secret: str | None = None
    bridges: Mapping[str, BrokerBridgeSettings] = Field(default_factory=dict)

    @field_validator("diagnostics_token_secret")
    @classmethod
    def validate_diagnostics_token_secret(cls, value: str | None) -> str | None:
        """Validate diagnostics token secret.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str | None` result produced by the operation.
        """
        if value is None:
            return None
        if not value.strip() or value != value.strip():
            raise ValueError("broker diagnostics token secret must be a non-empty trimmed identifier")
        return value

    @field_validator("management_token_secret")
    @classmethod
    def validate_management_token_secret(cls, value: str | None) -> str | None:
        """Validate management token secret.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `str | None` result produced by the operation.
        """
        if value is None:
            return None
        if not value.strip() or value != value.strip():
            raise ValueError("broker management token secret must be a non-empty trimmed identifier")
        return value

    @field_validator("endpoint")
    @classmethod
    def require_loopback_tcp_endpoint(cls, value: str) -> str:
        """Return loopback tcp endpoint, failing when it is unavailable.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The requested `str` value.
        """
        normalized = value.strip()
        if not normalized.startswith("tcp://"):
            raise ValueError("broker endpoint must be a tcp loopback endpoint")
        host_port = normalized.removeprefix("tcp://")
        host, separator, raw_port = host_port.rpartition(":")
        if not separator or not raw_port.isdecimal() or not 1 <= int(raw_port) <= 65_534:
            raise ValueError("broker endpoint must contain a TCP port between 1 and 65534")
        try:
            loopback = ip_address(host.removeprefix("[").removesuffix("]")).is_loopback
        except ValueError:
            loopback = host.lower() == "localhost"
        if not loopback:
            raise ValueError("broker endpoint must use a loopback address")
        return normalized

    @field_validator("bridges", mode="after")
    @classmethod
    def freeze_bridges(cls, value: Mapping[str, BrokerBridgeSettings]) -> Mapping[str, BrokerBridgeSettings]:
        """Freeze bridges.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `Mapping[str, BrokerBridgeSettings]` result produced by the operation.
        """
        if any(not bridge_id.strip() or bridge_id != bridge_id.strip() for bridge_id in value):
            raise ValueError("broker bridge identifiers must be non-empty and trimmed")
        return MappingProxyType(dict(value))

    @field_serializer("bridges")
    def serialize_bridges(self, value: Mapping[str, BrokerBridgeSettings]) -> dict[str, BrokerBridgeSettings]:
        """Implement the serialize bridges operation for the broker settings.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `dict[str, BrokerBridgeSettings]` result produced by the operation.
        """
        return dict(value)

    @model_validator(mode="after")
    def validate_bridge_contracts(self) -> BrokerSettings:
        """Validate bridge contracts.

        Returns:
            The `BrokerSettings` result produced by the operation.
        """
        owners: dict[tuple[str, str, str | None, str | None], str] = {}
        tool_owners: dict[str, str] = {}
        control_owners: dict[str, str] = {}
        configured_kernel_bridge_settings(self.bridges)
        for bridge_id, bridge in self.bridges.items():
            for resource in bridge.action_resources:
                key = (bridge.access, resource.kind, resource.resource, resource.resource_prefix)
                existing = owners.get(key)
                if existing is not None:
                    name = resource.resource if resource.resource is not None else resource.resource_prefix
                    raise ValueError(
                        f"broker action resource {resource.kind!r}/{name!r} "
                        f"has duplicate {bridge.access!r} ownership in {existing!r} and {bridge_id!r}"
                    )
                owners[key] = bridge_id
            for tool in bridge.tools:
                existing = tool_owners.get(tool.id)
                if existing is not None:
                    raise ValueError(
                        f"broker Tool {tool.id!r} has duplicate ownership in {existing!r} and {bridge_id!r}"
                    )
                tool_owners[tool.id] = bridge_id
            for control in bridge.controls:
                existing = control_owners.get(control)
                if existing is not None:
                    raise ValueError(
                        f"broker control {control!r} has duplicate ownership in {existing!r} and {bridge_id!r}"
                    )
                control_owners[control] = bridge_id
        return self


class AppSettings(FrozenSettingsModel):
    """Represent the validated app settings contract."""
    config_version: int = 6
    core: CoreSettings = Field(default_factory=CoreSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    i18n: I18nSettings = Field(default_factory=I18nSettings)
    plugins: PluginSettings = Field(default_factory=PluginSettings)
    cordis: CordisSettings = Field(default_factory=CordisSettings)
    agent: AgentSettings | None = None
    broker: BrokerSettings = Field(default_factory=BrokerSettings)
    http: HttpSettings = Field(default_factory=HttpSettings)
    daemon: DaemonSettings = Field(default_factory=DaemonSettings)
    lyip: LyipSettings = Field(default_factory=LyipSettings)
    webui: WebUISettings = Field(default_factory=WebUISettings)
    development: DevelopmentSettings = Field(default_factory=DevelopmentSettings)

    @property
    def runtimes(self) -> Mapping[str, RuntimeSettings]:
        """Compatibility view for legacy daemon code; v6 never loads this from TOML.

        Returns:
            The `Mapping[str, RuntimeSettings]` result produced by the operation.
        """

        return MappingProxyType({})

    @property
    def runtime_event_routes(self) -> tuple[RuntimeEventRoute, ...]:
        """Compatibility view for legacy daemon code; v6 never loads this from TOML.

        Returns:
            The `tuple[RuntimeEventRoute, ...]` result produced by the operation.
        """

        return ()

    @field_validator("config_version")
    @classmethod
    def require_current_config_version(cls, value: int) -> int:
        """Return current config version, failing when it is unavailable.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The requested `int` value.
        """
        if value == 5:
            raise ValueError("migration_required: config_version 5 requires manual migration to 6")
        if value != 6:
            raise ValueError("config_version must be 6")
        return value

    @model_validator(mode="after")
    def validate_cross_section_policy(self) -> AppSettings:
        """Validate cross section policy.

        Returns:
            The `AppSettings` result produced by the operation.
        """
        if self.agent is not None:
            raise ValueError("migration_required: [agent] was removed; configure a Broker Agent bridge instead")
        if self.development.allow_drills and not self.development.enabled:
            raise ValueError("development.allow_drills requires development.enabled")
        if self.development.watch_auto_restart and not self.development.enabled:
            raise ValueError("development.watch_auto_restart requires development.enabled")
        if self.logging.payload_mode == "full":
            if not self.development.enabled:
                raise ValueError("logging.payload_mode=full requires development.enabled")
            if self.logging.file is None:
                raise ValueError("logging.payload_mode=full requires an instance-private logging.file")
            if self.logging.console:
                raise ValueError("logging.payload_mode=full requires logging.console=false")
            if self.logging.json_lines:
                raise ValueError("logging.payload_mode=full requires logging.json_lines=false")
            try:
                self.logging.file.resolve(strict=False).relative_to(self.core.data_dir.resolve(strict=False))
            except ValueError as error:
                raise ValueError("logging.payload_mode=full requires logging.file below core.data_dir") from error
        elif self.logging.payload_exclude_runtimes:
            raise ValueError("logging.payload_exclude_runtimes requires logging.payload_mode=full")

        return self


def _validate_power_of_two(value: int | None, *, minimum: int, maximum: int, name: str) -> int | None:
    """Validate power of two.

    Args:
        value: Value to validate, transform, or store.
        minimum: The minimum value used by the operation.
        maximum: The maximum value used by the operation.
        name: Stable name used to identify the value.

    Returns:
        The `int | None` result produced by the operation.

    Notes:
        Internal implementation detail for `_validate_power_of_two`. It performs the local state
        transition directly and is not a stable extension boundary.
    """
    if value is None:
        return None
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    if value & (value - 1):
        raise ValueError(f"{name} must be a power of two")
    return value


_LYIP_CAPACITY_PROFILES: Mapping[str, LyipCapacitySettings] = MappingProxyType(
    {
        "latency": LyipCapacitySettings(business_slots=1_024, control_slots=64, blob_arena_mib=8, zmq_hwm=1_024),
        "balanced": LyipCapacitySettings(business_slots=4_096, control_slots=256, blob_arena_mib=32, zmq_hwm=4_096),
        "throughput": LyipCapacitySettings(
            business_slots=16_384, control_slots=512, blob_arena_mib=128, zmq_hwm=16_384
        ),
    }
)


def lyip_native_diagnostics() -> LyipNativeDiagnostics:
    """Probe the optional wheel without turning native availability into config.

    The probe is intentionally conservative. A successfully importable wheel is
    not considered available until it declares the supported ABI and an actual
    shared-memory transport.

    Returns:
        The `LyipNativeDiagnostics` result produced by the operation.
    """

    platform_name = platform(aliased=True)
    try:
        native = import_module("liteyukibot_ipc_native")
    except ImportError:
        return LyipNativeDiagnostics(
            state="unavailable",
            platform=platform_name,
            fallback_reason="the Liteyuki IPC native wheel is not installed",
        )
    try:
        wheel_version = metadata.version("liteyukibot-v7-ipc-native")
    except metadata.PackageNotFoundError:
        wheel_version = None
    abi = getattr(native, "LYIP_NATIVE_ABI", None)
    if not isinstance(abi, int) or isinstance(abi, bool):
        return LyipNativeDiagnostics(
            state="unavailable",
            wheel_version=wheel_version,
            platform=platform_name,
            fallback_reason="the native wheel does not declare a valid LYIP ABI",
        )
    if abi != 1:
        return LyipNativeDiagnostics(
            state="unavailable",
            wheel_version=wheel_version,
            abi=abi,
            platform=platform_name,
            fallback_reason="the native wheel ABI is incompatible with LYIP v1",
        )
    if not getattr(native, "native_available", False):
        return LyipNativeDiagnostics(
            state="unavailable",
            wheel_version=wheel_version,
            abi=abi,
            platform=platform_name,
            fallback_reason="the native wheel has no usable shared-memory transport",
        )
    if wheel_version is None:
        return LyipNativeDiagnostics(
            state="unavailable",
            abi=abi,
            platform=platform_name,
            fallback_reason="the native wheel version cannot be determined",
        )
    return LyipNativeDiagnostics(state="available", wheel_version=wheel_version, abi=abi, platform=platform_name)
