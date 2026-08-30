"""CLI-managed installation of trusted Alpha15 Cordis plugins."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from importlib import metadata
from pathlib import Path
from typing import Any, cast
from urllib.parse import unquote, urlsplit
from urllib.request import Request, url2pathname, urlopen

from tomli_w import dumps as dump_toml

from .config import ConfigWorkspace, load_settings
from .exceptions import PluginError

DEFAULT_PLUGIN_INDEX_URL = (
    "https://raw.githubusercontent.com/LiteyukiStudio/liteyukibot-v7-plugins/main/index.json"
)
CORDIS_PLUGIN_ENTRY_POINT_GROUP = "liteyukibot.cordis_plugins"
PLUGIN_STATE_SCHEMA = 1
MAX_INDEX_BYTES = 8 * 1024 * 1024
MAX_ARTIFACT_BYTES = 256 * 1024 * 1024
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
BUNDLE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9.-]{0,127}$")
PROJECT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9.-]{0,127}$")
MANAGED_DISTRIBUTIONS = frozenset(
    {
        "liteyukibot-v7",
        "liteyukibot-v7-kernel",
        "liteyukibot-v7-cordis",
        "liteyukibot-v7-adapter-onebot",
    }
)


class PluginManagerError(PluginError):
    """Raised when an index, artifact, package, or plugin state is invalid."""


def _object(value: object, subject: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PluginManagerError(f"{subject} must be an object")
    return value


def _required_object(
    value: object, subject: str, required: set[str], optional: set[str] | None = None
) -> dict[str, Any]:
    result = _object(value, subject)
    allowed_optional = optional or set()
    if not required <= set(result) or not set(result) <= required | allowed_optional:
        raise PluginManagerError(f"{subject} has missing or unknown fields")
    return result


def _string(value: object, subject: str, *, maximum: int = 2048, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > maximum or value != value.strip():
        raise PluginManagerError(f"{subject} must be a trimmed string of at most {maximum} characters")
    if not allow_empty and not value:
        raise PluginManagerError(f"{subject} must not be empty")
    return value


def _identifier(value: object, subject: str, pattern: re.Pattern[str]) -> str:
    result = _string(value, subject, maximum=128)
    if not pattern.fullmatch(result):
        raise PluginManagerError(f"{subject} is not a valid lowercase identifier")
    return result


def _strings(value: object, subject: str, *, maximum: int, item_maximum: int = 128) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise PluginManagerError(f"{subject} must be an array with at most {maximum} entries")
    result = tuple(_string(item, f"{subject}[{index}]", maximum=item_maximum) for index, item in enumerate(value))
    if len(set(result)) != len(result):
        raise PluginManagerError(f"{subject} must not contain duplicates")
    return result


def _json_value(value: object, subject: str) -> None:
    if value is None or isinstance(value, (str, int, bool)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PluginManagerError(f"{subject} must contain finite JSON values")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _json_value(item, f"{subject}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise PluginManagerError(f"{subject} object keys must be strings")
            _json_value(item, f"{subject}.{key}")
        return
    raise PluginManagerError(f"{subject} contains non-JSON value {type(value).__name__}")


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PluginManagerError(f"JSON contains duplicate object key {key!r}")
        result[key] = value
    return result


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _artifact_url(value: object, subject: str, *, allow_local: bool) -> str:
    result = _string(value, f"{subject} URL")
    parsed = urlsplit(result)
    if allow_local and (Path(result).expanduser().is_file() or parsed.scheme == "file"):
        return result
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise PluginManagerError(f"{subject} URL must be credential-free HTTPS")
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith((".localhost", ".local")):
        raise PluginManagerError(f"{subject} URL must not target a local hostname")
    try:
        address = ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        return result
    if not address.is_global:
        raise PluginManagerError(f"{subject} URL must not target a private or reserved address")
    return result


@dataclass(frozen=True, slots=True)
class PluginArtifact:
    """One immutable, byte-pinned plugin artifact."""

    url: str
    sha256: str
    bytes: int

    @classmethod
    def from_document(cls, value: object, subject: str, *, allow_local: bool) -> PluginArtifact:
        raw = _required_object(value, subject, {"url", "sha256", "bytes"})
        url = _artifact_url(raw["url"], subject, allow_local=allow_local)
        digest = _string(raw["sha256"], f"{subject} SHA-256", maximum=64)
        if not SHA256_PATTERN.fullmatch(digest):
            raise PluginManagerError(f"{subject} SHA-256 must be lowercase hexadecimal")
        size = raw["bytes"]
        if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= MAX_ARTIFACT_BYTES:
            raise PluginManagerError(f"{subject} byte size is outside the allowed range")
        return cls(url, digest, size)

    def as_document(self) -> dict[str, object]:
        return {"bytes": self.bytes, "sha256": self.sha256, "url": self.url}


@dataclass(frozen=True, slots=True)
class PluginFacet:
    """One runtime and platform-specific install facet."""

    runtime_kind: str
    artifacts: tuple[PluginArtifact, ...]
    wheels: tuple[PluginArtifact, ...]
    systems: tuple[str, ...]
    machines: tuple[str, ...]
    pythons: tuple[str, ...]
    load: Mapping[str, Any]
    capabilities: tuple[str, ...]

    @classmethod
    def from_document(cls, value: object, subject: str, *, allow_local: bool) -> PluginFacet:
        raw = _required_object(
            value,
            subject,
            {"runtime_kind", "artifacts", "wheels", "platform", "load", "capabilities"},
        )
        runtime_kind = _identifier(raw["runtime_kind"], f"{subject} runtime kind", BUNDLE_ID_PATTERN)
        artifacts_raw = raw["artifacts"]
        wheels_raw = raw["wheels"]
        if not isinstance(artifacts_raw, list) or not isinstance(wheels_raw, list):
            raise PluginManagerError(f"{subject} artifacts and wheels must be arrays")
        artifacts = tuple(
            PluginArtifact.from_document(item, f"{subject} artifact {index}", allow_local=allow_local)
            for index, item in enumerate(artifacts_raw)
        )
        wheels = tuple(
            PluginArtifact.from_document(item, f"{subject} wheel {index}", allow_local=allow_local)
            for index, item in enumerate(wheels_raw)
        )
        if not artifacts and not wheels:
            raise PluginManagerError(f"{subject} must contain at least one artifact or wheel")
        platform_raw = _required_object(raw["platform"], f"{subject} platform", {"systems", "machines", "pythons"})
        systems = _strings(platform_raw["systems"], f"{subject} systems", maximum=16)
        machines = _strings(platform_raw["machines"], f"{subject} machines", maximum=32)
        pythons = _strings(platform_raw["pythons"], f"{subject} Pythons", maximum=16)
        if any(not re.fullmatch(r"\d+\.\d+", item) for item in pythons):
            raise PluginManagerError(f"{subject} Python constraints must use major.minor form")
        load = _object(raw["load"], f"{subject} load plan")
        if len(json.dumps(load, separators=(",", ":"), sort_keys=True).encode()) > 64 * 1024:
            raise PluginManagerError(f"{subject} load plan is too large")
        _json_value(load, f"{subject} load plan")
        capabilities = _strings(raw["capabilities"], f"{subject} capabilities", maximum=128)
        return cls(runtime_kind, artifacts, wheels, systems, machines, pythons, load, capabilities)

    def entry_points(self) -> tuple[str, ...]:
        """Return current Cordis entry-point names from the canonical load plan."""

        value = self.load.get("entry_points")
        return _strings(value, "Cordis load.entry_points", maximum=64, item_maximum=128)

    def as_document(self) -> dict[str, object]:
        return {
            "artifacts": [item.as_document() for item in self.artifacts],
            "capabilities": list(self.capabilities),
            "load": dict(self.load),
            "platform": {"machines": list(self.machines), "pythons": list(self.pythons), "systems": list(self.systems)},
            "runtime_kind": self.runtime_kind,
            "wheels": [item.as_document() for item in self.wheels],
        }


@dataclass(frozen=True, slots=True)
class PluginBundle:
    """One versioned bundle from the public plugin index."""

    id: str
    version: str
    display_name: str
    summary: str
    publisher: Mapping[str, Any]
    license: Mapping[str, Any]
    repository: str
    status: str
    dependencies: tuple[str, ...]
    facets: tuple[PluginFacet, ...]
    project_id: str | None = None
    optional: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_document(cls, value: object, position: int, *, allow_local: bool) -> PluginBundle:
        required = {
            "id",
            "version",
            "display_name",
            "summary",
            "publisher",
            "license",
            "repository",
            "status",
            "dependencies",
            "facets",
        }
        optional_names = {
            "homepage",
            "yanked_reason",
            "project_id",
            "description",
            "tags",
            "compatibility",
            "gallery",
            "changelog",
        }
        subject = f"bundle {position}"
        raw = _required_object(value, subject, required, optional_names)
        bundle_id = _identifier(raw["id"], f"{subject} ID", BUNDLE_ID_PATTERN)
        version = _string(raw["version"], f"{subject} version", maximum=64)
        display_name = _string(raw["display_name"], f"{subject} display name", maximum=120)
        summary = _string(raw["summary"], f"{subject} summary", maximum=240)
        publisher = _required_object(raw["publisher"], f"{subject} publisher", {"id", "name", "url"})
        _identifier(publisher["id"], f"{subject} publisher ID", re.compile(r"^[a-z][a-z0-9-]{0,63}$"))
        _string(publisher["name"], f"{subject} publisher name", maximum=80)
        _artifact_url(publisher["url"], f"{subject} publisher", allow_local=False)
        license_raw = _object(raw["license"], f"{subject} license")
        if set(license_raw) - {"expression", "url"}:
            raise PluginManagerError(f"{subject} license has unknown fields")
        _string(license_raw.get("expression"), f"{subject} license expression", maximum=128)
        if "url" in license_raw:
            _artifact_url(license_raw["url"], f"{subject} license", allow_local=False)
        repository = _artifact_url(raw["repository"], f"{subject} repository", allow_local=False)
        for name in ("homepage",):
            if name in raw:
                _artifact_url(raw[name], f"{subject} {name}", allow_local=False)
        status = raw["status"]
        if status not in {"active", "yanked"}:
            raise PluginManagerError(f"{subject} status must be active or yanked")
        if status == "yanked":
            _string(raw.get("yanked_reason"), f"{subject} yanked reason", maximum=240)
        elif "yanked_reason" in raw:
            raise PluginManagerError(f"{subject} active release cannot have a yanked reason")
        dependencies = _strings(raw["dependencies"], f"{subject} dependencies", maximum=64, item_maximum=128)
        if any(not BUNDLE_ID_PATTERN.fullmatch(item) for item in dependencies):
            raise PluginManagerError(f"{subject} dependencies must be lowercase bundle IDs")
        facets_raw = raw["facets"]
        if not isinstance(facets_raw, list) or not facets_raw:
            raise PluginManagerError(f"{subject} must contain at least one facet")
        facets = tuple(
            PluginFacet.from_document(item, f"{subject} facet {index}", allow_local=allow_local)
            for index, item in enumerate(facets_raw)
        )
        if len({facet.runtime_kind for facet in facets}) != len(facets):
            raise PluginManagerError(f"{subject} repeats a runtime kind")
        project_id: str | None = None
        if "project_id" in raw:
            project_id = _identifier(raw["project_id"], f"{subject} project ID", PROJECT_ID_PATTERN)
            if project_id in MANAGED_DISTRIBUTIONS:
                raise PluginManagerError(f"{subject} project ID targets a LiteyukiBot distribution")
        optional = {name: raw[name] for name in optional_names if name in raw}
        for name in ("description",):
            if name in optional:
                _string(optional[name], f"{subject} {name}", maximum=8192)
        for name in ("tags", "compatibility", "gallery", "changelog"):
            if name in optional:
                _strings(optional[name], f"{subject} {name}", maximum=64, item_maximum=2048)
        return cls(
            bundle_id,
            version,
            display_name,
            summary,
            dict(publisher),
            dict(license_raw),
            repository,
            status,
            dependencies,
            facets,
            project_id,
            optional,
        )

    def facet_for_current_platform(self) -> PluginFacet:
        current_python = f"{sys.version_info.major}.{sys.version_info.minor}"
        current_system = platform.system().lower()
        current_machine = _machine_alias(platform.machine())
        matching = [
            facet
            for facet in self.facets
            if facet.runtime_kind == "cordis"
            and (not facet.pythons or current_python in facet.pythons)
            and (not facet.systems or current_system in {_system_alias(item) for item in facet.systems})
            and (not facet.machines or current_machine in {_machine_alias(item) for item in facet.machines})
        ]
        if not matching:
            raise PluginManagerError(
                f"plugin bundle {self.id!r} has no Cordis facet compatible with "
                f"Python {current_python}, {current_system}/{current_machine}"
            )
        return matching[0]

    def as_document(self) -> dict[str, object]:
        result: dict[str, object] = {
            "dependencies": list(self.dependencies),
            "facets": [facet.as_document() for facet in self.facets],
            "id": self.id,
            "license": dict(self.license),
            "publisher": dict(self.publisher),
            "repository": self.repository,
            "status": self.status,
            "summary": self.summary,
            "version": self.version,
        }
        if self.project_id is not None:
            result["project_id"] = self.project_id
        result.update(self.optional)
        return result


@dataclass(frozen=True, slots=True)
class PluginIndex:
    """Validated schema-1/2 plugin index."""

    schema: int
    bundles: tuple[PluginBundle, ...]

    @classmethod
    def from_document(cls, value: object, *, allow_local: bool = False) -> PluginIndex:
        raw = _object(value, "plugin index")
        schema = raw.get("schema")
        if isinstance(schema, bool) or schema not in {1, 2}:
            raise PluginManagerError("plugin index schema must be 1 or 2")
        if set(raw) != {"schema", "bundles"} or not isinstance(raw["bundles"], list):
            raise PluginManagerError("plugin index must contain exactly schema and bundles")
        if schema == 1:
            if raw["bundles"]:
                raise PluginManagerError("schema-1 plugin indexes cannot be installed by Alpha15")
            return cls(1, ())
        bundles = tuple(
            PluginBundle.from_document(item, position, allow_local=allow_local)
            for position, item in enumerate(raw["bundles"])
        )
        by_id = {bundle.id: bundle for bundle in bundles}
        if len(by_id) != len(bundles):
            raise PluginManagerError("plugin index contains duplicate bundle IDs")
        project_owners: dict[str, str] = {}
        entry_point_owners: dict[str, str] = {}
        for bundle in bundles:
            if bundle.project_id is not None:
                previous = project_owners.setdefault(bundle.project_id, bundle.id)
                if previous != bundle.id:
                    raise PluginManagerError(
                        f"plugin bundles {previous!r} and {bundle.id!r} share project ID {bundle.project_id!r}"
                    )
            for facet in bundle.facets:
                if facet.runtime_kind != "cordis":
                    continue
                for entry_point in facet.entry_points():
                    previous = entry_point_owners.setdefault(entry_point, bundle.id)
                    if previous != bundle.id:
                        raise PluginManagerError(
                            f"plugin bundles {previous!r} and {bundle.id!r} share entry point {entry_point!r}"
                        )
        for bundle in bundles:
            for dependency in bundle.dependencies:
                if dependency not in by_id:
                    raise PluginManagerError(f"plugin bundle {bundle.id!r} has unknown dependency {dependency!r}")
        return cls(2, bundles)

    def require(self, bundle_id: str) -> PluginBundle:
        for bundle in self.bundles:
            if bundle.id == bundle_id:
                if bundle.status == "yanked":
                    reason = bundle.optional.get("yanked_reason")
                    suffix = f": {reason}" if reason else ""
                    raise PluginManagerError(f"plugin bundle {bundle_id!r} is yanked{suffix}")
                return bundle
        raise PluginManagerError(f"plugin bundle {bundle_id!r} was not found in the plugin index")

    def resolve(self, root_id: str) -> tuple[PluginBundle, ...]:
        resolved: list[PluginBundle] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(bundle_id: str) -> None:
            if bundle_id in visited:
                return
            if bundle_id in visiting:
                raise PluginManagerError(f"plugin dependency cycle includes {bundle_id!r}")
            visiting.add(bundle_id)
            bundle = self.require(bundle_id)
            for dependency in bundle.dependencies:
                visit(dependency)
            visiting.remove(bundle_id)
            visited.add(bundle_id)
            resolved.append(bundle)

        visit(root_id)
        return tuple(resolved)


@dataclass(frozen=True, slots=True)
class InstalledPlugin:
    """Local provenance and activation state for one installed bundle."""

    id: str
    version: str
    project_id: str
    entry_points: tuple[str, ...]
    dependencies: tuple[str, ...]
    source: str
    enabled: bool
    config: Mapping[str, Any]

    @classmethod
    def from_document(cls, value: object, subject: str) -> InstalledPlugin:
        raw = _required_object(
            value,
            subject,
            {"id", "version", "project_id", "entry_points", "dependencies", "source", "enabled", "config"},
        )
        plugin_id = _identifier(raw["id"], f"{subject} ID", BUNDLE_ID_PATTERN)
        project_id = _identifier(raw["project_id"], f"{subject} project ID", PROJECT_ID_PATTERN)
        if project_id in MANAGED_DISTRIBUTIONS:
            raise PluginManagerError(f"{subject} project ID targets a LiteyukiBot distribution")
        entry_points = _strings(raw["entry_points"], f"{subject} entry points", maximum=64, item_maximum=128)
        dependencies = _strings(raw["dependencies"], f"{subject} dependencies", maximum=64, item_maximum=128)
        source = _string(raw["source"], f"{subject} source")
        if not isinstance(raw["enabled"], bool):
            raise PluginManagerError(f"{subject} enabled must be a boolean")
        config = _object(raw["config"], f"{subject} config")
        _json_value(config, f"{subject} config")
        return cls(
            plugin_id,
            _string(raw["version"], f"{subject} version", maximum=64),
            project_id,
            entry_points,
            dependencies,
            source,
            raw["enabled"],
            dict(config),
        )

    def as_document(self) -> dict[str, object]:
        return {
            "config": dict(self.config),
            "dependencies": list(self.dependencies),
            "enabled": self.enabled,
            "entry_points": list(self.entry_points),
            "id": self.id,
            "project_id": self.project_id,
            "source": self.source,
            "version": self.version,
        }


class _StateStore:
    def __init__(self, workspace: ConfigWorkspace) -> None:
        self.directory = workspace.directory / ".liteyuki"
        self.path = self.directory / "plugins.json"

    def load(self) -> dict[str, InstalledPlugin]:
        self._check_paths()
        if not self.path.exists():
            return {}
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicate_keys)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, PluginManagerError) as error:
            raise PluginManagerError(f"cannot read plugin state {self.path}: {error}") from error
        raw = _required_object(document, "plugin state", {"schema", "plugins"})
        if raw["schema"] != PLUGIN_STATE_SCHEMA or isinstance(raw["schema"], bool):
            raise PluginManagerError(f"plugin state schema must be {PLUGIN_STATE_SCHEMA}")
        plugins = _object(raw["plugins"], "plugin state plugins")
        result: dict[str, InstalledPlugin] = {}
        for position, (plugin_id, value) in enumerate(plugins.items()):
            record = InstalledPlugin.from_document(value, f"plugin state record {position}")
            if record.id != plugin_id:
                raise PluginManagerError(f"plugin state key {plugin_id!r} does not match its record ID")
            result[record.id] = record
        return result

    def save(self, plugins: Mapping[str, InstalledPlugin]) -> None:
        self._check_paths(create_directory=True)
        document = {
            "plugins": {plugin_id: plugins[plugin_id].as_document() for plugin_id in sorted(plugins)},
            "schema": PLUGIN_STATE_SCHEMA,
        }
        _atomic_write_text(self.path, _canonical_json(document))

    def _check_paths(self, *, create_directory: bool = False) -> None:
        if self.directory.is_symlink() or self.path.is_symlink():
            raise PluginManagerError("plugin state paths must not be symlinks")
        if self.directory.exists() and not self.directory.is_dir():
            raise PluginManagerError(f"plugin state directory is not a directory: {self.directory}")
        if create_directory:
            self.directory.mkdir(parents=True, exist_ok=True)


class PluginManager:
    """Coordinate index consumption, current-interpreter installation, and CLI activation."""

    def __init__(self, workspace: ConfigWorkspace, *, index_url: str = DEFAULT_PLUGIN_INDEX_URL) -> None:
        self.workspace = workspace
        self.index_url = index_url
        self.state = _StateStore(workspace)

    def fetch_index(self) -> PluginIndex:
        local = _local_path(self.index_url)
        allow_local = local is not None
        try:
            raw = (
                _read_bounded(local, self.index_url, MAX_INDEX_BYTES)
                if local is not None
                else _read_remote(self.index_url)
            )
            document = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_no_duplicate_keys)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, PluginManagerError) as error:
            if isinstance(error, PluginManagerError):
                raise
            raise PluginManagerError(f"cannot fetch plugin index {self.index_url}: {error}") from error
        return PluginIndex.from_document(document, allow_local=allow_local)

    def installed(self) -> tuple[InstalledPlugin, ...]:
        records = self.state.load()
        return tuple(records[plugin_id] for plugin_id in sorted(records))

    def install(self, bundle_id: str, *, enable: bool = True) -> tuple[InstalledPlugin, ...]:
        index = self.fetch_index()
        bundles = index.resolve(bundle_id)
        records = self.state.load()
        staged: list[tuple[PluginBundle, PluginFacet, Path]] = []
        with tempfile.TemporaryDirectory(prefix="liteyuki-plugin-") as directory:
            staging = Path(directory)
            for bundle in bundles:
                facet = bundle.facet_for_current_platform()
                project_id = bundle.project_id
                if project_id is None:
                    raise PluginManagerError(
                        f"plugin bundle {bundle.id!r} has no project_id; it cannot be installed by Alpha15"
                    )
                if not facet.wheels:
                    raise PluginManagerError(f"plugin bundle {bundle.id!r} has no Python wheel")
                if facet.artifacts:
                    raise PluginManagerError(
                        f"plugin bundle {bundle.id!r} declares non-wheel artifacts, which Alpha15 cannot install"
                    )
                if not _is_ready(bundle, facet):
                    wheel = _select_wheel(facet.wheels)
                    filename = _wheel_filename(wheel.url)
                    target = staging / f"{len(staged):03d}" / filename
                    target.parent.mkdir()
                    _download_verified(wheel, target)
                    staged.append((bundle, facet, target))
            if staged:
                _run_uv_install(tuple(item[2] for item in staged))
            for bundle in bundles:
                facet = bundle.facet_for_current_platform()
                _verify_installed_bundle(bundle, facet)

        updated = dict(records)
        selected_ids = {bundle.id for bundle in bundles}
        for bundle in bundles:
            facet = bundle.facet_for_current_platform()
            old = records.get(bundle.id)
            project_id = bundle.project_id
            if project_id is None:
                raise PluginManagerError(f"plugin bundle {bundle.id!r} has no project_id")
            updated[bundle.id] = InstalledPlugin(
                id=bundle.id,
                version=bundle.version,
                project_id=project_id,
                entry_points=facet.entry_points(),
                dependencies=bundle.dependencies,
                source=self.index_url,
                enabled=enable or (old.enabled if old is not None else False),
                config=dict(old.config) if old is not None else {},
            )
        if enable:
            self._activate(tuple(entry for bundle in bundles for entry in _entry_points(bundle)), updated)
        self.state.save(updated)
        return tuple(updated[bundle_id] for bundle_id in sorted(selected_ids))

    def enable(self, bundle_id: str) -> InstalledPlugin:
        records = self.state.load()
        record = _require_record(records, bundle_id)
        _verify_record_entry_points(record)
        updated = replace(record, enabled=True)
        records[bundle_id] = updated
        self._activate(record.entry_points, records)
        self.state.save(records)
        return updated

    def disable(self, bundle_id: str) -> InstalledPlugin:
        records = self.state.load()
        record = _require_record(records, bundle_id)
        for other in records.values():
            if other.id != bundle_id and other.enabled and _depends_on(other.id, bundle_id, records, set()):
                raise PluginManagerError(f"plugin bundle {bundle_id!r} is required by enabled {other.id!r}")
        settings, _document = self._file_settings()
        enabled, config = _cordis_values(settings)
        saved_config = dict(record.config)
        for entry_point in record.entry_points:
            if entry_point in config:
                saved_config[entry_point] = config.pop(entry_point)
        enabled = tuple(item for item in enabled if item not in record.entry_points)
        self._write_cordis(enabled, config)
        updated = replace(record, enabled=False, config=saved_config)
        records[bundle_id] = updated
        self.state.save(records)
        return updated

    def config(self, bundle_id: str) -> dict[str, Any]:
        """Return one bundle's entry-point configuration from the local workspace."""

        record = _require_record(self.state.load(), bundle_id)
        if not record.enabled:
            return dict(record.config)
        settings, _document = self._file_settings()
        _enabled, current = _cordis_values(settings)
        return {
            entry_point: current[entry_point]
            for entry_point in record.entry_points
            if entry_point in current
        }

    def set_config(
        self,
        bundle_id: str,
        assignments: Iterable[str],
        *,
        entry_point: str | None = None,
    ) -> dict[str, Any]:
        """Set JSON-compatible keys in one installed bundle's local config."""

        records = self.state.load()
        record = _require_record(records, bundle_id)
        selected_entry_point = _config_entry_point(record, entry_point)
        if record.enabled:
            settings, _document = self._file_settings()
            _enabled, current = _cordis_values(settings)
            value = current.get(selected_entry_point, {})
        else:
            value = record.config.get(selected_entry_point, {})
        config = _object(value, f"plugin {bundle_id} configuration")
        config = json.loads(json.dumps(config))
        _apply_assignments(config, assignments)
        if record.enabled:
            settings, _document = self._file_settings()
            enabled, current = _cordis_values(settings)
            current[selected_entry_point] = config
            self._write_cordis(enabled, current)
        else:
            saved = dict(record.config)
            saved[selected_entry_point] = config
            records[bundle_id] = replace(record, config=saved)
            self.state.save(records)
        return {selected_entry_point: config}

    def clear_config(self, bundle_id: str, *, entry_point: str | None = None) -> None:
        """Remove one or all entry-point configuration tables."""

        records = self.state.load()
        record = _require_record(records, bundle_id)
        selected = (entry_point,) if entry_point is not None else record.entry_points
        if any(item not in record.entry_points for item in selected):
            raise PluginManagerError(f"entry point is not owned by plugin bundle {bundle_id!r}")
        if record.enabled:
            settings, _document = self._file_settings()
            enabled, current = _cordis_values(settings)
            for item in selected:
                current.pop(item, None)
            self._write_cordis(enabled, current)
        else:
            saved = {key: value for key, value in record.config.items() if key not in selected}
            records[bundle_id] = replace(record, config=saved)
            self.state.save(records)

    def remove(self, bundle_id: str) -> None:
        records = self.state.load()
        record = _require_record(records, bundle_id)
        for other in records.values():
            if other.id != bundle_id and _depends_on(other.id, bundle_id, records, set()):
                raise PluginManagerError(f"plugin bundle {bundle_id!r} is required by installed {other.id!r}")
        if any(other.id != bundle_id and other.project_id == record.project_id for other in records.values()):
            raise PluginManagerError(f"plugin distribution {record.project_id!r} is shared by another installed bundle")
        if record.enabled:
            self.disable(bundle_id)
            records = self.state.load()
        _run_uv_uninstall(record.project_id)
        records.pop(bundle_id, None)
        self.state.save(records)

    def _activate(self, entry_points: Iterable[str], records: Mapping[str, InstalledPlugin]) -> None:
        settings, _document = self._file_settings()
        enabled, config = _cordis_values(settings)
        enabled_values = list(enabled)
        for entry_point in entry_points:
            if entry_point not in enabled_values:
                enabled_values.append(entry_point)
        for record in records.values():
            if record.enabled:
                for entry_point, value in record.config.items():
                    config.setdefault(entry_point, value)
        self._write_cordis(tuple(enabled_values), config)

    def _file_settings(self) -> tuple[Any, dict[str, Any]]:
        path = self.workspace.prepare()
        try:
            document = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
            raise PluginManagerError(f"cannot read project configuration {path}: {error}") from error
        if not isinstance(document, dict):
            raise PluginManagerError(f"project configuration {path} must be a TOML object")
        try:
            return load_settings(path, environ={}), document
        except Exception as error:
            raise PluginManagerError(f"project configuration is invalid: {error}") from error

    def _write_cordis(self, enabled: tuple[str, ...], config: Mapping[str, Any]) -> None:
        path = self.workspace.prepare()
        if path.is_symlink():
            raise PluginManagerError("project configuration must not be a symlink")
        original = path.read_bytes()
        try:
            document = tomllib.loads(original.decode("utf-8"))
            if not isinstance(document, dict):
                raise PluginManagerError("project configuration must be a TOML object")
            current = document.get("cordis", {})
            if not isinstance(current, dict):
                raise PluginManagerError("[cordis] must be a TOML table")
            cordis = dict(current)
            cordis["enabled"] = list(enabled)
            cordis["config"] = dict(config)
            document["cordis"] = cordis
            _atomic_write_text(path, dump_toml(document))
            load_settings(path, environ={})
        except Exception as error:
            try:
                _atomic_write_bytes(path, original)
            except OSError as restore_error:
                raise PluginManagerError(
                    "cannot update project configuration and cannot restore it: "
                    f"{restore_error}"
                ) from error
            if isinstance(error, PluginManagerError):
                raise
            raise PluginManagerError(f"updated project configuration is invalid: {error}") from error


def _cordis_values(settings: Any) -> tuple[tuple[str, ...], dict[str, Any]]:
    dumped = settings.cordis.model_dump(mode="json")
    enabled = tuple(cast(list[str], dumped["enabled"]))
    config = cast(dict[str, Any], dumped["config"])
    return enabled, dict(config)


def _entry_points(bundle: PluginBundle) -> tuple[str, ...]:
    return bundle.facet_for_current_platform().entry_points()


def _require_record(records: Mapping[str, InstalledPlugin], bundle_id: str) -> InstalledPlugin:
    record = records.get(bundle_id)
    if record is None:
        raise PluginManagerError(f"plugin bundle {bundle_id!r} is not installed")
    return record


def _config_entry_point(record: InstalledPlugin, selected: str | None) -> str:
    if selected is None:
        if len(record.entry_points) != 1:
            raise PluginManagerError("--entry-point is required for a bundle with multiple entry points")
        return record.entry_points[0]
    if selected not in record.entry_points:
        raise PluginManagerError(f"entry point {selected!r} is not owned by plugin bundle {record.id!r}")
    return selected


def _apply_assignments(config: dict[str, Any], assignments: Iterable[str]) -> None:
    found = False
    for position, assignment in enumerate(assignments):
        if not isinstance(assignment, str) or "=" not in assignment:
            raise PluginManagerError(f"plugin config assignment {position} must use KEY=VALUE")
        key, raw_value = assignment.split("=", 1)
        path = tuple(part.strip() for part in key.split("."))
        if not path or any(not part for part in path):
            raise PluginManagerError(f"plugin config assignment {position} has an empty key")
        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError:
            value = raw_value
        _json_value(value, f"plugin config assignment {position}")
        cursor = config
        for part in path[:-1]:
            child = cursor.get(part)
            if child is None:
                child = {}
                cursor[part] = child
            if not isinstance(child, dict):
                raise PluginManagerError(f"plugin config path {key!r} crosses a non-object value")
            cursor = child
        cursor[path[-1]] = value
        found = True
    if not found:
        raise PluginManagerError("at least one plugin config assignment is required")


def _depends_on(
    candidate_id: str, target_id: str, records: Mapping[str, InstalledPlugin], visiting: set[str]
) -> bool:
    if candidate_id in visiting:
        return False
    visiting.add(candidate_id)
    candidate = records[candidate_id]
    for dependency in candidate.dependencies:
        if dependency == target_id or dependency in records and _depends_on(dependency, target_id, records, visiting):
            return True
    return False


def _local_path(value: str) -> Path | None:
    candidate = Path(value).expanduser()
    if candidate.is_file():
        return candidate.resolve()
    parsed = urlsplit(value)
    if parsed.scheme != "file":
        return None
    path = Path(url2pathname(unquote(parsed.path)))
    if not path.is_file():
        raise PluginManagerError(f"local plugin index does not exist: {path}")
    return path.resolve()


def _read_bounded(path: Path, source: str, maximum: int) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise PluginManagerError(f"{source} exceeds the {maximum}-byte limit")
    return data


def _validate_response_url(value: str, subject: str) -> None:
    _artifact_url(value, subject, allow_local=False)


def _read_remote(source: str) -> bytes:
    parsed = urlsplit(source)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise PluginManagerError("plugin index URL must be credential-free HTTPS or a local test file")
    request = Request(source, headers={"User-Agent": "LiteyukiBot/7 plugin-manager"})
    with urlopen(request, timeout=30) as response:
        _validate_response_url(response.geturl(), "plugin index")
        data = cast(bytes, response.read(MAX_INDEX_BYTES + 1))
    if len(data) > MAX_INDEX_BYTES:
        raise PluginManagerError(f"plugin index exceeds the {MAX_INDEX_BYTES}-byte limit")
    return data


def _local_artifact_path(url: str) -> Path | None:
    candidate = Path(url).expanduser()
    if candidate.is_file():
        return candidate
    parsed = urlsplit(url)
    if parsed.scheme != "file":
        return None
    path = Path(url2pathname(unquote(parsed.path)))
    if not path.is_file():
        raise PluginManagerError(f"local plugin artifact does not exist: {path}")
    return path


def _download_verified(artifact: PluginArtifact, target: Path) -> None:
    local = _local_artifact_path(artifact.url)
    stream: Any
    if local is not None:
        stream = local.open("rb")
    else:
        parsed = urlsplit(artifact.url)
        if parsed.scheme != "https" or parsed.username or parsed.password:
            raise PluginManagerError("plugin artifacts must use credential-free HTTPS")
        stream = urlopen(
            Request(artifact.url, headers={"User-Agent": "LiteyukiBot/7 plugin-manager"}), timeout=60
        )
        _validate_response_url(stream.geturl(), "plugin artifact")
    try:
        digest = hashlib.sha256()
        total = 0
        with target.open("wb") as output:
            while chunk := stream.read(1024 * 1024):
                total += len(chunk)
                if total > artifact.bytes or total > MAX_ARTIFACT_BYTES:
                    raise PluginManagerError(f"artifact {artifact.url} exceeds its declared byte size")
                digest.update(chunk)
                output.write(chunk)
    finally:
        stream.close()
    if total != artifact.bytes:
        raise PluginManagerError(f"artifact {artifact.url} has {total} bytes; expected {artifact.bytes}")
    if digest.hexdigest() != artifact.sha256:
        raise PluginManagerError(f"artifact {artifact.url} has a SHA-256 digest different from the index")


def _wheel_filename(url: str) -> str:
    local = _local_artifact_path(url)
    filename = local.name if local is not None else Path(unquote(urlsplit(url).path)).name
    if not filename or not filename.lower().endswith(".whl") or filename in {".", ".."}:
        raise PluginManagerError(f"plugin wheel URL does not contain a wheel filename: {url}")
    return filename


def _select_wheel(wheels: tuple[PluginArtifact, ...]) -> PluginArtifact:
    compatible = [wheel for wheel in wheels if _wheel_is_compatible(_wheel_filename(wheel.url))]
    if not compatible:
        raise PluginManagerError("plugin facet has no wheel compatible with the current Python and platform")
    universal = [wheel for wheel in compatible if _wheel_filename(wheel.url).lower().endswith("-py3-none-any.whl")]
    if len(universal) == 1:
        return universal[0]
    if len(compatible) != 1:
        names = ", ".join(_wheel_filename(wheel.url) for wheel in compatible)
        raise PluginManagerError(f"plugin facet has multiple compatible wheels; index must disambiguate: {names}")
    return compatible[0]


def _wheel_is_compatible(filename: str) -> bool:
    stem = filename[:-4]
    parts = stem.split("-")
    if len(parts) < 5:
        return False
    python_tags, abi_tags, platform_tags = parts[-3:]
    major = sys.version_info.major
    minor = sys.version_info.minor
    python_options = {"py3", f"py{major}", f"py{major}{minor}"}
    if platform.python_implementation() == "CPython":
        python_options.add(f"cp{major}{minor}")
    if not any(tag in python_options for tag in python_tags.split(".")):
        return False
    if not any(tag in {"none", "abi3", f"cp{major}{minor}"} for tag in abi_tags.split(".")):
        return False
    machine = _machine_alias(platform.machine())
    system = platform.system().lower()
    for tag in platform_tags.split("."):
        lowered = tag.lower()
        if lowered == "any":
            return True
        windows_machine = {"x86_64": "amd64", "x86": "32", "arm64": "arm64"}.get(machine, machine)
        if system == "windows" and lowered.startswith("win") and windows_machine in lowered:
            return True
        if system == "linux" and (lowered.startswith(("linux", "manylinux", "musllinux")) and machine in lowered):
            return True
        if system == "darwin" and lowered.startswith("macosx") and (machine in lowered or "universal2" in lowered):
            return True
    return False


def _machine_alias(value: str) -> str:
    lowered = value.lower().replace("-", "_")
    return {"amd64": "x86_64", "x64": "x86_64", "aarch64": "arm64"}.get(lowered, lowered)


def _system_alias(value: str) -> str:
    lowered = value.lower()
    return {"win": "windows", "win32": "windows", "darwin": "darwin", "macos": "darwin"}.get(lowered, lowered)


def _is_ready(bundle: PluginBundle, facet: PluginFacet) -> bool:
    project_id = bundle.project_id
    if project_id is None:
        return False
    try:
        version = metadata.version(project_id)
    except metadata.PackageNotFoundError:
        return False
    if version != bundle.version:
        return False
    try:
        _verify_record_entry_points(
            InstalledPlugin(
                bundle.id,
                bundle.version,
                project_id,
                facet.entry_points(),
                bundle.dependencies,
                "",
                True,
                {},
            )
        )
    except PluginManagerError:
        return False
    return True


def _verify_installed_bundle(bundle: PluginBundle, facet: PluginFacet) -> None:
    project_id = bundle.project_id
    if project_id is None:
        raise PluginManagerError(f"plugin bundle {bundle.id!r} has no project_id")
    try:
        version = metadata.version(project_id)
    except metadata.PackageNotFoundError as error:
        raise PluginManagerError(f"installed distribution {project_id!r} was not found") from error
    if version != bundle.version:
        raise PluginManagerError(
            f"installed distribution {project_id!r} is version {version}, expected {bundle.version}"
        )
    _verify_entry_points(facet.entry_points(), project_id=project_id)


def _verify_record_entry_points(record: InstalledPlugin) -> None:
    try:
        version = metadata.version(record.project_id)
    except metadata.PackageNotFoundError as error:
        raise PluginManagerError(f"installed distribution {record.project_id!r} was not found") from error
    if version != record.version:
        raise PluginManagerError(
            f"installed distribution {record.project_id!r} is version {version}, expected {record.version}"
        )
    _verify_entry_points(record.entry_points, project_id=record.project_id)


def _verify_entry_points(expected: tuple[str, ...], *, project_id: str) -> None:
    distributions = {
        entry.name: _normalise_distribution(entry.dist.name)
        for entry in metadata.entry_points(group=CORDIS_PLUGIN_ENTRY_POINT_GROUP)
        if entry.dist is not None
    }
    expected_distribution = _normalise_distribution(project_id)
    missing = tuple(
        entry
        for entry in expected
        if distributions.get(entry) != expected_distribution
    )
    if missing:
        names = ", ".join(repr(item) for item in missing)
        raise PluginManagerError(f"installed package does not expose Cordis entry points: {names}")


def _normalise_distribution(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).casefold()


def _uv() -> str:
    executable = shutil.which("uv")
    if executable is None:
        raise PluginManagerError("uv executable was not found; install uv and retry")
    return executable


def _run_uv_install(paths: tuple[Path, ...]) -> None:
    command = [_uv(), "pip", "install", "--python", sys.executable, *(str(path) for path in paths)]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as error:
        raise PluginManagerError(f"cannot execute uv pip install: {error}") from error
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout).strip()
        raise PluginManagerError(f"uv pip install failed: {details[-4000:]}")


def _run_uv_uninstall(project_id: str) -> None:
    if project_id in MANAGED_DISTRIBUTIONS:
        raise PluginManagerError(f"refusing to uninstall managed distribution {project_id!r}")
    command = [_uv(), "pip", "uninstall", "--python", sys.executable, project_id]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as error:
        raise PluginManagerError(f"cannot execute uv pip uninstall: {error}") from error
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout).strip()
        raise PluginManagerError(f"uv pip uninstall failed: {details[-4000:]}")


def _atomic_write_text(path: Path, content: str) -> None:
    _atomic_write_bytes(path, content.encode("utf-8"))


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or path.is_symlink():
        raise PluginManagerError(f"refusing to write through a symlink: {path}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


__all__ = [
    "CORDIS_PLUGIN_ENTRY_POINT_GROUP",
    "DEFAULT_PLUGIN_INDEX_URL",
    "InstalledPlugin",
    "PluginArtifact",
    "PluginBundle",
    "PluginFacet",
    "PluginIndex",
    "PluginManager",
    "PluginManagerError",
]
