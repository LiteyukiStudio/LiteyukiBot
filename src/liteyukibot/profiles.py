"""Workspace-owned, immutable Python environment profiles."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .exceptions import LiteyukiError

_PROFILE_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")


class ProfileError(LiteyukiError):
    """Raised when the profile contract cannot be satisfied."""
    pass


@dataclass(frozen=True, slots=True)
class ProfileManifest:
    """Represent the validated profile manifest contract."""
    id: str
    created_at: str
    requirements: tuple[str, ...]
    python: str
    distributions: dict[str, str]
    direct_urls: dict[str, dict[str, str]]
    config_version: int = 6
    bundle_tag: str | None = None
    bundle_version: str | None = None
    bundle_manifest_sha256: str | None = None
    dependency_lock_sha256: str | None = None
    artifact_filenames: tuple[str, ...] = ()

    def document(self) -> dict[str, Any]:
        """Return the serialized document for the profile manifest operation.

        Returns:
            The `dict[str, Any]` result produced by the operation.
        """
        return {
            "schema": 3,
            "id": self.id,
            "created_at": self.created_at,
            "requirements": list(self.requirements),
            "python": self.python,
            "distributions": dict(sorted(self.distributions.items())),
            "direct_urls": {
                name: dict(sorted(provenance.items()))
                for name, provenance in sorted(self.direct_urls.items())
            },
            "config_version": self.config_version,
            "bundle": {
                "tag": self.bundle_tag,
                "version": self.bundle_version,
                "manifest_sha256": self.bundle_manifest_sha256,
                "dependency_lock_sha256": self.dependency_lock_sha256,
                "artifacts": list(self.artifact_filenames),
            }
            if self.bundle_tag is not None
            else None,
        }

    @property
    def digest(self) -> str:
        """Return the profile manifest's digest.

        Returns:
            The `str` result produced by the operation.
        """
        return hashlib.sha256(json.dumps(self.document(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def sanitize_direct_urls(value: dict[str, Any]) -> dict[str, dict[str, str]]:
        """Implement the sanitize direct urls operation for the profile manifest.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `dict[str, dict[str, str]]` result produced by the operation.
        """
        normalized: dict[str, dict[str, str]] = {}
        for name, raw in value.items():
            if not isinstance(name, str) or not name or not isinstance(raw, dict):
                continue
            url = raw.get("url")
            if not isinstance(url, str) or not url:
                continue
            parsed = urlsplit(url)
            hostname = parsed.hostname
            if hostname is not None:
                host = hostname if parsed.port is None else f"{hostname}:{parsed.port}"
                netloc = host
            else:
                netloc = parsed.netloc
            sanitized = urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
            provenance = {"url": sanitized}
            vcs = raw.get("vcs_info")
            commit_id = vcs.get("commit_id") if isinstance(vcs, dict) else raw.get("commit_id")
            if isinstance(commit_id, str) and commit_id:
                provenance["commit_id"] = commit_id
            normalized[name.lower()] = provenance
        return normalized


class ProfileStore:
    """Represent the profile store contract."""
    def __init__(self, workspace: str | Path) -> None:
        """Initialize the profile store.

        Args:
            workspace: The workspace value used by the operation.

        Returns:
            None.
        """
        self.workspace = Path(workspace).resolve()
        self.management = self.workspace / ".liteyuki"
        self.directory = self.management / "profiles"
        self.pointer = self.management / "current"
        self.lock = self.workspace / "liteyuki.lock"

    @staticmethod
    def python_path(profile: Path) -> Path:
        """Implement the python path operation for the profile store.

        Args:
            profile: Named runtime or benchmark profile.

        Returns:
            The `Path` result produced by the operation.
        """
        return profile / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    def profile_path(self, profile_id: str) -> Path:
        """Implement the profile path operation for the profile store.

        Args:
            profile_id: Stable identifier for the profile.

        Returns:
            The `Path` result produced by the operation.
        """
        if not _PROFILE_ID.fullmatch(profile_id):
            raise ProfileError("profile id must contain only lowercase letters, digits, and hyphens")
        return self.directory / profile_id

    def create(self, requirements: tuple[str, ...]) -> tuple[str, Path]:
        """Create the profile store operation.

        Args:
            requirements: The requirements value used by the operation.

        Returns:
            The `tuple[str, Path]` result produced by the operation.
        """
        if not requirements:
            raise ProfileError("profile stage requires at least one --require")
        profile_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-") + hashlib.sha256(os.urandom(16)).hexdigest()[:8]
        path = self.profile_path(profile_id)
        path.mkdir(parents=True)
        return profile_id, path

    def write_manifest(self, manifest: ProfileManifest) -> None:
        """Write manifest.

        Args:
            manifest: Validated manifest describing the component contract.

        Returns:
            None.
        """
        path = self.profile_path(manifest.id) / "manifest.json"
        self._write_json(path, manifest.document())

    def read_manifest(self, profile_id: str) -> ProfileManifest:
        """Read manifest.

        Args:
            profile_id: Stable identifier for the profile.

        Returns:
            The requested `ProfileManifest` value.
        """
        path = self.profile_path(profile_id) / "manifest.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("schema") not in (1, 2, 3) or value.get("id") != profile_id:
                raise ValueError("invalid profile manifest")
            return ProfileManifest(
                id=profile_id,
                created_at=str(value["created_at"]),
                requirements=tuple(str(item) for item in value["requirements"]),
                python=str(value["python"]),
                distributions={str(k): str(v) for k, v in dict(value["distributions"]).items()},
                direct_urls=ProfileManifest.sanitize_direct_urls(
                    dict(value.get("direct_urls", {})) if isinstance(value.get("direct_urls", {}), dict) else {}
                ),
                config_version=int(value.get("config_version", 5 if value.get("schema") == 2 else 6)),
                bundle_tag=(
                    str(dict(value["bundle"]).get("tag"))
                    if isinstance(value.get("bundle"), dict) and dict(value["bundle"]).get("tag") is not None
                    else None
                ),
                bundle_version=(
                    str(dict(value["bundle"]).get("version"))
                    if isinstance(value.get("bundle"), dict) and dict(value["bundle"]).get("version") is not None
                    else None
                ),
                bundle_manifest_sha256=(
                    str(dict(value["bundle"]).get("manifest_sha256"))
                    if isinstance(value.get("bundle"), dict)
                    and dict(value["bundle"]).get("manifest_sha256") is not None
                    else None
                ),
                dependency_lock_sha256=(
                    str(dict(value["bundle"]).get("dependency_lock_sha256"))
                    if isinstance(value.get("bundle"), dict)
                    and dict(value["bundle"]).get("dependency_lock_sha256") is not None
                    else None
                ),
                artifact_filenames=(
                    tuple(str(item) for item in dict(value["bundle"]).get("artifacts", []))
                    if isinstance(value.get("bundle"), dict)
                    and isinstance(dict(value["bundle"]).get("artifacts", []), list)
                    else ()
                ),
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ProfileError(f"profile {profile_id!r} is not verified") from error

    def active(self) -> str | None:
        """Implement the active operation for the profile store.

        Returns:
            The `str | None` result produced by the operation.
        """
        if not self.pointer.exists():
            return None
        try:
            profile_id = self.pointer.read_text(encoding="utf-8").strip()
            self.read_manifest(profile_id)
            return profile_id
        except OSError as error:
            raise ProfileError("cannot read active profile") from error

    def activate(self, profile_id: str) -> None:
        """Activate the profile store operation.

        Args:
            profile_id: Stable identifier for the profile.

        Returns:
            None.
        """
        self.read_manifest(profile_id)
        python = self.python_path(self.profile_path(profile_id))
        if not python.is_file():
            raise ProfileError(f"profile {profile_id!r} has no Python executable")
        previous = self.active()
        self.management.mkdir(parents=True, exist_ok=True)
        self._write_text(self.pointer, profile_id + "\n")
        self._write_json(
            self.lock,
            {"schema": 1, "active": profile_id, "previous": previous, "profiles": self.digests()},
        )

    def rollback(self) -> str:
        """Implement the rollback operation for the profile store.

        Returns:
            The `str` result produced by the operation.
        """
        previous = self.previous()
        current = self.active()
        self.read_manifest(previous)
        self._write_text(self.pointer, previous + "\n")
        self._write_json(self.lock, {"schema": 1, "active": previous, "previous": current, "profiles": self.digests()})
        return previous

    def previous(self) -> str:
        """Implement the previous operation for the profile store.

        Returns:
            The `str` result produced by the operation.
        """
        try:
            previous = json.loads(self.lock.read_text(encoding="utf-8")).get("previous")
        except (OSError, json.JSONDecodeError) as error:
            raise ProfileError("no rollback profile is available") from error
        if not isinstance(previous, str):
            raise ProfileError("no rollback profile is available")
        return previous

    def list(self) -> tuple[ProfileManifest, ...]:
        """List the profile store operation.

        Returns:
            The `tuple[ProfileManifest, ...]` result produced by the operation.
        """
        if not self.directory.exists():
            return ()
        manifests: list[ProfileManifest] = []
        for path in sorted(self.directory.iterdir()):
            if not path.is_dir():
                continue
            try:
                manifests.append(self.read_manifest(path.name))
            except ProfileError:
                continue
        return tuple(manifests)

    def digests(self) -> dict[str, str]:
        """Implement the digests operation for the profile store.

        Returns:
            The `dict[str, str]` result produced by the operation.
        """
        return {manifest.id: manifest.digest for manifest in self.list()}

    @staticmethod
    def _write_text(path: Path, text: str) -> None:
        """Write text.

        Args:
            path: Filesystem or logical resource path.
            text: The text value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `ProfileStore._write_text`. It delegates to `mkdir`,
            `with_suffix`, `write_text`, `replace` while keeping intermediate state local to the owning
            operation.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)

    @classmethod
    def _write_json(cls, path: Path, value: dict[str, Any]) -> None:
        """Write json.

        Args:
            path: Filesystem or logical resource path.
            value: Value to validate, transform, or store.

        Returns:
            None.

        Notes:
            Internal implementation detail for `ProfileStore._write_json`. It delegates to `_write_text`,
            `dumps` while keeping intermediate state local to the owning operation.
        """
        cls._write_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def installed_distributions() -> dict[str, str]:
    """Implement the installed distributions operation for the component.

    Returns:
        The `dict[str, str]` result produced by the operation.
    """
    import importlib.metadata

    return {
        item.metadata["Name"].lower(): item.version
        for item in importlib.metadata.distributions()
        if item.metadata.get("Name")
    }


def current_python() -> str:
    """Implement the current python operation for the component.

    Returns:
        The `str` result produced by the operation.
    """
    return str(Path(sys.executable).resolve())


__all__ = ["ProfileError", "ProfileManifest", "ProfileStore", "current_python", "installed_distributions"]
