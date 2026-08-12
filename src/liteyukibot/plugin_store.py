"""Immutable plugin artifacts and runtime generation deployment state."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from .exceptions import LiteyukiError

_IDENTIFIER = re.compile(r"[a-z][a-z0-9-]{0,63}")
_BUNDLE_IDENTIFIER = re.compile(r"[a-z][a-z0-9.-]{0,127}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


class PluginStoreError(LiteyukiError):
    """Raised when a plugin artifact, index, or deployment is unsafe or invalid."""


def _identifier(value: object, subject: str, *, bundle: bool = False) -> str:
    pattern = _BUNDLE_IDENTIFIER if bundle else _IDENTIFIER
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise PluginStoreError(f"{subject} must be a lowercase identifier")
    return value


def _sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise PluginStoreError(f"{subject} must be a lowercase SHA-256 digest")
    return value


def _machine(value: object) -> str:
    if not isinstance(value, str):
        raise PluginStoreError("platform machine must be a lowercase identifier")
    return _identifier(value.lower().replace("_", "-"), "platform machine")


def _strings(value: object, subject: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise PluginStoreError(f"{subject} must be an array of non-empty strings")
    return tuple(value)


def _json_object(value: object, subject: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PluginStoreError(f"{subject} must be an object")
    try:
        json.dumps(value)
    except (TypeError, ValueError) as error:
        raise PluginStoreError(f"{subject} must be JSON-safe") from error
    return {str(key): item for key, item in value.items()}


@dataclass(frozen=True, slots=True)
class PlatformTarget:
    """The concrete Python target for one locally resolved dependency closure."""

    system: str
    machine: str
    python: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "system", _identifier(self.system.lower(), "platform system"))
        object.__setattr__(self, "machine", _machine(self.machine))
        if not re.fullmatch(r"\d+\.\d+", self.python):
            raise PluginStoreError("platform python must use major.minor form")

    @classmethod
    def current(cls) -> PlatformTarget:
        return cls(platform.system(), platform.machine(), f"{sys.version_info.major}.{sys.version_info.minor}")

    def document(self) -> dict[str, str]:
        return {"system": self.system, "machine": self.machine, "python": self.python}


@dataclass(frozen=True, slots=True)
class PlatformConstraint:
    systems: tuple[str, ...] = ()
    machines: tuple[str, ...] = ()
    pythons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "systems",
            tuple(_identifier(item.lower(), "platform system") for item in self.systems),
        )
        object.__setattr__(self, "machines", tuple(_machine(item) for item in self.machines))
        if any(not re.fullmatch(r"\d+\.\d+", item) for item in self.pythons):
            raise PluginStoreError("platform Python constraints must use major.minor form")

    def matches(self, target: PlatformTarget) -> bool:
        return (
            (not self.systems or target.system in self.systems)
            and (not self.machines or target.machine in self.machines)
            and (not self.pythons or target.python in self.pythons)
        )

    def document(self) -> dict[str, list[str]]:
        return {
            "systems": list(self.systems),
            "machines": list(self.machines),
            "pythons": list(self.pythons),
        }


@dataclass(frozen=True, slots=True)
class ArtifactSpec:
    """One HTTPS-distributed immutable input referenced by an index release."""

    url: str
    sha256: str

    def __post_init__(self) -> None:
        parsed = urlsplit(self.url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise PluginStoreError("artifact URL must be credential-free HTTPS")
        object.__setattr__(self, "sha256", _sha256(self.sha256, "artifact"))

    def document(self) -> dict[str, str]:
        return {"url": self.url, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class PluginFacet:
    """One framework-specific installable part of a bundle release."""

    runtime_kind: str
    artifacts: tuple[ArtifactSpec, ...]
    requirements: tuple[str, ...] = ()
    platform: PlatformConstraint = field(default_factory=PlatformConstraint)
    load: dict[str, Any] = field(default_factory=dict)
    capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "runtime_kind", _identifier(self.runtime_kind, "runtime kind"))
        if not self.artifacts:
            raise PluginStoreError("plugin facet requires at least one artifact")
        if len({artifact.sha256 for artifact in self.artifacts}) != len(self.artifacts):
            raise PluginStoreError("plugin facet cannot repeat an artifact")
        if any(not item.strip() for item in self.requirements):
            raise PluginStoreError("plugin facet requirements must not be empty")
        if any(not item.strip() for item in self.capabilities):
            raise PluginStoreError("plugin facet capabilities must not be empty")
        object.__setattr__(self, "load", _json_object(self.load, "plugin facet load plan"))

    def document(self) -> dict[str, Any]:
        return {
            "runtime_kind": self.runtime_kind,
            "artifacts": [item.document() for item in self.artifacts],
            "requirements": list(self.requirements),
            "platform": self.platform.document(),
            "load": self.load,
            "capabilities": list(self.capabilities),
        }


@dataclass(frozen=True, slots=True)
class PluginBundle:
    """A versioned plugin identity with one or more isolated runtime facets."""

    id: str
    version: str
    facets: tuple[PluginFacet, ...]
    dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _identifier(self.id, "plugin bundle id", bundle=True))
        if not self.version.strip():
            raise PluginStoreError("plugin bundle version must not be empty")
        if not self.facets:
            raise PluginStoreError("plugin bundle requires at least one facet")
        if len({facet.runtime_kind for facet in self.facets}) != len(self.facets):
            raise PluginStoreError("plugin bundle cannot repeat a runtime facet")
        object.__setattr__(
            self,
            "dependencies",
            tuple(_identifier(item, "plugin dependency", bundle=True) for item in self.dependencies),
        )

    def facet_for(self, runtime_kind: str, target: PlatformTarget) -> PluginFacet:
        normalized = _identifier(runtime_kind, "runtime kind")
        for facet in self.facets:
            if facet.runtime_kind == normalized:
                if not facet.platform.matches(target):
                    raise PluginStoreError(
                        f"plugin {self.id!r} has no compatible {normalized!r} facet for this platform"
                    )
                return facet
        raise PluginStoreError(f"plugin {self.id!r} has no {normalized!r} facet")

    def document(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "dependencies": list(self.dependencies),
            "facets": [facet.document() for facet in self.facets],
        }


class PluginIndex:
    """Strict reader for a versioned metadata-only plugin index document."""

    def __init__(self, bundles: tuple[PluginBundle, ...]) -> None:
        if len({bundle.id for bundle in bundles}) != len(bundles):
            raise PluginStoreError("plugin index contains duplicate bundle IDs")
        self._bundles = {bundle.id: bundle for bundle in bundles}

    @classmethod
    def parse(cls, document: object) -> PluginIndex:
        value = _json_object(document, "plugin index")
        if value.get("schema") != 1:
            raise PluginStoreError("plugin index schema must be 1")
        raw_bundles = value.get("bundles")
        if not isinstance(raw_bundles, list):
            raise PluginStoreError("plugin index bundles must be an array")
        bundles: list[PluginBundle] = []
        for position, raw_bundle in enumerate(raw_bundles):
            bundle = _json_object(raw_bundle, f"plugin index bundle {position}")
            raw_facets = bundle.get("facets")
            if not isinstance(raw_facets, list):
                raise PluginStoreError("plugin index bundle facets must be an array")
            facets: list[PluginFacet] = []
            for facet_position, raw_facet in enumerate(raw_facets):
                facet = _json_object(raw_facet, f"plugin index facet {facet_position}")
                raw_artifacts = facet.get("artifacts")
                if not isinstance(raw_artifacts, list):
                    raise PluginStoreError("plugin facet artifacts must be an array")
                artifacts = tuple(
                    ArtifactSpec(
                        str(_json_object(raw_artifact, "plugin artifact")["url"]),
                        str(_json_object(raw_artifact, "plugin artifact")["sha256"]),
                    )
                    for raw_artifact in raw_artifacts
                )
                raw_platform = facet.get("platform", {})
                platform_document = _json_object(raw_platform, "plugin facet platform")
                facets.append(
                    PluginFacet(
                        runtime_kind=str(facet["runtime_kind"]),
                        artifacts=artifacts,
                        requirements=_strings(facet.get("requirements", []), "plugin facet requirements"),
                        platform=PlatformConstraint(
                            systems=_strings(platform_document.get("systems", []), "platform systems"),
                            machines=_strings(platform_document.get("machines", []), "platform machines"),
                            pythons=_strings(platform_document.get("pythons", []), "platform Pythons"),
                        ),
                        load=_json_object(facet.get("load", {}), "plugin facet load plan"),
                        capabilities=_strings(facet.get("capabilities", []), "plugin facet capabilities"),
                    )
                )
            bundles.append(
                PluginBundle(
                    id=str(bundle["id"]),
                    version=str(bundle["version"]),
                    facets=tuple(facets),
                    dependencies=_strings(bundle.get("dependencies", []), "plugin dependencies"),
                )
            )
        return cls(tuple(bundles))

    @property
    def digest(self) -> str:
        document = {"schema": 1, "bundles": [bundle.document() for bundle in self.bundles()]}
        return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def bundles(self) -> tuple[PluginBundle, ...]:
        return tuple(self._bundles[key] for key in sorted(self._bundles))

    def require(self, bundle_id: str) -> PluginBundle:
        try:
            return self._bundles[_identifier(bundle_id, "plugin bundle id", bundle=True)]
        except KeyError as error:
            raise PluginStoreError(f"plugin bundle {bundle_id!r} is not in the index") from error


class ArtifactStore:
    """Content-addressed local storage for verified immutable plugin artifacts."""

    def __init__(self, workspace: str | Path) -> None:
        self.root = Path(workspace).resolve() / ".liteyuki" / "plugins" / "store"

    def path_for(self, digest: str) -> Path:
        return self.root / _sha256(digest, "artifact") / "artifact"

    def import_file(self, source: str | Path, expected_digest: str | None = None) -> Path:
        source_path = Path(source).resolve(strict=True)
        if not source_path.is_file() or source_path.is_symlink():
            raise PluginStoreError("plugin artifact source must be a regular file")
        digest = self._digest(source_path)
        if expected_digest is not None and digest != _sha256(expected_digest, "artifact"):
            raise PluginStoreError("plugin artifact digest does not match the index")
        destination = self.path_for(digest)
        if destination.is_file():
            return destination
        temporary = destination.with_name("artifact.tmp")
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(source_path, temporary)
            if self._digest(temporary) != digest:
                raise PluginStoreError("plugin artifact changed while being imported")
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination

    def extract_zip(self, digest: str, destination: str | Path) -> Path:
        artifact = self.path_for(digest)
        if not artifact.is_file():
            raise PluginStoreError(f"plugin artifact {digest!r} is not available")
        target = Path(destination).resolve()
        temporary = target.with_name(target.name + ".tmp")
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.mkdir(parents=True)
        try:
            with zipfile.ZipFile(artifact) as archive:
                for member in archive.infolist():
                    member_path = PurePosixPath(member.filename)
                    is_symlink = member.external_attr >> 16 & 0o170000 == 0o120000
                    if (
                        not member.filename
                        or member_path.is_absolute()
                        or any(part in {"", ".", ".."} for part in member_path.parts)
                        or is_symlink
                    ):
                        raise PluginStoreError(f"plugin archive contains unsafe path: {member.filename!r}")
                    output = temporary.joinpath(*member_path.parts)
                    output.parent.mkdir(parents=True, exist_ok=True)
                    if member.is_dir():
                        output.mkdir(exist_ok=True)
                    else:
                        with archive.open(member) as source, output.open("xb") as handle:
                            shutil.copyfileobj(source, handle)
            if target.exists():
                shutil.rmtree(target)
            temporary.replace(target)
        except BaseException:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        return target

    @staticmethod
    def _digest(path: Path) -> str:
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()


@dataclass(frozen=True, slots=True)
class RuntimeGeneration:
    id: str
    runtime_id: str
    runtime_kind: str
    created_at: str
    target: PlatformTarget
    bundles: tuple[str, ...]
    artifacts: tuple[str, ...]
    load_plan: dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _identifier(self.id, "generation id"))
        object.__setattr__(self, "runtime_id", _identifier(self.runtime_id, "runtime id"))
        object.__setattr__(self, "runtime_kind", _identifier(self.runtime_kind, "runtime kind"))
        if not self.bundles:
            raise PluginStoreError("runtime generation requires at least one bundle")
        object.__setattr__(
            self,
            "bundles",
            tuple(_identifier(item, "plugin bundle id", bundle=True) for item in self.bundles),
        )
        object.__setattr__(self, "artifacts", tuple(_sha256(item, "generation artifact") for item in self.artifacts))
        object.__setattr__(self, "load_plan", _json_object(self.load_plan, "runtime generation load plan"))

    def document(self) -> dict[str, Any]:
        return {
            "schema": 1,
            "id": self.id,
            "runtime_id": self.runtime_id,
            "runtime_kind": self.runtime_kind,
            "created_at": self.created_at,
            "target": self.target.document(),
            "bundles": list(self.bundles),
            "artifacts": list(self.artifacts),
            "load_plan": self.load_plan,
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.document(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Deployment:
    kernel_profile: str | None
    runtime_generations: dict[str, str]
    previous: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kernel_profile is not None:
            object.__setattr__(self, "kernel_profile", _identifier(self.kernel_profile, "kernel profile"))
        object.__setattr__(
            self,
            "runtime_generations",
            {
                _identifier(key, "runtime id"): _identifier(value, "generation id")
                for key, value in self.runtime_generations.items()
            },
        )
        object.__setattr__(
            self,
            "previous",
            {
                _identifier(key, "runtime id"): _identifier(value, "generation id")
                for key, value in self.previous.items()
            },
        )

    def document(self) -> dict[str, Any]:
        return {
            "schema": 2,
            "kernel_profile": self.kernel_profile,
            "runtimes": dict(sorted(self.runtime_generations.items())),
            "previous_runtimes": dict(sorted(self.previous.items())),
        }


class RuntimeGenerationStore:
    """Persist verified generation manifests and atomically switch deployment pointers."""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).resolve()
        self.root = self.workspace / ".liteyuki" / "plugins" / "runtimes"
        self.lock = self.workspace / "liteyuki.lock"

    def path_for(self, runtime_id: str, generation_id: str) -> Path:
        return (
            self.root
            / _identifier(runtime_id, "runtime id")
            / "generations"
            / _identifier(generation_id, "generation id")
        )

    def write(self, generation: RuntimeGeneration) -> Path:
        path = self.path_for(generation.runtime_id, generation.id)
        manifest = path / "manifest.json"
        if manifest.exists():
            if self.read(generation.runtime_id, generation.id).digest != generation.digest:
                raise PluginStoreError("generation ID already belongs to a different manifest")
            return path
        path.mkdir(parents=True)
        self._write_json(manifest, generation.document())
        self._write_json(path / "load-plan.json", generation.load_plan)
        return path

    def read(self, runtime_id: str, generation_id: str) -> RuntimeGeneration:
        path = self.path_for(runtime_id, generation_id) / "manifest.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("schema") != 1:
                raise ValueError("unexpected generation schema")
            target = _json_object(value["target"], "generation target")
            generation = RuntimeGeneration(
                id=str(value["id"]),
                runtime_id=str(value["runtime_id"]),
                runtime_kind=str(value["runtime_kind"]),
                created_at=str(value["created_at"]),
                target=PlatformTarget(str(target["system"]), str(target["machine"]), str(target["python"])),
                bundles=tuple(str(item) for item in value["bundles"]),
                artifacts=tuple(str(item) for item in value["artifacts"]),
                load_plan=_json_object(value["load_plan"], "generation load plan"),
            )
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise PluginStoreError(f"runtime generation {generation_id!r} is not verified") from error
        load_plan = self.path_for(runtime_id, generation_id) / "load-plan.json"
        if generation.runtime_id != runtime_id or not load_plan.is_file():
            raise PluginStoreError(f"runtime generation {generation_id!r} is not verified")
        return generation

    def active(self) -> Deployment:
        if not self.lock.is_file():
            return Deployment(None, {})
        try:
            value = json.loads(self.lock.read_text(encoding="utf-8"))
            if value.get("schema") == 1:
                active = value.get("active")
                return Deployment(active if isinstance(active, str) else None, {})
            if value.get("schema") != 2:
                raise ValueError("unexpected deployment schema")
            return Deployment(
                value.get("kernel_profile"),
                _json_object(value.get("runtimes", {}), "runtime deployment"),
                _json_object(value.get("previous_runtimes", {}), "previous runtime deployment"),
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise PluginStoreError("plugin deployment lock is invalid") from error

    def activate(self, runtime_id: str, generation_id: str) -> Deployment:
        generation = self.read(runtime_id, generation_id)
        current = self.active()
        runtimes = dict(current.runtime_generations)
        previous = dict(current.previous)
        old = runtimes.get(generation.runtime_id)
        runtimes[generation.runtime_id] = generation.id
        if old is not None:
            previous[generation.runtime_id] = old
        deployment = Deployment(current.kernel_profile, runtimes, previous)
        self._write_json(self.lock, deployment.document())
        return deployment

    def rollback(self, runtime_id: str) -> Deployment:
        current = self.active()
        normalized = _identifier(runtime_id, "runtime id")
        try:
            previous = current.previous[normalized]
        except KeyError as error:
            raise PluginStoreError(f"runtime {runtime_id!r} has no rollback generation") from error
        self.read(normalized, previous)
        runtimes = dict(current.runtime_generations)
        old = runtimes.get(normalized)
        runtimes[normalized] = previous
        history = dict(current.previous)
        if old is not None:
            history[normalized] = old
        deployment = Deployment(current.kernel_profile, runtimes, history)
        self._write_json(self.lock, deployment.document())
        return deployment

    @staticmethod
    def new_generation_id() -> str:
        return datetime.now(UTC).strftime("%Y%m%d-%H%M%S-") + hashlib.sha256(os.urandom(16)).hexdigest()[:8]

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)


__all__ = [
    "ArtifactSpec",
    "ArtifactStore",
    "Deployment",
    "PlatformConstraint",
    "PlatformTarget",
    "PluginBundle",
    "PluginFacet",
    "PluginIndex",
    "PluginStoreError",
    "RuntimeGeneration",
    "RuntimeGenerationStore",
]
