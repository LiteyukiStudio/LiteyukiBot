from __future__ import annotations

from collections.abc import Mapping
from importlib import import_module, metadata
from ipaddress import ip_address
from pathlib import Path
from platform import platform
from types import MappingProxyType
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

type JsonValue = str | int | float | bool | None | tuple[JsonValue, ...] | Mapping[str, JsonValue]


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, frozenset)):
        return [_thaw(item) for item in value]
    return value


class FrozenSettingsModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", validate_default=True, allow_inf_nan=False)


class CoreSettings(FrozenSettingsModel):
    data_dir: Path = Field(default_factory=lambda: (Path.cwd() / "data").resolve())
    cache_dir: Path = Field(default_factory=lambda: (Path.cwd() / "cache").resolve())
    queue_capacity: int = Field(default=1024, ge=1)
    enqueue_timeout_seconds: float = Field(default=1.0, gt=0)
    handler_timeout_seconds: float = Field(default=30.0, gt=0)
    max_concurrent_events: int = Field(default=100, ge=1)


class LoggingSettings(FrozenSettingsModel):
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
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("logging level must not be empty")
        return normalized

    @field_validator("payload_exclude_runtimes")
    @classmethod
    def validate_payload_exclude_runtimes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() or item != item.strip() for item in value):
            raise ValueError("payload exclusion runtime identifiers must be non-empty and trimmed")
        if len(set(value)) != len(value):
            raise ValueError("payload exclusion runtime identifiers must not contain duplicates")
        return value


class I18nSettings(FrozenSettingsModel):
    locale: str = "auto"

    @field_validator("locale")
    @classmethod
    def validate_locale(cls, value: str) -> str:
        normalized = value.strip().replace("_", "-")
        aliases = {"en": "en-US", "zh": "zh-CN", "zh-Hans": "zh-CN"}
        normalized = aliases.get(normalized, normalized)
        if normalized not in {"auto", "en-US", "zh-CN"}:
            raise ValueError("i18n locale must be auto, en-US, or zh-CN")
        return normalized


class PluginSettings(FrozenSettingsModel):
    enabled: tuple[str, ...] = ()
    local_modules: tuple[str, ...] = ()
    config: Mapping[str, Any] = Field(default_factory=dict)

    @field_validator("enabled", "local_modules")
    @classmethod
    def validate_unique_names(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() or item != item.strip() for item in value):
            raise ValueError("plugin names must be non-empty and must not contain surrounding whitespace")
        if len(set(value)) != len(value):
            raise ValueError("plugin names must not contain duplicates")
        return value

    @field_validator("config", mode="after")
    @classmethod
    def freeze_config(cls, value: Mapping[str, Any]) -> Mapping[str, Any]:
        return cast(Mapping[str, Any], _freeze(value))

    @field_serializer("config")
    def serialize_config(self, value: Mapping[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], _thaw(value))


class AgentSettings(FrozenSettingsModel):
    """Select the single v1 agent harness that processes routed events."""

    enabled: bool = False
    agent_harness: str = "native"

    @field_validator("agent_harness")
    @classmethod
    def validate_agent_harness(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("agent_harness must be a non-empty trimmed string")
        return value


class RuntimeSettings(FrozenSettingsModel):
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
        if any(not argument for argument in value):
            raise ValueError("runtime command arguments must not be empty")
        return value

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("runtime kind must be a non-empty trimmed string")
        return value

    @field_validator("env", mode="after")
    @classmethod
    def freeze_env(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        return MappingProxyType(dict(value))

    @field_validator("secret_env", mode="after")
    @classmethod
    def freeze_secret_env(cls, value: Mapping[str, str]) -> Mapping[str, str]:
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
        return cast(Mapping[str, JsonValue], _freeze(value))

    @field_serializer("env")
    def serialize_env(self, value: Mapping[str, str]) -> dict[str, str]:
        return dict(value)

    @field_serializer("secret_env")
    def serialize_secret_env(self, value: Mapping[str, str]) -> dict[str, str]:
        return dict(value)

    @field_serializer("options")
    def serialize_options(self, value: Mapping[str, JsonValue]) -> dict[str, Any]:
        return cast(dict[str, Any], _thaw(value))

    @model_validator(mode="after")
    def validate_heartbeat(self) -> RuntimeSettings:
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
    policy: Literal["required", "best_effort"]
    completion: Literal["sync", "async"]

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, value: tuple[str, ...]) -> tuple[str, ...]:
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
        if not value.strip() or value != value.strip():
            raise ValueError("runtime event route target must be a non-empty trimmed string")
        return value

    @model_validator(mode="after")
    def validate_no_self_routes(self) -> RuntimeEventRoute:
        if self.target in self.sources:
            raise ValueError("runtime event route cannot target one of its sources")
        return self


class HttpSettings(FrozenSettingsModel):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = Field(default=20216, ge=1, le=65535)

    @field_validator("host")
    @classmethod
    def normalize_host(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def require_loopback_binding(self) -> HttpSettings:
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
    """Policy for the local daemon that owns one restartable kernel worker."""

    auto_restart: bool = False
    restart_limit: int = Field(default=5, ge=1)
    restart_window_seconds: float = Field(default=60.0, gt=0)
    restart_backoff_initial_seconds: float = Field(default=0.5, gt=0)
    restart_backoff_max_seconds: float = Field(default=10.0, gt=0)

    @model_validator(mode="after")
    def validate_backoff(self) -> DaemonSettings:
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
        return _validate_power_of_two(value, minimum=256, maximum=65_536, name="business_slots")

    @field_validator("control_slots")
    @classmethod
    def validate_control_slots(cls, value: int | None) -> int | None:
        return _validate_power_of_two(value, minimum=32, maximum=4_096, name="control_slots")

    @field_validator("blob_arena_mib")
    @classmethod
    def validate_blob_arena_mib(cls, value: int | None) -> int | None:
        return _validate_power_of_two(value, minimum=4, maximum=512, name="blob_arena_mib")

    @field_validator("zmq_hwm")
    @classmethod
    def validate_zmq_hwm(cls, value: int | None) -> int | None:
        return _validate_power_of_two(value, minimum=256, maximum=65_536, name="zmq_hwm")

    @model_validator(mode="after")
    def require_complete_override(self) -> LyipLinkCapacitySettings:
        values = (self.business_slots, self.control_slots, self.blob_arena_mib, self.zmq_hwm)
        if any(value is not None for value in values) and any(value is None for value in values):
            raise ValueError("LYIP capacity override must provide all four values")
        return self

    @property
    def is_configured(self) -> bool:
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
        if self.state == "available":
            if self.wheel_version is None or self.abi is None:
                raise ValueError("available native diagnostics require wheel_version and ABI")
            if self.fallback_reason is not None:
                raise ValueError("available native diagnostics cannot have a fallback reason")
        elif not self.fallback_reason:
            raise ValueError("unavailable native diagnostics require a fallback reason")
        return self


class LyipLinkSettings(FrozenSettingsModel):
    backend: Literal["shm", "zmq"] | None = None
    capacity_profile: Literal["latency", "balanced", "throughput"] | None = None
    capacity: LyipLinkCapacitySettings = Field(default_factory=LyipLinkCapacitySettings)


class LyipSettings(FrozenSettingsModel):
    default_backend: Literal["auto", "shm", "zmq"] = "auto"
    capacity_profile: Literal["latency", "balanced", "throughput"] = "balanced"
    zmq_large_payload_fallback: bool = False
    links: Mapping[str, LyipLinkSettings] = Field(default_factory=dict)

    @field_validator("links", mode="after")
    @classmethod
    def freeze_links(cls, value: Mapping[str, LyipLinkSettings]) -> Mapping[str, LyipLinkSettings]:
        if any(not runtime_id.strip() or runtime_id != runtime_id.strip() for runtime_id in value):
            raise ValueError("LYIP link runtime identifiers must be non-empty and trimmed")
        return MappingProxyType(dict(value))

    @field_serializer("links")
    def serialize_links(self, value: Mapping[str, LyipLinkSettings]) -> dict[str, LyipLinkSettings]:
        return dict(value)

    def resolve_link(self, runtime_id: str) -> LyipLinkResolution:
        """Resolve inheritance once before a worker starts.

        Native availability is intentionally excluded here: it is observed at
        startup and converts ``auto`` to a transport without changing this
        immutable requested policy.
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


class EventLedgerSettings(FrozenSettingsModel):
    active_capacity: int = Field(default=1_024, ge=1_024, le=262_144)
    terminal_capacity: int = Field(default=16_384, ge=1_024, le=262_144)
    terminal_ttl_seconds: int = Field(default=3_600, ge=60, le=86_400)


class WebUISettings(FrozenSettingsModel):
    mode: Literal["disabled", "on_demand", "always"] = "on_demand"
    port: int = Field(default=0, ge=0, le=65_535)
    idle_shutdown_seconds: int = Field(default=300, ge=30, le=3_600)
    ticket_ttl_seconds: int = Field(default=60, ge=15, le=300)
    session_idle_seconds: int = Field(default=1_800, ge=60, le=14_400)
    session_max_seconds: int = Field(default=28_800, ge=300, le=86_400)

    @model_validator(mode="after")
    def validate_session_windows(self) -> WebUISettings:
        if self.session_max_seconds < self.session_idle_seconds:
            raise ValueError("session_max_seconds must not be less than session_idle_seconds")
        return self


class DevelopmentSettings(FrozenSettingsModel):
    """Opt-in local development controls; they never create an HTTP API."""

    enabled: bool = False
    allow_drills: bool = False
    watch_auto_restart: bool = False
    watch_debounce_seconds: float = Field(default=0.75, gt=0)


class AppSettings(FrozenSettingsModel):
    config_version: int = 5
    core: CoreSettings = Field(default_factory=CoreSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    i18n: I18nSettings = Field(default_factory=I18nSettings)
    plugins: PluginSettings = Field(default_factory=PluginSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    runtimes: Mapping[str, RuntimeSettings] = Field(default_factory=dict)
    runtime_event_routes: tuple[RuntimeEventRoute, ...] = ()
    http: HttpSettings = Field(default_factory=HttpSettings)
    daemon: DaemonSettings = Field(default_factory=DaemonSettings)
    lyip: LyipSettings = Field(default_factory=LyipSettings)
    event_ledger: EventLedgerSettings = Field(default_factory=EventLedgerSettings)
    webui: WebUISettings = Field(default_factory=WebUISettings)
    development: DevelopmentSettings = Field(default_factory=DevelopmentSettings)

    @field_validator("config_version")
    @classmethod
    def require_current_config_version(cls, value: int) -> int:
        if value != 5:
            raise ValueError("config_version must be 5")
        return value

    @field_validator("runtimes", mode="after")
    @classmethod
    def freeze_runtimes(cls, value: Mapping[str, RuntimeSettings]) -> Mapping[str, RuntimeSettings]:
        if any(not runtime_id.strip() for runtime_id in value):
            raise ValueError("runtime identifiers must not be empty")
        return MappingProxyType(dict(value))

    @field_serializer("runtimes")
    def serialize_runtimes(self, value: Mapping[str, RuntimeSettings]) -> dict[str, RuntimeSettings]:
        return dict(value)

    @model_validator(mode="after")
    def validate_cross_section_policy(self) -> AppSettings:
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

        enabled = {runtime_id for runtime_id, runtime in self.runtimes.items() if runtime.enabled}
        routes: set[tuple[str, bool, str]] = set()
        for route in self.runtime_event_routes:
            if route.target not in self.runtimes:
                raise ValueError(f"runtime event route target {route.target!r} is not configured")
            if route.target not in enabled:
                raise ValueError(f"runtime event route target {route.target!r} is disabled")
            for source in route.sources:
                if source not in self.runtimes:
                    raise ValueError(f"runtime event route source {source!r} is not configured")
                if source not in enabled:
                    raise ValueError(f"runtime event route source {source!r} is disabled")
            for source in route.sources:
                key = (source, route.messages_only, route.target)
                if key in routes:
                    raise ValueError("runtime event routes must not contain duplicate source/filter/target rules")
                routes.add(key)
        return self


def _validate_power_of_two(value: int | None, *, minimum: int, maximum: int, name: str) -> int | None:
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
