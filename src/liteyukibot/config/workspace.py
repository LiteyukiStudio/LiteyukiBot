"""Project-local configuration initialization and upgrade guardrails."""

from __future__ import annotations

import os
import shutil
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..exceptions import LiteyukiError
from .errors import ConfigIssue, ConfigurationError
from .loader import load_settings
from .models import AppSettings, LoggingSettings
from .template import CONFIG_VERSION, render_config_template


class ConfigUpgradeRequired(LiteyukiError):
    """Raised after preserving an older configuration and writing upgrade material."""


class ConfigWorkspace:
    """Own the conventional project config path without changing loader semantics."""

    filename = "liteyuki.toml"

    def __init__(self, directory: str | os.PathLike[str] = ".") -> None:
        self.directory = Path(directory).resolve()
        self.path = self.directory / self.filename
        self.management_directory = self.directory / ".liteyuki"

    @staticmethod
    def is_docker() -> bool:
        return Path("/.dockerenv").is_file() or os.environ.get("container") == "docker"

    def prepare(self) -> Path:
        """Return the primary path after applying Docker/bootstrap upgrade policy."""

        if not self.path.exists():
            if self.is_docker():
                self.initialize()
                return self.path
            raise ConfigurationError(
                [ConfigIssue(self.path, "project configuration is missing; run `liteyuki init` first")]
            )
        if not self.path.is_file():
            raise ConfigurationError([ConfigIssue(self.path, "project configuration path is not a file")])

        document = self._read_root_document()
        version = document.get("config_version")
        if not isinstance(version, int) or isinstance(version, bool):
            self._upgrade(version=None, refresh=False)
        assert isinstance(version, int)
        if version > CONFIG_VERSION:
            raise ConfigurationError(
                [ConfigIssue(self.path, f"config_version {version} is newer than this kernel ({CONFIG_VERSION})")]
            )
        if version < CONFIG_VERSION:
            self._upgrade(version=version, refresh=False)
        return self.path

    def upgrade(self, *, refresh: bool = False) -> Path | None:
        """Generate upgrade material for an older root configuration."""

        if not self.path.exists():
            raise ConfigurationError(
                [ConfigIssue(self.path, "project configuration is missing; run liteyuki init first")]
            )
        if not self.path.is_file():
            raise ConfigurationError([ConfigIssue(self.path, "project configuration path is not a file")])
        document = self._read_root_document()
        version = document.get("config_version")
        if not isinstance(version, int) or isinstance(version, bool):
            self._upgrade(version=None, refresh=refresh)
        assert isinstance(version, int)
        if version > CONFIG_VERSION:
            raise ConfigurationError(
                [ConfigIssue(self.path, f"config_version {version} is newer than this kernel ({CONFIG_VERSION})")]
            )
        if version < CONFIG_VERSION:
            self._upgrade(version=version, refresh=refresh)
        return None

    def initialize(
        self,
        *,
        data_dir: str = "data",
        cache_dir: str = "cache",
        logging_level: str = "INFO",
        payload_mode: str = "metadata",
        payload_exclude_runtimes: tuple[str, ...] = (),
        plugins: tuple[str, ...] = (),
        plugin_config: dict[str, dict[str, Any]] | None = None,
        runtimes: dict[str, dict[str, Any]] | None = None,
        runtime_event_routes: tuple[dict[str, Any], ...] = (),
    ) -> Path:
        if self.path.exists():
            raise ConfigurationError([ConfigIssue(self.path, "project configuration already exists")])
        logging = LoggingSettings.model_validate(
            {
                "level": logging_level,
                "payload_mode": payload_mode,
                "payload_exclude_runtimes": payload_exclude_runtimes,
            }
        )
        self.directory.mkdir(parents=True, exist_ok=True)
        rendered = render_config_template(
            data_dir=data_dir,
            cache_dir=cache_dir,
            logging_level=logging.level,
            payload_mode=logging.payload_mode,
            payload_exclude_runtimes=logging.payload_exclude_runtimes,
            plugins=plugins,
            plugin_config=plugin_config,
            runtimes=runtimes,
            runtime_event_routes=runtime_event_routes,
        )
        AppSettings.model_validate(tomllib.loads(rendered))
        self.path.write_text(rendered, encoding="utf-8")
        return self.path

    def _read_root_document(self) -> dict[str, Any]:
        try:
            value = tomllib.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
            raise ConfigurationError(
                [ConfigIssue(self.path, f"cannot parse project configuration: {error}")]
            ) from error
        if not isinstance(value, dict):
            raise ConfigurationError(
                [ConfigIssue(self.path, "configuration document must contain an object at its root")]
            )
        return value

    def _validate_current_file(self) -> None:
        load_settings(self.path, environ={}, cli_overrides={"config_version": CONFIG_VERSION})

    def _upgrade(self, *, version: int | None, refresh: bool) -> None:
        self._validate_current_file()
        self._write_upgrade_material(version=version, refresh=refresh)

    def _write_upgrade_material(self, *, version: int | None, refresh: bool) -> None:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        backup = self.management_directory / "config-backups" / timestamp / self.filename
        upgrade_directory = self.management_directory / "config-upgrades"
        upgrade = upgrade_directory / f"liteyuki.v{CONFIG_VERSION}.toml"
        if upgrade.exists() and not refresh:
            found = "missing" if version is None else str(version)
            raise ConfigUpgradeRequired(
                f"configuration version {found} requires manual upgrade to {CONFIG_VERSION}; "
                f"existing template: {upgrade}"
            )
        backup.parent.mkdir(parents=True, exist_ok=True)
        upgrade_directory.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.path, backup)
        upgrade.write_text(render_config_template(), encoding="utf-8")
        (upgrade_directory / "README.md").write_text(
            "# Configuration upgrade required\n\n"
            "The kernel did not modify your existing configuration. Compare the generated "
            f"`liteyuki.v{CONFIG_VERSION}.toml` with the backup under `../config-backups/`, "
            "merge the required changes into `liteyuki.toml`, then start LiteyukiBot again.\n",
            encoding="utf-8",
        )
        found = "missing" if version is None else str(version)
        raise ConfigUpgradeRequired(
            f"configuration version {found} requires manual upgrade to {CONFIG_VERSION}; "
            f"backup: {backup}; template: {upgrade}"
        )
