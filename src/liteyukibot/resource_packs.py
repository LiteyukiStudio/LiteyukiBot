"""Read-only, layered resource packs for kernel and plugin presentation assets."""

from __future__ import annotations

import json
import zipfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from functools import partial
from hashlib import sha256
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from .services import ServiceKey

RESOURCE_CATALOG_SERVICE = ServiceKey("liteyukibot.resource-packs", 1)
RESOURCE_MANIFEST_FILENAME = "manifest-v1.json"
RESOURCE_MANIFEST_SCHEMA = 1


class ResourcePackError(ValueError):
    """Raised when a resource pack or its workspace index is unsafe or invalid."""


def _token(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ResourcePackError(f"resource pack {subject} must be a non-empty trimmed string")
    return value


def _relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ResourcePackError(f"resource path is unsafe: {value!r}")
    return path.as_posix()


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _manifest_payload(files: Mapping[str, bytes]) -> dict[str, object]:
    entries = [
        {"path": path, "sha256": sha256(content).hexdigest(), "size": len(content)}
        for path, content in sorted(files.items())
    ]
    payload: dict[str, object] = {"files": entries, "schema": RESOURCE_MANIFEST_SCHEMA}
    return {**payload, "root_sha256": sha256(_canonical_json(payload)).hexdigest()}


def write_resource_manifest(root: str | Path) -> Path:
    """Write the explicit integrity manifest for one directory resource pack."""

    directory = Path(root).resolve()
    if not directory.is_dir():
        raise ResourcePackError(f"resource manifest root is not a directory: {directory}")
    files: dict[str, bytes] = {}
    for candidate in directory.rglob("*"):
        if candidate.is_dir():
            continue
        if candidate.is_symlink() or not candidate.resolve().is_relative_to(directory):
            raise ResourcePackError(f"resource pack contains an unsafe file: {candidate}")
        relative = _relative_path(candidate.relative_to(directory).as_posix())
        if relative == RESOURCE_MANIFEST_FILENAME:
            continue
        files[relative] = candidate.read_bytes()
    manifest = directory / RESOURCE_MANIFEST_FILENAME
    manifest.write_bytes(_canonical_json(_manifest_payload(files)) + b"\n")
    return manifest


def verify_resource_manifest(root: str | Path) -> None:
    """Verify a directory resource pack without loading it into a catalog."""

    directory = Path(root).resolve()
    if not directory.is_dir():
        raise ResourcePackError(f"resource manifest root is not a directory: {directory}")
    files: dict[str, ResourceFile] = {}
    for candidate in directory.rglob("*"):
        if candidate.is_dir():
            continue
        if candidate.is_symlink() or not candidate.resolve().is_relative_to(directory):
            raise ResourcePackError(f"resource pack contains an unsafe file: {candidate}")
        relative = _relative_path(candidate.relative_to(directory).as_posix())
        files[relative] = ResourceFile("verification", relative, candidate.read_bytes)
    _verify_manifest(files)


@dataclass(frozen=True, slots=True)
class ResourcePackDeclaration:
    """A package-owned resource root declared by an enabled native plugin."""

    package: str
    root: str = "resources"

    def __post_init__(self) -> None:
        _token(self.package, "package")
        _relative_path(self.root)


@dataclass(frozen=True, slots=True)
class ResourcePackMetadata:
    id: str
    name: str
    version: str
    description: str
    origin: str
    name_key: str | None = None
    description_key: str | None = None
    icon: str | None = None


@dataclass(frozen=True, slots=True)
class ResourceFile:
    pack_id: str
    path: str
    _read: Callable[[], bytes]

    def read_bytes(self) -> bytes:
        return self._read()

    def read_text(self, encoding: str = "utf-8") -> str:
        return self.read_bytes().decode(encoding)


@dataclass(frozen=True, slots=True)
class ResourcePack:
    metadata: ResourcePackMetadata
    files: Mapping[str, ResourceFile]


class ResourceCatalog:
    """A deterministic overlay of resource-pack paths without extraction or copying."""

    def __init__(self, packs: Iterable[ResourcePack]) -> None:
        ordered = tuple(packs)
        ids: set[str] = set()
        files: dict[str, ResourceFile] = {}
        for pack in ordered:
            if pack.metadata.id in ids:
                raise ResourcePackError(f"duplicate resource pack id: {pack.metadata.id}")
            ids.add(pack.metadata.id)
            files.update(pack.files)
        self._packs = ordered
        self._files = files

    @property
    def packs(self) -> tuple[ResourcePackMetadata, ...]:
        return tuple(pack.metadata for pack in self._packs)

    def pack(self, pack_id: str) -> ResourcePackMetadata:
        for pack in self._packs:
            if pack.metadata.id == pack_id:
                return pack.metadata
        raise ResourcePackError(f"resource pack does not exist: {pack_id}")

    def pack_for_declaration(self, declaration: ResourcePackDeclaration) -> ResourcePack:
        """Return the installed package pack owned by one extension declaration."""

        origin = f"package:{declaration.package}:{declaration.root}"
        matches = tuple(pack for pack in self._packs if pack.metadata.origin == origin)
        if len(matches) != 1:
            raise ResourcePackError(
                f"resource declaration does not resolve to exactly one installed pack: {origin}"
            )
        return matches[0]

    def pack_files(self, pack_id: str, prefix: str = "") -> tuple[ResourceFile, ...]:
        """Return files from one pack without applying the catalog overlay."""

        for pack in self._packs:
            if pack.metadata.id == pack_id:
                normalized = "" if not prefix else _relative_path(prefix).rstrip("/") + "/"
                return tuple(
                    resource for path, resource in sorted(pack.files.items()) if path.startswith(normalized)
                )
        raise ResourcePackError(f"resource pack does not exist: {pack_id}")

    def icon(self, pack_id: str) -> ResourceFile | None:
        """Return a validated package icon for a future local presentation client."""

        for pack in self._packs:
            if pack.metadata.id == pack_id:
                return pack.files.get(pack.metadata.icon) if pack.metadata.icon else None
        raise ResourcePackError(f"resource pack does not exist: {pack_id}")

    def get(self, path: str) -> ResourceFile | None:
        return self._files.get(_relative_path(path))

    def require(self, path: str) -> ResourceFile:
        resource = self.get(path)
        if resource is None:
            raise ResourcePackError(f"resource does not exist: {path}")
        return resource

    def paths(self, prefix: str = "") -> tuple[str, ...]:
        normalized = "" if not prefix else _relative_path(prefix).rstrip("/") + "/"
        return tuple(path for path in sorted(self._files) if path.startswith(normalized))

    def files(self, prefix: str = "") -> tuple[ResourceFile, ...]:
        """Return layered files without collapsing same-path catalog entries."""

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
        builtin = Path(__file__).with_name("builtin_resources") / "vanilla_language"
        packs = [_load_directory(builtin, "kernel")]
        for declaration in sorted(plugin_packs, key=lambda item: (item.package, item.root)):
            root = resources.files(declaration.package).joinpath(declaration.root)
            packs.append(_load_traversable(root, f"package:{declaration.package}:{declaration.root}"))
        packs.extend(_load_workspace_packs(Path(workspace)))
        return cls(packs)


def _metadata(value: object, origin: str, fallback_id: str) -> ResourcePackMetadata:
    if not isinstance(value, dict):
        raise ResourcePackError(f"resource pack metadata must be an object: {origin}")
    pack_id = _token(value.get("id", fallback_id), "id")
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
        name_key=name_key,
        description_key=description_key,
        icon=icon,
    )


def _optional_token(value: object, subject: str) -> str | None:
    if value is None:
        return None
    return _token(value, subject)


def _read_metadata(raw: str, origin: str, fallback_id: str) -> ResourcePackMetadata:
    try:
        value: Any = yaml.safe_load(raw)
    except yaml.YAMLError as error:
        raise ResourcePackError(f"cannot parse resource metadata: {origin}") from error
    return _metadata(value, origin, fallback_id)


def _verify_manifest(files: Mapping[str, ResourceFile]) -> None:
    try:
        raw = files[RESOURCE_MANIFEST_FILENAME].read_bytes()
    except KeyError as error:
        raise ResourcePackError("resource pack has no manifest-v1.json") from error
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
    normalized: list[dict[str, object]] = []
    paths: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "size"}:
            raise ResourcePackError("resource manifest entry has an invalid shape")
        path, digest, size = entry.get("path"), entry.get("sha256"), entry.get("size")
        if not isinstance(path, str) or _relative_path(path) != path or path == RESOURCE_MANIFEST_FILENAME:
            raise ResourcePackError("resource manifest entry path is invalid")
        if path in paths or not isinstance(digest, str) or len(digest) != 64 or not isinstance(size, int) or size < 0:
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
    root = root.resolve()
    metadata_path = root / "metadata.yml"
    if not metadata_path.is_file():
        raise ResourcePackError(f"resource pack has no metadata.yml: {root}")
    metadata = _read_metadata(metadata_path.read_text(encoding="utf-8"), str(root), root.name)
    files: dict[str, ResourceFile] = {}
    for candidate in root.rglob("*"):
        if candidate.is_dir():
            continue
        if candidate.is_symlink() or not candidate.resolve().is_relative_to(root):
            raise ResourcePackError(f"resource pack contains an unsafe file: {candidate}")
        relative = _relative_path(candidate.relative_to(root).as_posix())
        files[relative] = ResourceFile(metadata.id, relative, candidate.read_bytes)
    _verify_manifest(files)
    _validate_icon(metadata, files)
    return ResourcePack(metadata, files)


def _load_traversable(root: resources.abc.Traversable, origin: str) -> ResourcePack:
    metadata_file = root.joinpath("metadata.yml")
    if not metadata_file.is_file():
        raise ResourcePackError(f"resource pack has no metadata.yml: {origin}")
    metadata = _read_metadata(metadata_file.read_text(encoding="utf-8"), origin, origin.rsplit(":", 1)[-1])
    files: dict[str, ResourceFile] = {}

    def visit(node: resources.abc.Traversable, prefix: str = "") -> None:
        for child in node.iterdir():
            relative = _relative_path(f"{prefix}/{child.name}" if prefix else child.name)
            if child.is_dir():
                visit(child, relative)
            elif child.is_file():
                files[relative] = ResourceFile(metadata.id, relative, child.read_bytes)

    visit(root)
    _verify_manifest(files)
    _validate_icon(metadata, files)
    return ResourcePack(metadata, files)


def _load_zip(path: Path) -> ResourcePack:
    try:
        with zipfile.ZipFile(path) as archive:
            entries = {entry.filename: entry for entry in archive.infolist() if not entry.is_dir()}
            for name, entry in entries.items():
                _relative_path(name)
                mode = entry.external_attr >> 16
                if mode and mode & 0o170000 == 0o120000:
                    raise ResourcePackError(f"resource ZIP contains a symbolic link: {path}")
            metadata_entry = entries.get("metadata.yml")
            if metadata_entry is None:
                raise ResourcePackError(f"resource ZIP has no metadata.yml: {path}")
            metadata = _read_metadata(archive.read(metadata_entry).decode("utf-8"), str(path), path.stem)
    except zipfile.BadZipFile as error:
        raise ResourcePackError(f"resource ZIP is invalid: {path}") from error
    files = {
        _relative_path(name): ResourceFile(
            metadata.id,
            _relative_path(name),
            partial(_read_zip_entry, path, name),
        )
        for name in entries
    }
    _verify_manifest(files)
    _validate_icon(metadata, files)
    return ResourcePack(metadata, files)


def _validate_icon(metadata: ResourcePackMetadata, files: Mapping[str, ResourceFile]) -> None:
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


def _read_zip_entry(path: Path, name: str) -> bytes:
    with zipfile.ZipFile(path) as archive:
        return archive.read(name)


def _load_workspace_packs(workspace: Path) -> list[ResourcePack]:
    root = workspace.resolve() / "resources"
    index = root / "index.json"
    if not index.exists():
        return []
    try:
        requested = json.loads(index.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ResourcePackError(f"cannot read resource index: {index}") from error
    if not isinstance(requested, list) or any(not isinstance(item, str) for item in requested):
        raise ResourcePackError("resource index must be a list of pack names")
    if len(set(requested)) != len(requested):
        raise ResourcePackError("resource index must not contain duplicate pack names")
    packs: list[ResourcePack] = []
    for name in requested:
        relative = _relative_path(name)
        candidate = (root / relative).resolve()
        if not candidate.is_relative_to(root.resolve()):
            raise ResourcePackError(f"resource index escapes its workspace: {name}")
        if candidate.is_dir():
            packs.append(_load_directory(candidate, "workspace"))
        elif candidate.is_file() and candidate.suffix.lower() == ".zip":
            packs.append(_load_zip(candidate))
        else:
            raise ResourcePackError(f"resource pack listed by index does not exist: {name}")
    return packs


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
