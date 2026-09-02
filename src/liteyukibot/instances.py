"""Persistent nickname registry for Liteyuki application instances."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .exceptions import LiteyukiError

if os.name == "nt":
    import msvcrt
else:
    import fcntl

REGISTRY_ENVIRONMENT_VARIABLE = "LITEYUKI_INSTANCE_REGISTRY"
_FORMAT_VERSION = 1
_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class InstanceRegistryError(LiteyukiError):
    """Raised when the local instance nickname registry is invalid."""


@dataclass(frozen=True, slots=True)
class InstanceRecord:
    """One registered Liteyuki instance directory."""

    name: str
    path: Path

    def as_document(self, *, is_default: bool = False) -> dict[str, object]:
        """Render one user-facing registry record."""
        return {
            "name": self.name,
            "path": str(self.path),
            "default": is_default,
        }


def default_instance_registry_path() -> Path:
    """Return the user-level registry path, honoring the test-friendly override."""
    override = os.environ.get(REGISTRY_ENVIRONMENT_VARIABLE)
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".liteyuki" / "instances.json").resolve()


def _validate_name(name: str) -> str:
    if not _NAME_PATTERN.fullmatch(name):
        raise InstanceRegistryError(
            "instance nickname must start with a letter or number and contain only "
            "ASCII letters, numbers, '.', '_' or '-' (maximum 64 characters)"
        )
    return name


def _name_key(name: str) -> str:
    return _validate_name(name).casefold()


@contextmanager
def _registry_lock(path: Path) -> Iterator[None]:
    """Serialize registry mutations across processes with a persistent sidecar lock."""
    lock_path = path.with_name(f".{path.name}.lock")
    if lock_path.is_symlink() or (lock_path.exists() and not lock_path.is_file()):
        raise InstanceRegistryError(f"instance registry lock is not a regular file: {lock_path}")
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as stream:
            try:
                if os.name == "nt":
                    stream.seek(0, os.SEEK_END)
                    if stream.tell() == 0:
                        stream.write(b"\0")
                        stream.flush()
                    stream.seek(0)
                    msvcrt_module = cast(Any, msvcrt)
                    msvcrt_module.locking(stream.fileno(), msvcrt_module.LK_LOCK, 1)
                else:
                    fcntl_module = cast(Any, fcntl)
                    fcntl_module.flock(stream.fileno(), fcntl_module.LOCK_EX)
            except OSError as error:
                raise InstanceRegistryError(f"cannot lock instance registry: {lock_path}") from error
            try:
                yield
            finally:
                try:
                    if os.name == "nt":
                        stream.seek(0)
                        msvcrt_module = cast(Any, msvcrt)
                        msvcrt_module.locking(stream.fileno(), msvcrt_module.LK_UNLCK, 1)
                    else:
                        fcntl_module = cast(Any, fcntl)
                        fcntl_module.flock(stream.fileno(), fcntl_module.LOCK_UN)
                except OSError as error:
                    raise InstanceRegistryError(f"cannot unlock instance registry: {lock_path}") from error
    except OSError as error:
        raise InstanceRegistryError(f"cannot open instance registry lock: {lock_path}") from error


class InstanceRegistry:
    """Read and atomically update the user-level instance nickname registry."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = (
            default_instance_registry_path()
            if path is None
            else Path(path).expanduser().resolve()
        )

    def list(self) -> tuple[InstanceRecord, ...]:
        """Return registered instances in stable nickname order."""
        records, _ = self._read()
        return tuple(sorted(records.values(), key=lambda record: record.name.casefold()))

    def find(self, name: str) -> InstanceRecord | None:
        """Return a nickname record when it exists."""
        records, _ = self._read()
        key = _name_key(name)
        return next((record for record in records.values() if record.name.casefold() == key), None)

    def resolve(self, name: str) -> InstanceRecord:
        """Resolve one required nickname."""
        record = self.find(name)
        if record is None:
            raise InstanceRegistryError(f"unknown instance nickname: {name}")
        return record

    def default(self) -> InstanceRecord | None:
        """Return the configured default instance, if any."""
        records, default_name = self._read()
        if default_name is None:
            return None
        return records[default_name.casefold()]

    def register(
        self,
        name: str,
        directory: str | os.PathLike[str],
        *,
        replace: bool = False,
    ) -> InstanceRecord:
        """Register a nickname without creating or deleting its directory."""
        validated_name = _validate_name(name)
        path = Path(directory).expanduser().resolve()
        if path.exists() and not path.is_dir():
            raise InstanceRegistryError(f"instance path is not a directory: {path}")

        key = validated_name.casefold()
        with _registry_lock(self.path):
            records, default_name = self._read()
            existing = records.get(key)
            if existing is not None and not replace:
                raise InstanceRegistryError(f"instance nickname already exists: {existing.name}")
            if existing is not None and default_name is not None and default_name.casefold() == key:
                default_name = validated_name
            record = InstanceRecord(validated_name, path)
            records[key] = record
            self._write(records, default_name)
            return record

    def set_default(self, name: str) -> InstanceRecord:
        """Set one registered nickname as the implicit instance."""
        key = _name_key(name)
        with _registry_lock(self.path):
            records, _ = self._read()
            record = records.get(key)
            if record is None:
                raise InstanceRegistryError(f"unknown instance nickname: {name}")
            self._write(records, record.name)
            return record

    def remove(self, name: str) -> InstanceRecord:
        """Remove a registration while keeping the instance directory intact."""
        key = _name_key(name)
        with _registry_lock(self.path):
            records, default_name = self._read()
            record = records.get(key)
            if record is None:
                raise InstanceRegistryError(f"unknown instance nickname: {name}")
            del records[key]
            if default_name is not None and default_name.casefold() == key:
                default_name = None
            self._write(records, default_name)
            return record

    def _read(self) -> tuple[dict[str, InstanceRecord], str | None]:
        if not self.path.exists():
            return {}, None
        if self.path.is_symlink() or not self.path.is_file():
            raise InstanceRegistryError(f"instance registry is not a regular file: {self.path}")
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InstanceRegistryError(f"cannot read instance registry: {self.path}") from error
        if not isinstance(document, dict):
            raise InstanceRegistryError("instance registry root must be an object")
        version = document.get("version")
        if version != _FORMAT_VERSION:
            raise InstanceRegistryError(
                f"unsupported instance registry version: {version!r}; expected {_FORMAT_VERSION}"
            )
        raw_instances = document.get("instances")
        if not isinstance(raw_instances, dict):
            raise InstanceRegistryError("instance registry instances must be an object")

        records: dict[str, InstanceRecord] = {}
        for raw_name, raw_record in raw_instances.items():
            if not isinstance(raw_name, str) or not isinstance(raw_record, dict):
                raise InstanceRegistryError("instance registry contains an invalid record")
            name = _validate_name(raw_name)
            path = raw_record.get("path")
            if not isinstance(path, str) or not path:
                raise InstanceRegistryError(f"instance registry path is invalid for: {name}")
            directory = Path(path).expanduser().resolve()
            if directory.exists() and not directory.is_dir():
                raise InstanceRegistryError(f"instance path is not a directory: {directory}")
            key = name.casefold()
            if key in records:
                raise InstanceRegistryError(f"duplicate instance nickname: {name}")
            records[key] = InstanceRecord(name, directory)

        raw_default = document.get("default")
        if raw_default is not None:
            if not isinstance(raw_default, str) or raw_default.casefold() not in records:
                raise InstanceRegistryError("instance registry default does not name a registered instance")
            default_name: str | None = raw_default
        else:
            default_name = None
        return records, default_name

    def _write(self, records: dict[str, InstanceRecord], default_name: str | None) -> None:
        if self.path.is_symlink():
            raise InstanceRegistryError(f"instance registry must not be a symlink: {self.path}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        document: dict[str, Any] = {
            "version": _FORMAT_VERSION,
            "default": default_name,
            "instances": {
                record.name: {"path": str(record.path)}
                for record in sorted(records.values(), key=lambda item: item.name.casefold())
            },
        }
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump(document, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.write("\n")
            os.replace(temporary, self.path)
        except OSError as error:
            raise InstanceRegistryError(f"cannot write instance registry: {self.path}") from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


__all__ = [
    "InstanceRecord",
    "InstanceRegistry",
    "InstanceRegistryError",
    "REGISTRY_ENVIRONMENT_VARIABLE",
    "default_instance_registry_path",
]
