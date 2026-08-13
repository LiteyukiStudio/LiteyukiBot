"""Named instance paths and their configuration isolation contract."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import AppSettings, ConfigWorkspace

_INSTANCE_NAME = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62})\Z")
DEFAULT_INSTANCE = "default"


def normalize_instance_name(value: str) -> str:
    name = value.strip()
    if not _INSTANCE_NAME.fullmatch(name):
        raise ValueError("instance name must use 1-63 lower-case ASCII letters, digits, or hyphens")
    return name


@dataclass(frozen=True, slots=True)
class InstancePaths:
    """Workspace-local daemon state plus optional derived kernel directories."""

    workspace: Path
    name: str

    @classmethod
    def from_workspace(cls, workspace: ConfigWorkspace, name: str) -> InstancePaths:
        return cls(workspace.directory, normalize_instance_name(name))

    @property
    def root(self) -> Path:
        return self.workspace / ".liteyuki" / "instances" / self.name

    @property
    def overlay_path(self) -> Path:
        return self.workspace / ".liteyuki" / "instances" / f"{self.name}.toml"

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @property
    def log_file(self) -> Path:
        return self.root / "logs" / "kernel.log"

    @property
    def daemon_descriptor(self) -> Path:
        return self.root / "daemon.json"

    @property
    def daemon_lock(self) -> Path:
        return self.root / "daemon.lock"

    def overlay_paths(self) -> tuple[Path, ...]:
        return (self.overlay_path,) if self.name != DEFAULT_INSTANCE and self.overlay_path.exists() else ()

    def apply_storage(self, settings: AppSettings) -> AppSettings:
        """Keep the default instance stable; derive all named-instance storage."""

        if self.name == DEFAULT_INSTANCE:
            return settings
        document = settings.model_dump(mode="json")
        document["core"]["data_dir"] = str(self.data_dir)
        document["core"]["cache_dir"] = str(self.cache_dir)
        document["logging"]["file"] = str(self.log_file)
        return AppSettings.model_validate(document)


__all__ = ["DEFAULT_INSTANCE", "InstancePaths", "normalize_instance_name"]
