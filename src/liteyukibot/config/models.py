from __future__ import annotations

from collections.abc import Mapping
from ipaddress import ip_address
from pathlib import Path
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

    @field_validator("level")
    @classmethod
    def normalize_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("logging level must not be empty")
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


class RuntimeSettings(FrozenSettingsModel):
    kind: Literal["nonebot", "v6", "custom"]
    enabled: bool = True
    command: tuple[str, ...] = ()
    working_directory: Path | None = None
    env: Mapping[str, str] = Field(default_factory=dict)
    options: Mapping[str, JsonValue] = Field(default_factory=dict)
    handshake_timeout_seconds: float = Field(default=10.0, gt=0)
    ready_timeout_seconds: float = Field(default=30.0, gt=0)
    heartbeat_interval_seconds: float = Field(default=10.0, gt=0)
    stale_after_seconds: float = Field(default=30.0, gt=0)
    max_failures: int = Field(default=5, ge=1)
    failure_window_seconds: float = Field(default=60.0, gt=0)

    @field_validator("command")
    @classmethod
    def validate_command(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not argument for argument in value):
            raise ValueError("runtime command arguments must not be empty")
        return value

    @field_validator("env", mode="after")
    @classmethod
    def freeze_env(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        return MappingProxyType(dict(value))

    @field_validator("options", mode="after")
    @classmethod
    def freeze_options(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        return cast(Mapping[str, JsonValue], _freeze(value))

    @field_serializer("env")
    def serialize_env(self, value: Mapping[str, str]) -> dict[str, str]:
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


class AppSettings(FrozenSettingsModel):
    core: CoreSettings = Field(default_factory=CoreSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    plugins: PluginSettings = Field(default_factory=PluginSettings)
    runtimes: Mapping[str, RuntimeSettings] = Field(default_factory=dict)
    http: HttpSettings = Field(default_factory=HttpSettings)

    @field_validator("runtimes", mode="after")
    @classmethod
    def freeze_runtimes(cls, value: Mapping[str, RuntimeSettings]) -> Mapping[str, RuntimeSettings]:
        if any(not runtime_id.strip() for runtime_id in value):
            raise ValueError("runtime identifiers must not be empty")
        return MappingProxyType(dict(value))

    @field_serializer("runtimes")
    def serialize_runtimes(self, value: Mapping[str, RuntimeSettings]) -> dict[str, RuntimeSettings]:
        return dict(value)
