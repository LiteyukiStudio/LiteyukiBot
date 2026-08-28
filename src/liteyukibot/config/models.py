from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator


def _validate_json(value: Any, path: str) -> None:
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


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
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

    @field_validator("level")
    @classmethod
    def normalize_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("logging level must not be empty")
        return normalized


class I18nSettings(FrozenSettingsModel):
    locale: str = "auto"

    @field_validator("locale")
    @classmethod
    def validate_locale(cls, value: str) -> str:
        normalized = value.strip().replace("_", "-")
        normalized = {"en": "en-US", "zh": "zh-CN", "zh-Hans": "zh-CN"}.get(normalized, normalized)
        if normalized not in {"auto", "en-US", "zh-CN"}:
            raise ValueError("i18n locale must be auto, en-US, or zh-CN")
        return normalized


class CordisSettings(FrozenSettingsModel):
    enabled: tuple[str, ...] = ()
    config: Mapping[str, Any] = Field(default_factory=dict)

    @field_validator("enabled")
    @classmethod
    def validate_plugins(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item or item != item.strip() for item in value):
            raise ValueError("Cordis plugin names must be non-empty trimmed strings")
        if len(set(value)) != len(value):
            raise ValueError("Cordis plugin names must not contain duplicates")
        return value

    @field_validator("config", mode="after")
    @classmethod
    def freeze_config(cls, value: Mapping[str, Any]) -> Mapping[str, Any]:
        _validate_json(value, "cordis.config")
        return cast(Mapping[str, Any], _freeze(value))

    @field_serializer("config")
    def serialize_config(self, value: Mapping[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], _thaw(value))


class PermissionsSettings(FrozenSettingsModel):
    grants: tuple[Mapping[str, Any], ...] = ()
    roles: Mapping[str, tuple[str, ...]] = Field(default_factory=dict)

    @field_validator("grants", mode="after")
    @classmethod
    def freeze_grants(cls, value: tuple[Mapping[str, Any], ...]) -> tuple[Mapping[str, Any], ...]:
        _validate_json(value, "permissions.grants")
        return tuple(cast(Mapping[str, Any], _freeze(item)) for item in value)

    @field_validator("roles", mode="after")
    @classmethod
    def freeze_roles(cls, value: Mapping[str, tuple[str, ...]]) -> Mapping[str, tuple[str, ...]]:
        _validate_json(value, "permissions.roles")
        return MappingProxyType({str(key): tuple(items) for key, items in value.items()})

    @field_serializer("grants")
    def serialize_grants(self, value: tuple[Mapping[str, Any], ...]) -> list[dict[str, Any]]:
        return [cast(dict[str, Any], _thaw(item)) for item in value]

    @field_serializer("roles")
    def serialize_roles(self, value: Mapping[str, tuple[str, ...]]) -> dict[str, list[str]]:
        return {key: list(items) for key, items in value.items()}


class CommandsSettings(FrozenSettingsModel):
    prefixes: tuple[str, ...] = ("/",)

    @field_validator("prefixes")
    @classmethod
    def validate_prefixes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or any(not item or item != item.strip() for item in value):
            raise ValueError("commands prefixes must contain non-empty trimmed strings")
        if len(set(value)) != len(value):
            raise ValueError("commands prefixes must not contain duplicates")
        return value


class ResourcesSettings(FrozenSettingsModel):
    pass


class ProfileSettings(FrozenSettingsModel):
    database: Path | None = None


class EssentialsSettings(FrozenSettingsModel):
    language: Literal["zh-CN", "en"] = "zh-CN"


class OneBotV11Settings(FrozenSettingsModel):
    accounts: Mapping[str, Mapping[str, Any]] = Field(default_factory=dict)

    @field_validator("accounts", mode="after")
    @classmethod
    def freeze_accounts(cls, value: Mapping[str, Mapping[str, Any]]) -> Mapping[str, Mapping[str, Any]]:
        if any(not account_id or account_id != account_id.strip() for account_id in value):
            raise ValueError("onebot.v11 account identifiers must be non-empty and trimmed")
        _validate_json(value, "onebot.v11.accounts")
        return MappingProxyType(
            {str(account_id): cast(Mapping[str, Any], _freeze(account)) for account_id, account in value.items()}
        )

    @field_serializer("accounts")
    def serialize_accounts(self, value: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
        return {account_id: cast(dict[str, Any], _thaw(account)) for account_id, account in value.items()}


class OneBotSettings(FrozenSettingsModel):
    v11: OneBotV11Settings = Field(default_factory=OneBotV11Settings)


class AppSettings(FrozenSettingsModel):
    config_version: Literal[7] = 7
    core: CoreSettings = Field(default_factory=CoreSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    i18n: I18nSettings = Field(default_factory=I18nSettings)
    cordis: CordisSettings = Field(default_factory=CordisSettings)
    permissions: PermissionsSettings = Field(default_factory=PermissionsSettings)
    commands: CommandsSettings = Field(default_factory=CommandsSettings)
    resources: ResourcesSettings = Field(default_factory=ResourcesSettings)
    profile: ProfileSettings = Field(default_factory=ProfileSettings)
    essentials: EssentialsSettings = Field(default_factory=EssentialsSettings)
    onebot: OneBotSettings = Field(default_factory=OneBotSettings)

    @model_validator(mode="after")
    def validate_logging_policy(self) -> AppSettings:
        if self.logging.payload_mode == "full":
            if self.logging.file is None:
                raise ValueError("logging.payload_mode=full requires logging.file")
            if self.logging.console or self.logging.json_lines:
                raise ValueError("logging.payload_mode=full requires console and json_lines to be disabled")
            try:
                self.logging.file.resolve(strict=False).relative_to(self.core.data_dir.resolve(strict=False))
            except ValueError as error:
                raise ValueError("logging.payload_mode=full requires logging.file below core.data_dir") from error
        return self


__all__ = [
    "AppSettings",
    "CommandsSettings",
    "CordisSettings",
    "CoreSettings",
    "EssentialsSettings",
    "I18nSettings",
    "LoggingSettings",
    "OneBotSettings",
    "OneBotV11Settings",
    "PermissionsSettings",
    "ProfileSettings",
    "ResourcesSettings",
]
