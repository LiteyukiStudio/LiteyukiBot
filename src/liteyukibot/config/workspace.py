"""Project-local configuration initialization and upgrade guardrails."""

from __future__ import annotations

import os
import shutil
import stat
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..exceptions import LiteyukiError
from .errors import ConfigIssue, ConfigurationError
from .models import AppSettings, LoggingSettings
from .template import CONFIG_VERSION, render_config_template


class ConfigUpgradeRequired(LiteyukiError):
    """Raised after preserving an older configuration and writing upgrade material."""


class ConfigWorkspace:
    """Own the conventional project config path without changing loader semantics."""

    filename = "liteyuki.toml"

    def __init__(self, directory: str | os.PathLike[str] = ".") -> None:
        """Initialize the config workspace.

        Args:
            directory: The directory value used by the operation.

        Returns:
            None.
        """
        self.directory = Path(directory).resolve()
        self.path = self.directory / self.filename
        self.management_directory = self.directory / ".liteyuki"

    @staticmethod
    def is_docker() -> bool:
        """Implement the is docker operation for the config workspace.

        Returns:
            Whether the requested condition is satisfied.
        """
        return Path("/.dockerenv").is_file() or os.environ.get("container") == "docker"

    def prepare(self) -> Path:
        """Return the primary path after applying Docker/bootstrap upgrade policy.

        Returns:
            The `Path` result produced by the operation.
        """

        if self.path.is_symlink():
            raise ConfigurationError([ConfigIssue(self.path, "project configuration must not be a symlink")])
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
        """Generate upgrade material for an older root configuration.

        Args:
            refresh: The refresh value used by the operation.

        Returns:
            The `Path | None` result produced by the operation.
        """

        if self.path.is_symlink():
            raise ConfigurationError([ConfigIssue(self.path, "project configuration must not be a symlink")])
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
        logging_console: bool = True,
        logging_json_lines: bool = False,
        payload_mode: str = "metadata",
        locale: str = "auto",
        cordis_plugins: tuple[str, ...] = (),
        cordis_config: dict[str, Any] | None = None,
        permissions: dict[str, Any] | None = None,
        commands: dict[str, Any] | None = None,
        resources: dict[str, Any] | None = None,
        profile: dict[str, Any] | None = None,
        essentials: dict[str, Any] | None = None,
        onebot: dict[str, Any] | None = None,
    ) -> Path:
        """Initialize the config workspace operation.

        Args:
            data_dir: Filesystem path for the data.
            cache_dir: Filesystem path for the cache.
            logging_level: The logging level value used by the operation.
            logging_console: The logging console value used by the operation.
            logging_json_lines: The logging json lines value used by the operation.
            payload_mode: The payload mode value used by the operation.
            locale: The locale value used by the operation.
            cordis_plugins: The cordis plugins value used by the operation.
            cordis_config: The cordis config value used by the operation.
            permissions: Direct Permissions package settings.
            commands: Direct Commands package settings.
            resources: Direct Resources package settings.
            profile: Direct Profile package settings.
            essentials: Direct Essentials package settings.
            onebot: Adapter-owned OneBot settings.

        Returns:
            The `Path` result produced by the operation.
        """
        if self.path.exists():
            raise ConfigurationError([ConfigIssue(self.path, "project configuration already exists")])
        resource_directory = self.directory / "resources"
        if resource_directory.is_symlink():
            raise ConfigurationError([ConfigIssue(resource_directory, "resource directory must not be a symlink")])
        if resource_directory.exists() and not resource_directory.is_dir():
            raise ConfigurationError([ConfigIssue(resource_directory, "resource path is not a directory")])
        index = resource_directory / "index.json"
        if index.is_symlink():
            raise ConfigurationError([ConfigIssue(index, "resource index must not be a symlink")])
        if index.exists() and not index.is_file():
            raise ConfigurationError([ConfigIssue(index, "resource index path is not a file")])
        logging = LoggingSettings.model_validate(
            {
                "level": logging_level,
                "console": logging_console,
                "json_lines": logging_json_lines,
                "payload_mode": payload_mode,
            }
        )
        self.directory.mkdir(parents=True, exist_ok=True)
        rendered = render_config_template(
            data_dir=data_dir,
            cache_dir=cache_dir,
            logging_level=logging.level,
            logging_console=logging.console,
            logging_json_lines=logging.json_lines,
            payload_mode=logging.payload_mode,
            locale=locale,
            cordis_plugins=cordis_plugins,
            cordis_config=cordis_config,
            permissions=permissions,
            commands=commands,
            resources=resources,
            profile=profile,
            essentials=essentials,
            onebot=onebot,
        )
        AppSettings.model_validate(tomllib.loads(rendered))
        try:
            with self.path.open("x", encoding="utf-8") as stream:
                stream.write(rendered)
        except FileExistsError as error:
            raise ConfigurationError([ConfigIssue(self.path, "project configuration already exists")]) from error
        try:
            resource_directory.mkdir(exist_ok=True)
        except FileExistsError as error:
            raise ConfigurationError([ConfigIssue(resource_directory, "resource path is not a directory")]) from error
        if resource_directory.is_symlink() or not resource_directory.is_dir():
            raise ConfigurationError([ConfigIssue(resource_directory, "resource directory must be a real directory")])
        try:
            with index.open("x", encoding="utf-8") as stream:
                stream.write("[]\n")
        except FileExistsError:
            if index.is_symlink() or not index.is_file():
                raise ConfigurationError([ConfigIssue(index, "resource index must be a real file")]) from None
        return self.path

    def _read_root_document(self) -> dict[str, Any]:
        """Read root document.

        Returns:
            The `dict[str, Any]` result produced by the operation.

        Notes:
            Internal implementation detail for `ConfigWorkspace._read_root_document`. It delegates to
            `loads`, `read_text` while keeping intermediate state local to the owning operation.
        """
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

    def _upgrade(self, *, version: int | None, refresh: bool) -> None:
        """Implement the upgrade operation for the config workspace.

        Args:
            version: The version value used by the operation.
            refresh: The refresh value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `ConfigWorkspace._upgrade`. It delegates to
            `_write_upgrade_material` while keeping intermediate state local to the owning operation.
        """
        self._write_upgrade_material(version=version, refresh=refresh)

    def _write_upgrade_material(self, *, version: int | None, refresh: bool) -> None:
        """Write upgrade material.

        Args:
            version: The version value used by the operation.
            refresh: The refresh value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `ConfigWorkspace._write_upgrade_material`. It delegates to
            `strftime`, `now`, `exists`, `mkdir` while keeping intermediate state local to the owning
            operation.
        """
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        backup = self.management_directory / "config-backups" / timestamp / self.filename
        upgrade_directory = self.management_directory / "config-upgrades"
        upgrade = upgrade_directory / f"liteyuki.v{CONFIG_VERSION}.toml"
        instructions = upgrade_directory / "README.md"
        for candidate in (
            self.management_directory,
            self.management_directory / "config-backups",
            upgrade_directory,
            upgrade,
            instructions,
        ):
            if candidate.is_symlink():
                raise ConfigurationError(
                    [ConfigIssue(candidate, "configuration management path must not be a symlink")]
                )
        if upgrade.exists() and not refresh:
            found = "missing" if version is None else str(version)
            raise ConfigUpgradeRequired(
                f"migration_required: configuration version {found} requires manual upgrade to {CONFIG_VERSION}; "
                f"existing template: {upgrade}"
            )
        backup.parent.mkdir(parents=True, exist_ok=True)
        upgrade_directory.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.path, backup)
        backup.chmod(stat.S_IREAD)
        upgrade.write_text(render_config_template(), encoding="utf-8")
        instructions.write_text(
            "# Configuration upgrade required\n\n"
            "The kernel did not modify your existing configuration. Compare the generated "
            f"`liteyuki.v{CONFIG_VERSION}.toml` with the backup under `../config-backups/`, "
            "merge the required changes into `liteyuki.toml`, then start LiteyukiBot again.\n",
            encoding="utf-8",
        )
        found = "missing" if version is None else str(version)
        raise ConfigUpgradeRequired(
            f"migration_required: configuration version {found} requires manual upgrade to {CONFIG_VERSION}; "
            f"backup: {backup}; template: {upgrade}"
        )
