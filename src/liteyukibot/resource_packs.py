"""Read-only, layered resource packs for kernel and plugin presentation assets."""

from __future__ import annotations

import json
import struct
import zipfile
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from functools import partial
from hashlib import sha256
from importlib import resources
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Literal

import yaml
from liteyukibot_kernel import ServiceKey

RESOURCE_CATALOG_SERVICE = ServiceKey("liteyukibot.resource-packs", 1)
RESOURCE_MANIFEST_FILENAME = "manifest-v1.json"
RESOURCE_MANIFEST_SCHEMA = 1
_RESOURCE_MAX_FILES = 4096
_RESOURCE_MAX_FILE_BYTES = 8 * 1024 * 1024
_RESOURCE_MAX_TOTAL_BYTES = 64 * 1024 * 1024
_RESOURCE_MAX_COMPRESSED_BYTES = 64 * 1024 * 1024
_RESOURCE_MAX_COMPRESSION_RATIO = 100
_RESOURCE_CATALOG_MAX_PACKS = 256
_RESOURCE_CATALOG_MAX_BYTES = 256 * 1024 * 1024
_RESOURCE_MAX_INDEX_BYTES = 1024 * 1024
_RESOURCE_MAX_MANIFEST_BYTES = 1024 * 1024


class ResourcePackError(ValueError):
    """Raised when a resource pack or its workspace index is unsafe or invalid."""


def _validate_resource_budget(
    *, file_count: int, total_bytes: int, file_size: int, origin: str
) -> None:
    """Reject resource packs that exceed bounded file or decompression budgets."""

    if file_size < 0 or file_size > _RESOURCE_MAX_FILE_BYTES:
        raise ResourcePackError(
            f"resource pack file exceeds {_RESOURCE_MAX_FILE_BYTES} bytes: {origin}"
        )
    if file_count > _RESOURCE_MAX_FILES:
        raise ResourcePackError(f"resource pack contains more than {_RESOURCE_MAX_FILES} files: {origin}")
    if total_bytes > _RESOURCE_MAX_TOTAL_BYTES:
        raise ResourcePackError(
            f"resource pack exceeds {_RESOURCE_MAX_TOTAL_BYTES} uncompressed bytes: {origin}"
        )


def _read_limited_path(
    path: Path,
    origin: str,
    *,
    max_bytes: int = _RESOURCE_MAX_FILE_BYTES,
) -> bytes:
    """Read a filesystem resource while enforcing the per-file limit first."""

    try:
        with path.open("rb") as stream:
            content = stream.read(max_bytes + 1)
    except OSError as error:
        raise ResourcePackError(f"cannot read resource file: {origin}") from error
    if len(content) > max_bytes:
        raise ResourcePackError(f"resource pack file exceeds {max_bytes} bytes: {origin}")
    return content


def _read_limited_traversable(
    path: resources.abc.Traversable,
    origin: str,
    *,
    max_bytes: int = _RESOURCE_MAX_FILE_BYTES,
) -> bytes:
    """Read an importlib resource while enforcing the per-file limit first."""

    try:
        with path.open("rb") as stream:
            content = stream.read(max_bytes + 1)
    except OSError as error:
        raise ResourcePackError(f"cannot read resource file: {origin}") from error
    if len(content) > max_bytes:
        raise ResourcePackError(f"resource pack file exceeds {max_bytes} bytes: {origin}")
    return content


def _resource_read_limit(relative: str) -> int:
    """Return the tighter read budget for metadata files with dedicated limits."""

    return _RESOURCE_MAX_MANIFEST_BYTES if relative == RESOURCE_MANIFEST_FILENAME else _RESOURCE_MAX_FILE_BYTES


def _path_size(path: Path, origin: str) -> int:
    """Return a resource file size before reading its contents."""

    try:
        return path.stat().st_size
    except OSError as error:
        raise ResourcePackError(f"cannot stat resource file: {origin}") from error


def _validate_zip_directory_budget(path: Path) -> None:
    """Inspect bounded ZIP metadata before ``ZipFile`` materializes its directory list."""

    origin = str(path)
    archive_size = _path_size(path, origin)
    if archive_size > _RESOURCE_MAX_COMPRESSED_BYTES:
        raise ResourcePackError(f"resource ZIP exceeds {_RESOURCE_MAX_COMPRESSED_BYTES} compressed bytes: {path}")
    tail_size = min(archive_size, 22 + 65_535)
    try:
        with path.open("rb") as stream:
            stream.seek(archive_size - tail_size)
            tail = stream.read(tail_size)
    except OSError as error:
        raise ResourcePackError(f"cannot read resource ZIP metadata: {path}") from error
    eocd_offset = tail.rfind(b"PK\x05\x06")
    if eocd_offset < 0 or eocd_offset + 22 > len(tail):
        raise ResourcePackError(f"resource ZIP is invalid: {path}")
    try:
        eocd = struct.unpack_from("<4s4H2IH", tail, eocd_offset)
    except struct.error as error:
        raise ResourcePackError(f"resource ZIP is invalid: {path}") from error
    entry_count = eocd[4]
    if entry_count == 0xFFFF:
        absolute_eocd_offset = archive_size - tail_size + eocd_offset
        locator_offset = absolute_eocd_offset - 20
        if locator_offset < 0:
            raise ResourcePackError(f"resource ZIP is invalid: {path}")
        try:
            with path.open("rb") as stream:
                stream.seek(locator_offset)
                locator = stream.read(20)
                if len(locator) != 20:
                    raise ResourcePackError(f"resource ZIP is invalid: {path}")
                locator_values = struct.unpack("<4sIQ", locator)
                if locator_values[0] != b"PK\x06\x07":
                    raise ResourcePackError(f"resource ZIP is invalid: {path}")
                stream.seek(locator_values[2])
                zip64_eocd = stream.read(56)
        except (OSError, struct.error) as error:
            raise ResourcePackError(f"resource ZIP is invalid: {path}") from error
        if len(zip64_eocd) != 56 or zip64_eocd[:4] != b"PK\x06\x06":
            raise ResourcePackError(f"resource ZIP is invalid: {path}")
        entry_count = struct.unpack_from("<4sQ2H2I4Q", zip64_eocd)[7]
    if entry_count > _RESOURCE_MAX_FILES:
        raise ResourcePackError(f"resource pack contains more than {_RESOURCE_MAX_FILES} files: {path}")


def _token(value: object, subject: str) -> str:
    """Implement the token operation for the component.

    Args:
        value: Value to validate, transform, or store.
        subject: The subject value used by the operation.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_token`. It delegates to `strip` while keeping intermediate
        state local to the owning operation.
    """
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ResourcePackError(f"resource pack {subject} must be a non-empty trimmed string")
    return value


def _relative_path(value: str) -> str:
    """Implement the relative path operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_relative_path`. It delegates to `is_absolute`, `any`,
        `as_posix` while keeping intermediate state local to the owning operation.
    """
    path = PurePosixPath(value)
    if (
        "\x00" in value
        or "\\" in value
        or path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ResourcePackError(f"resource path is unsafe: {value!r}")
    return path.as_posix()


def _canonical_json(value: object) -> bytes:
    """Implement the canonical json operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `bytes` result produced by the operation.

    Notes:
        Internal implementation detail for `_canonical_json`. It delegates to `encode`, `dumps` while
        keeping intermediate state local to the owning operation.
    """
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _manifest_payload(files: Mapping[str, bytes]) -> dict[str, object]:
    """Implement the manifest payload operation for the component.

    Args:
        files: The files value used by the operation.

    Returns:
        The `dict[str, object]` result produced by the operation.

    Notes:
        Internal implementation detail for `_manifest_payload`. It delegates to `hexdigest`, `sha256`,
        `sorted`, `items` while keeping intermediate state local to the owning operation.
    """
    entries = [
        {"path": path, "sha256": sha256(content).hexdigest(), "size": len(content)}
        for path, content in sorted(files.items())
    ]
    payload: dict[str, object] = {"files": entries, "schema": RESOURCE_MANIFEST_SCHEMA}
    return {**payload, "root_sha256": sha256(_canonical_json(payload)).hexdigest()}


def write_resource_manifest(root: str | Path) -> Path:
    """Write the explicit integrity manifest for one directory resource pack.

    Args:
        root: The root value used by the operation.

    Returns:
        The `Path` result produced by the operation.
    """

    directory = Path(root).resolve()
    if not directory.is_dir():
        raise ResourcePackError(f"resource manifest root is not a directory: {directory}")
    files: dict[str, bytes] = {}
    file_count = 0
    total_bytes = 0
    for candidate in directory.rglob("*"):
        if candidate.is_symlink():
            raise ResourcePackError(f"resource pack contains an unsafe file: {candidate}")
        if candidate.is_dir():
            continue
        if not candidate.resolve().is_relative_to(directory):
            raise ResourcePackError(f"resource pack contains an unsafe file: {candidate}")
        relative = _relative_path(candidate.relative_to(directory).as_posix())
        if relative == RESOURCE_MANIFEST_FILENAME:
            continue
        origin = f"{directory}:{relative}"
        declared_size = _path_size(candidate, origin)
        file_count += 1
        total_bytes += declared_size
        _validate_resource_budget(
            file_count=file_count,
            total_bytes=total_bytes,
            file_size=declared_size,
            origin=str(directory),
        )
        content = _read_limited_path(candidate, origin)
        total_bytes = total_bytes - declared_size + len(content)
        _validate_resource_budget(
            file_count=file_count,
            total_bytes=total_bytes,
            file_size=len(content),
            origin=str(directory),
        )
        files[relative] = content
    manifest = directory / RESOURCE_MANIFEST_FILENAME
    rendered = _canonical_json(_manifest_payload(files)) + b"\n"
    if len(rendered) > _RESOURCE_MAX_MANIFEST_BYTES:
        raise ResourcePackError(f"resource manifest exceeds {_RESOURCE_MAX_MANIFEST_BYTES} bytes")
    manifest.write_bytes(rendered)
    return manifest


def verify_resource_manifest(root: str | Path) -> None:
    """Verify a directory resource pack without loading it into a catalog.

    Args:
        root: The root value used by the operation.

    Returns:
        None.
    """

    directory = Path(root).resolve()
    if not directory.is_dir():
        raise ResourcePackError(f"resource manifest root is not a directory: {directory}")
    files: dict[str, ResourceFile] = {}
    file_count = 0
    total_bytes = 0
    for candidate in directory.rglob("*"):
        if candidate.is_symlink():
            raise ResourcePackError(f"resource pack contains an unsafe file: {candidate}")
        if candidate.is_dir():
            continue
        if not candidate.resolve().is_relative_to(directory):
            raise ResourcePackError(f"resource pack contains an unsafe file: {candidate}")
        relative = _relative_path(candidate.relative_to(directory).as_posix())
        origin = f"{directory}:{relative}"
        declared_size = _path_size(candidate, origin)
        file_count += 1
        total_bytes += declared_size
        _validate_resource_budget(
            file_count=file_count,
            total_bytes=total_bytes,
            file_size=declared_size,
            origin=str(directory),
        )
        content = _read_limited_path(candidate, origin, max_bytes=_resource_read_limit(relative))
        total_bytes = total_bytes - declared_size + len(content)
        _validate_resource_budget(
            file_count=file_count,
            total_bytes=total_bytes,
            file_size=len(content),
            origin=str(directory),
        )
        files[relative] = ResourceFile("verification", relative, partial(bytes, content))
    _verify_manifest(files)


@dataclass(frozen=True, slots=True)
class ResourcePackDeclaration:
    """A package-owned resource root declared by an enabled native plugin."""

    package: str
    root: str = "resources"

    def __post_init__(self) -> None:
        """Validate and normalize the resource pack declaration after initialization.

        Returns:
            None.
        """
        _token(self.package, "package")
        _relative_path(self.root)


@dataclass(frozen=True, slots=True)
class ResourcePackMetadata:
    """Represent the resource pack metadata contract."""
    id: str
    name: str
    version: str
    description: str
    origin: str
    kind: Literal["language", "function", "mixed"] = "mixed"
    name_key: str | None = None
    description_key: str | None = None
    icon: str | None = None


@dataclass(frozen=True, slots=True)
class ResourceFile:
    """Represent the resource file contract."""
    pack_id: str
    path: str
    _read: Callable[[], bytes]

    def __post_init__(self) -> None:
        """Snapshot and validate file content so public readers cannot mutate a pack later."""

        _token(self.pack_id, "file pack id")
        if not isinstance(self.path, str) or _relative_path(self.path) != self.path:
            raise ResourcePackError(f"resource file path is unsafe: {self.path!r}")
        if not callable(self._read):
            raise TypeError("resource file reader must be callable")
        content = self._read()
        if not isinstance(content, bytes):
            raise TypeError("resource file reader must return bytes")
        _validate_resource_budget(
            file_count=1,
            total_bytes=len(content),
            file_size=len(content),
            origin=f"{self.pack_id}:{self.path}",
        )
        object.__setattr__(self, "_read", partial(bytes, content))

    def read_bytes(self) -> bytes:
        """Read bytes.

        Returns:
            The requested `bytes` value.
        """
        return self._read()

    def read_text(self, encoding: str = "utf-8") -> str:
        """Read text.

        Args:
            encoding: The encoding value used by the operation.

        Returns:
            The requested `str` value.
        """
        return self.read_bytes().decode(encoding)


@dataclass(frozen=True, slots=True)
class ResourcePack:
    """Represent the resource pack contract."""
    metadata: ResourcePackMetadata
    files: Mapping[str, ResourceFile]
    size_bytes: int = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Compute the retained byte size from actual file contents."""

        if not isinstance(self.metadata, ResourcePackMetadata):
            raise TypeError("resource pack metadata must be ResourcePackMetadata")
        if not isinstance(self.files, Mapping):
            raise TypeError("resource pack files must be a mapping")
        normalized_files: dict[str, ResourceFile] = {}
        total_bytes = 0
        for file_count, (path, resource) in enumerate(self.files.items(), start=1):
            if file_count > _RESOURCE_MAX_FILES:
                raise ResourcePackError(
                    f"resource pack contains more than {_RESOURCE_MAX_FILES} files: {self.metadata.origin}"
                )
            if not isinstance(path, str) or _relative_path(path) != path:
                raise ResourcePackError(f"resource file path is unsafe: {path!r}")
            if not isinstance(resource, ResourceFile):
                raise TypeError("resource pack files must contain ResourceFile values")
            if resource.path != path:
                raise ResourcePackError(f"resource file path does not match its mapping key: {path}")
            if resource.pack_id != self.metadata.id:
                raise ResourcePackError(f"resource file belongs to a different pack: {path}")
            content = resource.read_bytes()
            total_bytes += len(content)
            _validate_resource_budget(
                file_count=file_count,
                total_bytes=total_bytes,
                file_size=len(content),
                origin=f"{self.metadata.origin}:{resource.path}",
            )
            normalized_files[path] = resource
        object.__setattr__(self, "files", MappingProxyType(normalized_files))
        object.__setattr__(self, "size_bytes", total_bytes)


def _resource_pack_size(pack: ResourcePack) -> int:
    """Return the verified in-memory size of one resource pack."""

    size = pack.size_bytes
    return size


def _append_catalog_pack(packs: list[ResourcePack], pack: ResourcePack, total_bytes: int) -> int:
    """Append one pack while enforcing catalog-wide count and memory budgets."""

    if len(packs) >= _RESOURCE_CATALOG_MAX_PACKS:
        raise ResourcePackError(f"resource catalog contains more than {_RESOURCE_CATALOG_MAX_PACKS} packs")
    total_bytes += _resource_pack_size(pack)
    if total_bytes > _RESOURCE_CATALOG_MAX_BYTES:
        raise ResourcePackError(
            f"resource catalog exceeds {_RESOURCE_CATALOG_MAX_BYTES} in-memory bytes"
        )
    packs.append(pack)
    return total_bytes


class ResourceCatalog:
    """A deterministic overlay of resource-pack paths without extraction or copying."""

    def __init__(self, packs: Iterable[ResourcePack]) -> None:
        """Initialize the resource catalog.

        Args:
            packs: The packs value used by the operation.

        Returns:
            None.
        """
        ordered: list[ResourcePack] = []
        ids: set[str] = set()
        files: dict[str, ResourceFile] = {}
        total_bytes = 0
        for pack in packs:
            if len(ordered) >= _RESOURCE_CATALOG_MAX_PACKS:
                raise ResourcePackError(f"resource catalog contains more than {_RESOURCE_CATALOG_MAX_PACKS} packs")
            if pack.metadata.id in ids:
                raise ResourcePackError(f"duplicate resource pack id: {pack.metadata.id}")
            ids.add(pack.metadata.id)
            total_bytes += _resource_pack_size(pack)
            if total_bytes > _RESOURCE_CATALOG_MAX_BYTES:
                raise ResourcePackError(
                    f"resource catalog exceeds {_RESOURCE_CATALOG_MAX_BYTES} in-memory bytes"
                )
            ordered.append(pack)
            files.update(pack.files)
        self._packs = tuple(ordered)
        self._files = files

    @property
    def packs(self) -> tuple[ResourcePackMetadata, ...]:
        """Return the resource catalog's packs.

        Returns:
            The `tuple[ResourcePackMetadata, ...]` result produced by the operation.
        """
        return tuple(pack.metadata for pack in self._packs)

    def pack(self, pack_id: str) -> ResourcePackMetadata:
        """Implement the pack operation for the resource catalog.

        Args:
            pack_id: Stable identifier for the pack.

        Returns:
            The `ResourcePackMetadata` result produced by the operation.
        """
        for pack in self._packs:
            if pack.metadata.id == pack_id:
                return pack.metadata
        raise ResourcePackError(f"resource pack does not exist: {pack_id}")

    def pack_for_declaration(self, declaration: ResourcePackDeclaration) -> ResourcePack:
        """Return the installed package pack owned by one extension declaration.

        Args:
            declaration: The declaration value used by the operation.

        Returns:
            The `ResourcePack` result produced by the operation.
        """

        origin = f"package:{declaration.package}:{declaration.root}"
        matches = tuple(pack for pack in self._packs if pack.metadata.origin == origin)
        if len(matches) != 1:
            raise ResourcePackError(
                f"resource declaration does not resolve to exactly one installed pack: {origin}"
            )
        return matches[0]

    def pack_files(self, pack_id: str, prefix: str = "") -> tuple[ResourceFile, ...]:
        """Return files from one pack without applying the catalog overlay.

        Args:
            pack_id: Stable identifier for the pack.
            prefix: The prefix value used by the operation.

        Returns:
            The `tuple[ResourceFile, ...]` result produced by the operation.
        """

        for pack in self._packs:
            if pack.metadata.id == pack_id:
                normalized = "" if not prefix else _relative_path(prefix).rstrip("/") + "/"
                return tuple(
                    resource for path, resource in sorted(pack.files.items()) if path.startswith(normalized)
                )
        raise ResourcePackError(f"resource pack does not exist: {pack_id}")

    def icon(self, pack_id: str) -> ResourceFile | None:
        """Return a validated package icon for a future local presentation client.

        Args:
            pack_id: Stable identifier for the pack.

        Returns:
            The `ResourceFile | None` result produced by the operation.
        """

        for pack in self._packs:
            if pack.metadata.id == pack_id:
                return pack.files.get(pack.metadata.icon) if pack.metadata.icon else None
        raise ResourcePackError(f"resource pack does not exist: {pack_id}")

    def get(self, path: str) -> ResourceFile | None:
        """Return the resource catalog operation.

        Args:
            path: Filesystem or logical resource path.

        Returns:
            The `ResourceFile | None` result produced by the operation.
        """
        return self._files.get(_relative_path(path))

    def require(self, path: str) -> ResourceFile:
        """Return the resource catalog operation, failing when it is unavailable.

        Args:
            path: Filesystem or logical resource path.

        Returns:
            The requested `ResourceFile` value.
        """
        resource = self.get(path)
        if resource is None:
            raise ResourcePackError(f"resource does not exist: {path}")
        return resource

    def paths(self, prefix: str = "") -> tuple[str, ...]:
        """Implement the paths operation for the resource catalog.

        Args:
            prefix: The prefix value used by the operation.

        Returns:
            The `tuple[str, ...]` result produced by the operation.
        """
        normalized = "" if not prefix else _relative_path(prefix).rstrip("/") + "/"
        return tuple(path for path in sorted(self._files) if path.startswith(normalized))

    def files(self, prefix: str = "") -> tuple[ResourceFile, ...]:
        """Return layered files without collapsing same-path catalog entries.

        Args:
            prefix: The prefix value used by the operation.

        Returns:
            The `tuple[ResourceFile, ...]` result produced by the operation.
        """

        normalized = "" if not prefix else _relative_path(prefix).rstrip("/") + "/"
        return tuple(
            resource
            for pack in self._packs
            for path, resource in sorted(pack.files.items())
            if path.startswith(normalized)
        )

    @classmethod
    def load(
        cls,
        workspace: str | Path,
        *,
        plugin_packs: Iterable[ResourcePackDeclaration] = (),
    ) -> ResourceCatalog:
        """Load the resource catalog operation.

        Args:
            workspace: The workspace value used by the operation.
            plugin_packs: The plugin packs value used by the operation.

        Returns:
            The `ResourceCatalog` result produced by the operation.
        """
        builtin = Path(__file__).with_name("builtin_resources") / "vanilla_language"
        packs: list[ResourcePack] = []
        total_bytes = _append_catalog_pack(packs, _load_directory(builtin, "kernel"), 0)
        declarations: list[ResourcePackDeclaration] = []
        for declaration in plugin_packs:
            if len(declarations) >= _RESOURCE_CATALOG_MAX_PACKS - 1:
                raise ResourcePackError(f"resource catalog contains more than {_RESOURCE_CATALOG_MAX_PACKS} packs")
            declarations.append(declaration)
        declarations.sort(key=lambda item: (item.package, item.root))
        for declaration in declarations:
            root = resources.files(declaration.package).joinpath(declaration.root)
            total_bytes = _append_catalog_pack(
                packs,
                _load_traversable(root, f"package:{declaration.package}:{declaration.root}"),
                total_bytes,
            )
        for pack in _load_workspace_packs(Path(workspace)):
            total_bytes = _append_catalog_pack(packs, pack, total_bytes)
        return cls(packs)

    def reload(
        self,
        workspace: str | Path,
        *,
        plugin_packs: Iterable[ResourcePackDeclaration] = (),
    ) -> tuple[ResourcePackMetadata, ...]:
        """Atomically replace this catalog from the current resource roots.

        Args:
            workspace: Input accepted by this callable.
            plugin_packs: Input accepted by this callable.

        Returns:
            Result produced by this callable.
        """
        replacement = type(self).load(workspace, plugin_packs=plugin_packs)
        self._packs = replacement._packs
        self._files = replacement._files
        return self.packs


def _metadata(value: object, origin: str, fallback_id: str) -> ResourcePackMetadata:
    """Implement the metadata operation for the component.

    Args:
        value: Value to validate, transform, or store.
        origin: The origin value used by the operation.
        fallback_id: Stable identifier for the fallback.

    Returns:
        The `ResourcePackMetadata` result produced by the operation.

    Notes:
        Internal implementation detail for `_metadata`. It delegates to `_token`, `get`,
        `_optional_token`, `_relative_path` while keeping intermediate state local to the owning
        operation.
    """
    if not isinstance(value, dict):
        raise ResourcePackError(f"resource pack metadata must be an object: {origin}")
    pack_id = _token(value.get("id", fallback_id), "id")
    kind = value.get("kind", "mixed")
    if kind not in {"language", "function", "mixed"}:
        raise ResourcePackError(f"resource pack kind is unsupported: {origin}")
    name_key = _optional_token(value.get("name_key"), "name_key")
    description_key = _optional_token(value.get("description_key"), "description_key")
    icon = _optional_token(value.get("icon"), "icon")
    if icon is not None:
        icon = _relative_path(icon)
        if not icon.endswith(".png"):
            raise ResourcePackError("resource pack icon must be a PNG file")
    return ResourcePackMetadata(
        id=pack_id,
        name=_token(value.get("name", pack_id), "name"),
        version=_token(value.get("version", "0.0.0"), "version"),
        description=str(value.get("description", "")),
        origin=origin,
        kind=kind,
        name_key=name_key,
        description_key=description_key,
        icon=icon,
    )


def _optional_token(value: object, subject: str) -> str | None:
    """Implement the optional token operation for the component.

    Args:
        value: Value to validate, transform, or store.
        subject: The subject value used by the operation.

    Returns:
        The `str | None` result produced by the operation.

    Notes:
        Internal implementation detail for `_optional_token`. It delegates to `_token` while keeping
        intermediate state local to the owning operation.
    """
    if value is None:
        return None
    return _token(value, subject)


def _read_metadata(raw: str, origin: str, fallback_id: str) -> ResourcePackMetadata:
    """Read metadata.

    Args:
        raw: The raw value used by the operation.
        origin: The origin value used by the operation.
        fallback_id: Stable identifier for the fallback.

    Returns:
        The `ResourcePackMetadata` result produced by the operation.

    Notes:
        Internal implementation detail for `_read_metadata`. It delegates to `safe_load`, `_metadata`
        while keeping intermediate state local to the owning operation.
    """
    try:
        value: Any = yaml.safe_load(raw)
    except yaml.YAMLError as error:
        raise ResourcePackError(f"cannot parse resource metadata: {origin}") from error
    return _metadata(value, origin, fallback_id)


def _verify_manifest(files: Mapping[str, ResourceFile]) -> None:
    """Verify manifest.

    Args:
        files: The files value used by the operation.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_verify_manifest`. It delegates to `read_bytes`, `loads`,
        `get`, `_relative_path` while keeping intermediate state local to the owning operation.
    """
    try:
        raw = files[RESOURCE_MANIFEST_FILENAME].read_bytes()
    except KeyError as error:
        raise ResourcePackError("resource pack has no manifest-v1.json") from error
    if len(raw) > _RESOURCE_MAX_MANIFEST_BYTES:
        raise ResourcePackError(f"resource manifest exceeds {_RESOURCE_MAX_MANIFEST_BYTES} bytes")
    try:
        manifest = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ResourcePackError("resource manifest is not valid JSON") from error
    if not isinstance(manifest, dict) or set(manifest) != {"files", "root_sha256", "schema"}:
        raise ResourcePackError("resource manifest has an invalid shape")
    if manifest.get("schema") != RESOURCE_MANIFEST_SCHEMA:
        raise ResourcePackError("resource manifest schema is unsupported")
    entries = manifest.get("files")
    root_digest = manifest.get("root_sha256")
    if not isinstance(entries, list) or not isinstance(root_digest, str):
        raise ResourcePackError("resource manifest has invalid entries")
    if len(entries) > _RESOURCE_MAX_FILES:
        raise ResourcePackError(f"resource manifest contains more than {_RESOURCE_MAX_FILES} files")
    normalized: list[dict[str, object]] = []
    paths: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "size"}:
            raise ResourcePackError("resource manifest entry has an invalid shape")
        path, digest, size = entry.get("path"), entry.get("sha256"), entry.get("size")
        if not isinstance(path, str) or _relative_path(path) != path or path == RESOURCE_MANIFEST_FILENAME:
            raise ResourcePackError("resource manifest entry path is invalid")
        if (
            path in paths
            or not isinstance(digest, str)
            or len(digest) != 64
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
        ):
            raise ResourcePackError("resource manifest entry is invalid")
        paths.add(path)
        normalized.append({"path": path, "sha256": digest, "size": size})
    if normalized != sorted(normalized, key=lambda entry: str(entry["path"])):
        raise ResourcePackError("resource manifest entries are not sorted")
    payload: dict[str, object] = {"files": normalized, "schema": RESOURCE_MANIFEST_SCHEMA}
    if sha256(_canonical_json(payload)).hexdigest() != root_digest:
        raise ResourcePackError("resource manifest root digest does not match")
    actual = {path for path in files if path != RESOURCE_MANIFEST_FILENAME}
    if paths != actual:
        raise ResourcePackError("resource manifest file set does not match")
    for entry in normalized:
        path = str(entry["path"])
        content = files[path].read_bytes()
        if len(content) != entry["size"] or sha256(content).hexdigest() != entry["sha256"]:
            raise ResourcePackError(f"resource manifest digest does not match: {path}")


def _load_directory(root: Path, origin: str) -> ResourcePack:
    """Load directory.

    Args:
        root: The root value used by the operation.
        origin: The origin value used by the operation.

    Returns:
        The `ResourcePack` result produced by the operation.

    Notes:
        Internal implementation detail for `_load_directory`. It delegates to `resolve`, `is_file`,
        `_read_metadata`, `read_text` while keeping intermediate state local to the owning operation.
    """
    root = root.resolve()
    metadata_path = root / "metadata.yml"
    if metadata_path.is_symlink():
        raise ResourcePackError(f"resource pack contains an unsafe file: {metadata_path}")
    if not metadata_path.is_file():
        raise ResourcePackError(f"resource pack has no metadata.yml: {root}")
    metadata = _read_metadata(
        _read_limited_path(metadata_path, str(metadata_path)).decode("utf-8"),
        str(root),
        root.name,
    )
    files: dict[str, ResourceFile] = {}
    file_count = 0
    total_bytes = 0
    for candidate in root.rglob("*"):
        if candidate.is_symlink():
            raise ResourcePackError(f"resource pack contains an unsafe file: {candidate}")
        if candidate.is_dir():
            continue
        if not candidate.resolve().is_relative_to(root):
            raise ResourcePackError(f"resource pack contains an unsafe file: {candidate}")
        relative = _relative_path(candidate.relative_to(root).as_posix())
        origin = f"{root}:{relative}"
        declared_size = _path_size(candidate, origin)
        file_count += 1
        total_bytes += declared_size
        _validate_resource_budget(
            file_count=file_count,
            total_bytes=total_bytes,
            file_size=declared_size,
            origin=str(root),
        )
        content = _read_limited_path(candidate, origin, max_bytes=_resource_read_limit(relative))
        total_bytes = total_bytes - declared_size + len(content)
        _validate_resource_budget(
            file_count=file_count,
            total_bytes=total_bytes,
            file_size=len(content),
            origin=str(root),
        )
        files[relative] = ResourceFile(metadata.id, relative, partial(bytes, content))
    _verify_manifest(files)
    _validate_icon(metadata, files)
    return ResourcePack(metadata, files)


def _load_traversable(root: resources.abc.Traversable, origin: str) -> ResourcePack:
    """Load traversable.

    Args:
        root: The root value used by the operation.
        origin: The origin value used by the operation.

    Returns:
        The `ResourcePack` result produced by the operation.

    Notes:
        Internal implementation detail for `_load_traversable`. It delegates to `joinpath`, `is_file`,
        `_read_metadata`, `read_text` while keeping intermediate state local to the owning operation.
    """
    metadata_file = root.joinpath("metadata.yml")
    if not metadata_file.is_file():
        raise ResourcePackError(f"resource pack has no metadata.yml: {origin}")
    metadata = _read_metadata(
        _read_limited_traversable(metadata_file, f"{origin}:metadata.yml").decode("utf-8"),
        origin,
        origin.rsplit(":", 1)[-1],
    )
    files: dict[str, ResourceFile] = {}
    file_count = 0
    total_bytes = 0

    def visit(node: resources.abc.Traversable, prefix: str = "") -> None:
        """Implement the visit operation for the load traversable.

        Args:
            node: The node value used by the operation.
            prefix: The prefix value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_load_traversable.visit`. It delegates to `iterdir`,
            `_relative_path`, `is_dir`, `visit` while keeping intermediate state local to the owning
            operation.
        """
        nonlocal file_count, total_bytes
        for child in node.iterdir():
            relative = _relative_path(f"{prefix}/{child.name}" if prefix else child.name)
            if child.is_dir():
                visit(child, relative)
            elif child.is_file():
                content = _read_limited_traversable(
                    child,
                    f"{origin}:{relative}",
                    max_bytes=_resource_read_limit(relative),
                )
                file_count += 1
                total_bytes += len(content)
                _validate_resource_budget(
                    file_count=file_count,
                    total_bytes=total_bytes,
                    file_size=len(content),
                    origin=origin,
                )
                files[relative] = ResourceFile(metadata.id, relative, partial(bytes, content))

    visit(root)
    _verify_manifest(files)
    _validate_icon(metadata, files)
    return ResourcePack(metadata, files)


def _load_zip(path: Path) -> ResourcePack:
    """Load zip.

    Args:
        path: Filesystem or logical resource path.

    Returns:
        The `ResourcePack` result produced by the operation.

    Notes:
        Internal implementation detail for `_load_zip`. It delegates to `infolist`, `is_dir`, `items`,
        `_relative_path` while keeping intermediate state local to the owning operation.
    """
    _validate_zip_directory_budget(path)
    try:
        with zipfile.ZipFile(path) as archive:
            entries: dict[str, zipfile.ZipInfo] = {}
            normalized_names: set[str] = set()
            file_count = 0
            total_bytes = 0
            total_compressed_bytes = 0
            for entry in archive.infolist():
                if entry.is_dir():
                    continue
                name = entry.filename
                if name in entries:
                    raise ResourcePackError(f"resource ZIP contains duplicate file: {name}")
                normalized = _relative_path(name)
                if normalized in normalized_names:
                    raise ResourcePackError(f"resource ZIP contains duplicate path: {normalized}")
                file_count += 1
                total_bytes += entry.file_size
                total_compressed_bytes += entry.compress_size
                _validate_resource_budget(
                    file_count=file_count,
                    total_bytes=total_bytes,
                    file_size=entry.file_size,
                    origin=str(path),
                )
                if total_compressed_bytes > _RESOURCE_MAX_COMPRESSED_BYTES:
                    raise ResourcePackError(
                        f"resource ZIP exceeds {_RESOURCE_MAX_COMPRESSED_BYTES} compressed bytes: {path}"
                    )
                if normalized == RESOURCE_MANIFEST_FILENAME and entry.file_size > _RESOURCE_MAX_MANIFEST_BYTES:
                    raise ResourcePackError(f"resource manifest exceeds {_RESOURCE_MAX_MANIFEST_BYTES} bytes")
                if entry.file_size and (
                    entry.compress_size == 0
                    or entry.file_size / entry.compress_size > _RESOURCE_MAX_COMPRESSION_RATIO
                ):
                    raise ResourcePackError(f"resource ZIP compression ratio is unsafe: {name}")
                mode = entry.external_attr >> 16
                if mode and mode & 0o170000 == 0o120000:
                    raise ResourcePackError(f"resource ZIP contains a symbolic link: {path}")
                entries[name] = entry
                normalized_names.add(normalized)
            metadata_entry = entries.get("metadata.yml")
            if metadata_entry is None:
                raise ResourcePackError(f"resource ZIP has no metadata.yml: {path}")
            contents: dict[str, bytes] = {}
            actual_total_bytes = 0
            for name, entry in entries.items():
                content = archive.read(entry)
                if len(content) != entry.file_size:
                    raise ResourcePackError(f"resource ZIP entry size does not match: {name}")
                actual_total_bytes += len(content)
                _validate_resource_budget(
                    file_count=file_count,
                    total_bytes=actual_total_bytes,
                    file_size=len(content),
                    origin=str(path),
                )
                contents[name] = content
            metadata = _read_metadata(contents["metadata.yml"].decode("utf-8"), str(path), path.stem)
    except zipfile.BadZipFile as error:
        raise ResourcePackError(f"resource ZIP is invalid: {path}") from error
    files = {
        _relative_path(name): ResourceFile(metadata.id, _relative_path(name), partial(bytes, contents[name]))
        for name in entries
    }
    _verify_manifest(files)
    _validate_icon(metadata, files)
    return ResourcePack(metadata, files)


def _validate_icon(metadata: ResourcePackMetadata, files: Mapping[str, ResourceFile]) -> None:
    """Validate icon.

    Args:
        metadata: The metadata value used by the operation.
        files: The files value used by the operation.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_validate_icon`. It delegates to `read_bytes`, `from_bytes`
        while keeping intermediate state local to the owning operation.
    """
    if metadata.icon is None:
        return
    try:
        raw = files[metadata.icon].read_bytes()
    except KeyError as error:
        raise ResourcePackError(f"resource pack icon does not exist: {metadata.icon}") from error
    if len(raw) > 512 * 1024:
        raise ResourcePackError("resource pack icon exceeds 512 KiB")
    if len(raw) < 29 or raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
        raise ResourcePackError("resource pack icon is not a valid PNG")
    width = int.from_bytes(raw[16:20], "big")
    height = int.from_bytes(raw[20:24], "big")
    color_type = raw[25]
    if width != height or width == 0:
        raise ResourcePackError("resource pack icon must be a non-empty square image")
    if color_type not in {4, 6}:
        raise ResourcePackError("resource pack icon must include an alpha channel")


def _load_workspace_packs(workspace: Path) -> Iterator[ResourcePack]:
    """Load workspace packs.

    Args:
        workspace: The workspace value used by the operation.

    Returns:
        An iterator of loaded resource packs.

    Notes:
        Internal implementation detail for `_load_workspace_packs`. It delegates to `resolve`, `exists`,
        `loads`, `read_text` while keeping intermediate state local to the owning operation.
    """
    root = workspace.resolve() / "resources"
    if root.is_symlink():
        raise ResourcePackError(f"resource root is an unsafe file: {root}")
    index = root / "index.json"
    if index.is_symlink():
        raise ResourcePackError(f"resource index is an unsafe file: {index}")
    if not index.exists():
        return
    try:
        raw_index = _read_limited_path(index, f"resource index: {index}", max_bytes=_RESOURCE_MAX_INDEX_BYTES)
        requested = json.loads(raw_index.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ResourcePackError(f"cannot read resource index: {index}") from error
    if not isinstance(requested, list) or any(not isinstance(item, str) for item in requested):
        raise ResourcePackError("resource index must be a list of pack names")
    if len(requested) > _RESOURCE_CATALOG_MAX_PACKS:
        raise ResourcePackError(f"resource index contains more than {_RESOURCE_CATALOG_MAX_PACKS} pack names")
    if len(set(requested)) != len(requested):
        raise ResourcePackError("resource index must not contain duplicate pack names")
    for name in requested:
        relative = _relative_path(name)
        candidate = (root / relative).resolve()
        if not candidate.is_relative_to(root.resolve()):
            raise ResourcePackError(f"resource index escapes its workspace: {name}")
        if candidate.is_dir():
            yield _load_directory(candidate, "workspace")
        elif candidate.is_file() and candidate.suffix.lower() == ".zip":
            yield _load_zip(candidate)
        else:
            raise ResourcePackError(f"resource pack listed by index does not exist: {name}")


__all__ = [
    "ResourceCatalog",
    "RESOURCE_CATALOG_SERVICE",
    "ResourceFile",
    "ResourcePack",
    "ResourcePackDeclaration",
    "ResourcePackError",
    "ResourcePackMetadata",
    "RESOURCE_MANIFEST_FILENAME",
    "RESOURCE_MANIFEST_SCHEMA",
    "verify_resource_manifest",
    "write_resource_manifest",
]
