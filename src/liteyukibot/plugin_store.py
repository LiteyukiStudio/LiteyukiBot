"""Immutable plugin artifacts and runtime generation deployment state."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import platform
import re
import shutil
import sys
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from license_expression import ExpressionError, get_spdx_licensing

from .exceptions import LiteyukiError

_IDENTIFIER = re.compile(r"[a-z][a-z0-9-]{0,63}")
_BUNDLE_IDENTIFIER = re.compile(r"[a-z][a-z0-9.-]{0,127}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_MAX_ARTIFACT_BYTES = 256 * 1024 * 1024
_MAX_BUNDLES = 10_000
_MAX_RESOLVED_BUNDLES = 128
_MAX_GENERATION_INPUTS = 256
_MAX_GENERATION_INPUT_BYTES = 1024 * 1024 * 1024
_MAX_LOAD_PLAN_BYTES = 64 * 1024
_MAX_ARCHIVE_MEMBERS = 10_000
_MAX_ARCHIVE_MEMBER_BYTES = 256 * 1024 * 1024
_MAX_ARCHIVE_EXTRACTED_BYTES = 1024 * 1024 * 1024
PLUGIN_GENERATION_ENV = "LITEYUKI_PLUGIN_GENERATION"
_ALLOWED_LICENSE_REFS = frozenset({"LicenseRef-LSO-Common-1.4", "LicenseRef-LSO-Commercial-1.4"})


class PluginStoreError(LiteyukiError):
    """Raised when a plugin artifact, index, or deployment is unsafe or invalid."""


@lru_cache(maxsize=1)
def _spdx_licensing() -> Any:
    """Return the immutable SPDX catalog without rebuilding its symbol table.

    Returns:
        The `license_expression` SPDX licensing catalog.

    Notes:
        Catalog construction is expensive and immutable, so one process-local
        instance is shared by the separately bounded expression cache.
    """
    return get_spdx_licensing()  # type: ignore[no-untyped-call]


@lru_cache(maxsize=256)
def _validate_license_expression(expression: str) -> None:
    """Validate one SPDX expression with a bounded process-local cache.

    Args:
        expression: Trimmed schema-2 license expression.

    Returns:
        None when syntax and identifiers are acceptable.

    Notes:
        Constructing the SPDX catalog is comparatively expensive. The bounded
        cache prevents repeated index entries from rebuilding it while avoiding
        unbounded retention of publisher-controlled expressions.
    """
    licensing = _spdx_licensing()
    try:
        licensing.parse(expression, validate=False, strict=True)
    except ExpressionError as error:
        raise PluginStoreError("plugin license expression has invalid SPDX syntax") from error
    validation = licensing.validate(expression, strict=True)
    invalid_symbols = tuple(str(symbol) for symbol in validation.invalid_symbols)
    if any(symbol not in _ALLOWED_LICENSE_REFS for symbol in invalid_symbols):
        raise PluginStoreError("plugin license expression contains an unknown SPDX identifier")


def _archive_member_path(member: zipfile.ZipInfo) -> PurePosixPath:
    """Validate and normalize one ZIP member's payload-relative path.

    Args:
        member: ZIP directory entry supplied by the verified archive.

    Returns:
        Safe relative path suitable for joining below the extraction root.

    Notes:
        Absolute paths, empty/dot components, traversal, symbolic links, and
        oversized members are rejected before any member is written.

    Security:
        ZIP metadata controls destination paths and claimed output size. This
        validator is retained because plugins are distributed as archives; it
        prevents traversal, link escape, and per-member decompression abuse.
        See `docs/security/trusted-boundaries.md#plugin-artifacts-and-native-code`.
    """
    path = PurePosixPath(member.filename)
    is_symlink = member.external_attr >> 16 & 0o170000 == 0o120000
    if (
        not member.filename
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or is_symlink
    ):
        raise PluginStoreError(f"plugin archive contains unsafe path: {member.filename!r}")
    if member.file_size > _MAX_ARCHIVE_MEMBER_BYTES:
        raise PluginStoreError(f"plugin archive member is too large: {member.filename!r}")
    return path


def _validated_archive_members(archive: zipfile.ZipFile) -> tuple[tuple[zipfile.ZipInfo, PurePosixPath], ...]:
    """Validate an entire ZIP directory before extraction starts.

    Args:
        archive: Open plugin archive whose central directory is inspected.

    Returns:
        Members paired with normalized, safe relative paths.

    Notes:
        Member count and total declared expanded bytes are checked before the
        first filesystem write, avoiding partially extracted invalid archives.

    Security:
        Compressed input can expand into excessive files or bytes. The archive
        capability is retained for installable plugins, bounded by count,
        member size, total size, and path checks. See
        `docs/security/trusted-boundaries.md#plugin-artifacts-and-native-code`.
    """
    members = archive.infolist()
    if len(members) > _MAX_ARCHIVE_MEMBERS:
        raise PluginStoreError("plugin archive contains too many members")
    validated = tuple((member, _archive_member_path(member)) for member in members)
    if sum(member.file_size for member, _path in validated) > _MAX_ARCHIVE_EXTRACTED_BYTES:
        raise PluginStoreError("plugin archive exceeds the extracted size limit")
    return validated


def _identifier(value: object, subject: str, *, bundle: bool = False) -> str:
    """Implement the identifier operation for the component.

    Args:
        value: Value to validate, transform, or store.
        subject: The subject value used by the operation.
        bundle: The bundle value used by the operation.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_identifier`. It delegates to `fullmatch` while keeping
        intermediate state local to the owning operation.
    """
    pattern = _BUNDLE_IDENTIFIER if bundle else _IDENTIFIER
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise PluginStoreError(f"{subject} must be a lowercase identifier")
    return value


def _sha256(value: object, subject: str) -> str:
    """Implement the sha256 operation for the component.

    Args:
        value: Value to validate, transform, or store.
        subject: The subject value used by the operation.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_sha256`. It delegates to `fullmatch` while keeping
        intermediate state local to the owning operation.
    """
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise PluginStoreError(f"{subject} must be a lowercase SHA-256 digest")
    return value


def _machine(value: object) -> str:
    """Implement the machine operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_machine`. It delegates to `_identifier`, `replace`, `lower`
        while keeping intermediate state local to the owning operation.
    """
    if not isinstance(value, str):
        raise PluginStoreError("platform machine must be a lowercase identifier")
    return _identifier(value.lower().replace("_", "-"), "platform machine")


def _strings(value: object, subject: str) -> tuple[str, ...]:
    """Implement the strings operation for the component.

    Args:
        value: Value to validate, transform, or store.
        subject: The subject value used by the operation.

    Returns:
        The `tuple[str, ...]` result produced by the operation.

    Notes:
        Internal implementation detail for `_strings`. It delegates to `any`, `strip` while keeping
        intermediate state local to the owning operation.
    """
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise PluginStoreError(f"{subject} must be an array of non-empty strings")
    return tuple(value)


def _bounded_string(value: object, subject: str, maximum: int) -> str:
    """Validate one trimmed, non-empty, length-bounded string.

    Args:
        value: Candidate value supplied by plugin index metadata.
        subject: Human-readable field name used in validation errors.
        maximum: Maximum accepted Unicode code-point count.

    Returns:
        The validated string without modifying its contents.

    Notes:
        Validation rejects implicit trimming so canonical index serialization
        covers the exact publisher-supplied value.
    """
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > maximum:
        raise PluginStoreError(f"{subject} must be a trimmed string of at most {maximum} characters")
    return value


def _https_url(value: object, subject: str) -> str:
    """Validate a public, credential-free HTTPS URL from schema-2 metadata.

    Args:
        value: Candidate URL value.
        subject: Human-readable field name used in validation errors.

    Returns:
        The validated URL.

    Notes:
        This validates metadata before fetch. Redirect destinations are checked
        again by the artifact download path.

    Security:
        Literal loopback, private, link-local, and reserved addresses are
        rejected. DNS can still change after validation, so artifact redirects
        are validated independently at fetch time.
    """
    text = _bounded_string(value, subject, 2048)
    parsed = urlsplit(text)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise PluginStoreError(f"{subject} must be credential-free HTTPS")
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith((".localhost", ".local")):
        raise PluginStoreError(f"{subject} must not target a local hostname")
    try:
        address = ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        return text
    if not address.is_global:
        raise PluginStoreError(f"{subject} must not target a private or reserved address")
    return text


class _PublicRedirectHandler(HTTPRedirectHandler):
    """Reject unsafe redirect destinations before urllib opens them."""

    def __init__(self, subject: str) -> None:
        super().__init__()
        self.subject = subject

    def redirect_request(
        self,
        request: Any,
        response: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> Request | None:
        _https_url(new_url, self.subject)
        return super().redirect_request(request, response, code, message, headers, new_url)


def _open_public_url(request: Request, *, timeout: float, subject: str) -> Any:
    """Open one validated URL while checking every redirect hop."""

    return build_opener(_PublicRedirectHandler(subject)).open(request, timeout=timeout)


def _exact_object(value: object, subject: str, required: set[str], optional: set[str] | None = None) -> dict[str, Any]:
    """Validate an object whose schema does not permit unknown properties.

    Args:
        value: Candidate JSON object.
        subject: Human-readable object name used in validation errors.
        required: Required property names.
        optional: Optional property names.

    Returns:
        The validated JSON-safe object.

    Notes:
        Exact-key validation prevents unknown schema-2 metadata from escaping
        canonical digest coverage.
    """
    document = _json_object(value, subject)
    allowed = required | (optional or set())
    if not required.issubset(document) or set(document) - allowed:
        raise PluginStoreError(f"{subject} has missing or unknown fields")
    return document


def _json_object(value: object, subject: str) -> dict[str, Any]:
    """Implement the json object operation for the component.

    Args:
        value: Value to validate, transform, or store.
        subject: The subject value used by the operation.

    Returns:
        The `dict[str, Any]` result produced by the operation.

    Notes:
        Internal implementation detail for `_json_object`. It delegates to `dumps`, `items` while
        keeping intermediate state local to the owning operation.
    """
    if not isinstance(value, dict):
        raise PluginStoreError(f"{subject} must be an object")
    try:
        json.dumps(value)
    except (TypeError, ValueError) as error:
        raise PluginStoreError(f"{subject} must be JSON-safe") from error
    return {str(key): item for key, item in value.items()}


def _artifact_specs(value: list[object], subject: str, *, schema: int = 1) -> tuple[ArtifactSpec, ...]:
    """Implement the artifact specs operation for the component.

    Args:
        value: Value to validate, transform, or store.
        subject: The subject value used by the operation.
        schema: Parent index schema controlling exact keys and byte metadata.

    Returns:
        The `tuple[ArtifactSpec, ...]` result produced by the operation.

    Notes:
        Internal implementation detail for `_artifact_specs`. It delegates to `_json_object` while
        keeping intermediate state local to the owning operation.
    """
    specifications: list[ArtifactSpec] = []
    for raw_artifact in value:
        artifact = (
            _exact_object(raw_artifact, subject, {"url", "sha256", "bytes"})
            if schema == 2
            else _json_object(raw_artifact, subject)
        )
        specifications.append(
            ArtifactSpec(
                artifact["url"],
                artifact["sha256"],
                artifact.get("bytes") if schema == 2 else None,
            )
        )
    return tuple(specifications)


@dataclass(frozen=True, slots=True)
class PlatformTarget:
    """The concrete Python target for one locally resolved dependency closure."""

    system: str
    machine: str
    python: str

    def __post_init__(self) -> None:
        """Validate and normalize the platform target after initialization.

        Returns:
            None.
        """
        object.__setattr__(self, "system", _identifier(self.system.lower(), "platform system"))
        object.__setattr__(self, "machine", _machine(self.machine))
        if not re.fullmatch(r"\d+\.\d+", self.python):
            raise PluginStoreError("platform python must use major.minor form")

    @classmethod
    def current(cls) -> PlatformTarget:
        """Implement the current operation for the platform target.

        Returns:
            The `PlatformTarget` result produced by the operation.
        """
        return cls(platform.system(), platform.machine(), f"{sys.version_info.major}.{sys.version_info.minor}")

    def document(self) -> dict[str, str]:
        """Return the serialized document for the platform target operation.

        Returns:
            The `dict[str, str]` result produced by the operation.
        """
        return {"system": self.system, "machine": self.machine, "python": self.python}


@dataclass(frozen=True, slots=True)
class PlatformConstraint:
    """Represent the platform constraint contract."""
    systems: tuple[str, ...] = ()
    machines: tuple[str, ...] = ()
    pythons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate and normalize the platform constraint after initialization.

        Returns:
            None.
        """
        object.__setattr__(
            self,
            "systems",
            tuple(_identifier(item.lower(), "platform system") for item in self.systems),
        )
        object.__setattr__(self, "machines", tuple(_machine(item) for item in self.machines))
        if any(not re.fullmatch(r"\d+\.\d+", item) for item in self.pythons):
            raise PluginStoreError("platform Python constraints must use major.minor form")

    def matches(self, target: PlatformTarget) -> bool:
        """Implement the matches operation for the platform constraint.

        Args:
            target: Target value or location for the operation.

        Returns:
            Whether the requested condition is satisfied.
        """
        return (
            (not self.systems or target.system in self.systems)
            and (not self.machines or target.machine in self.machines)
            and (not self.pythons or target.python in self.pythons)
        )

    def document(self) -> dict[str, list[str]]:
        """Return the serialized document for the platform constraint operation.

        Returns:
            The `dict[str, list[str]]` result produced by the operation.
        """
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
    bytes: int | None = None

    def __post_init__(self) -> None:
        """Validate and normalize the artifact spec after initialization.

        Returns:
            None.
        """
        _https_url(self.url, "artifact URL")
        object.__setattr__(self, "sha256", _sha256(self.sha256, "artifact"))
        if self.bytes is not None and (
            isinstance(self.bytes, bool)
            or not isinstance(self.bytes, int)
            or not 1 <= self.bytes <= _MAX_ARTIFACT_BYTES
        ):
            raise PluginStoreError("artifact byte size is outside the allowed range")

    def document(self) -> dict[str, str | int]:
        """Return the serialized document for the artifact spec operation.

        Returns:
            The JSON-safe artifact declaration. Schema-1 declarations omit
            `bytes`; schema-2 declarations retain the exact expected length.
        """
        return {
            "url": self.url,
            "sha256": self.sha256,
            **({"bytes": self.bytes} if self.bytes is not None else {}),
        }


@dataclass(frozen=True, slots=True)
class PluginPublisher:
    """Verified publisher identity displayed for one schema-2 plugin release."""

    id: str
    name: str
    url: str

    def __post_init__(self) -> None:
        """Validate publisher identity fields.

        Returns:
            None.
        """
        object.__setattr__(self, "id", _identifier(self.id, "plugin publisher ID"))
        _bounded_string(self.name, "plugin publisher name", 80)
        _https_url(self.url, "plugin publisher URL")

    def document(self) -> dict[str, str]:
        """Return the canonical publisher document.

        Returns:
            Publisher ID, display name, and public HTTPS URL.
        """
        return {"id": self.id, "name": self.name, "url": self.url}


@dataclass(frozen=True, slots=True)
class PluginLicense:
    """SPDX-compatible license declaration for one schema-2 plugin release."""

    expression: str
    url: str | None = None

    def __post_init__(self) -> None:
        """Validate the expression syntax and custom-license evidence URL.

        Returns:
            None.
        """
        expression = _bounded_string(self.expression, "plugin license expression", 128)
        _validate_license_expression(expression)
        if "LicenseRef-" in expression and self.url is None:
            raise PluginStoreError("plugin custom license requires a URL")
        if self.url is not None:
            _https_url(self.url, "plugin license URL")

    def document(self) -> dict[str, str]:
        """Return the canonical license document.

        Returns:
            License expression and optional custom-license evidence URL.
        """
        return {"expression": self.expression, **({"url": self.url} if self.url is not None else {})}


@dataclass(frozen=True, slots=True)
class PluginFacet:
    """One framework-specific installable part of a bundle release."""

    runtime_kind: str
    artifacts: tuple[ArtifactSpec, ...]
    wheels: tuple[ArtifactSpec, ...] = ()
    platform: PlatformConstraint = field(default_factory=PlatformConstraint)
    load: dict[str, Any] = field(default_factory=dict)
    capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate and normalize the plugin facet after initialization.

        Returns:
            None.
        """
        object.__setattr__(self, "runtime_kind", _identifier(self.runtime_kind, "runtime kind"))
        if not self.artifacts and not self.wheels:
            raise PluginStoreError("plugin facet requires at least one artifact or wheel")
        inputs = (*self.artifacts, *self.wheels)
        if len({artifact.sha256 for artifact in inputs}) != len(inputs):
            raise PluginStoreError("plugin facet cannot repeat an artifact or wheel")
        if any(not item.strip() for item in self.capabilities):
            raise PluginStoreError("plugin facet capabilities must not be empty")
        object.__setattr__(self, "load", _json_object(self.load, "plugin facet load plan"))

    def document(self) -> dict[str, Any]:
        """Return the serialized document for the plugin facet operation.

        Returns:
            The `dict[str, Any]` result produced by the operation.
        """
        return {
            "runtime_kind": self.runtime_kind,
            "artifacts": [item.document() for item in self.artifacts],
            "wheels": [item.document() for item in self.wheels],
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
    display_name: str | None = None
    summary: str | None = None
    publisher: PluginPublisher | None = None
    license: PluginLicense | None = None
    repository: str | None = None
    homepage: str | None = None
    status: str = "active"
    yanked_reason: str | None = None

    def __post_init__(self) -> None:
        """Validate and normalize the plugin bundle after initialization.

        Returns:
            None.
        """
        object.__setattr__(self, "id", _identifier(self.id, "plugin bundle id", bundle=True))
        _bounded_string(self.version, "plugin bundle version", 64)
        if not self.facets:
            raise PluginStoreError("plugin bundle requires at least one facet")
        if len({facet.runtime_kind for facet in self.facets}) != len(self.facets):
            raise PluginStoreError("plugin bundle cannot repeat a runtime facet")
        object.__setattr__(
            self,
            "dependencies",
            tuple(_identifier(item, "plugin dependency", bundle=True) for item in self.dependencies),
        )
        metadata = (self.display_name, self.summary, self.publisher, self.license, self.repository)
        if any(item is not None for item in metadata) and not all(item is not None for item in metadata):
            raise PluginStoreError("schema-2 plugin bundle metadata must be complete")
        if self.display_name is not None:
            _bounded_string(self.display_name, "plugin display name", 120)
            _bounded_string(self.summary, "plugin summary", 240)
            _https_url(self.repository, "plugin repository")
            if self.homepage is not None:
                _https_url(self.homepage, "plugin homepage")
            if self.status not in {"active", "yanked"}:
                raise PluginStoreError("plugin status must be active or yanked")
            if self.status == "yanked":
                _bounded_string(self.yanked_reason, "plugin yanked reason", 240)
            elif self.yanked_reason is not None:
                raise PluginStoreError("active plugin release cannot have a yanked reason")
        elif self.homepage is not None or self.status != "active" or self.yanked_reason is not None:
            raise PluginStoreError("schema-1 plugin bundle cannot contain schema-2 metadata")

    def facet_for(self, runtime_kind: str, target: PlatformTarget) -> PluginFacet:
        """Implement the facet for operation for the plugin bundle.

        Args:
            runtime_kind: The runtime kind value used by the operation.
            target: Target value or location for the operation.

        Returns:
            The `PluginFacet` result produced by the operation.
        """
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
        """Return the serialized document for the plugin bundle operation.

        Returns:
            The `dict[str, Any]` result produced by the operation.
        """
        document: dict[str, Any] = {
            "id": self.id,
            "version": self.version,
            "dependencies": list(self.dependencies),
            "facets": [facet.document() for facet in self.facets],
        }
        if self.display_name is not None:
            if self.publisher is None or self.license is None or self.repository is None or self.summary is None:
                raise AssertionError("validated schema-2 metadata is incomplete")
            document.update(
                {
                    "display_name": self.display_name,
                    "summary": self.summary,
                    "publisher": self.publisher.document(),
                    "license": self.license.document(),
                    "repository": self.repository,
                    "status": self.status,
                }
            )
            if self.homepage is not None:
                document["homepage"] = self.homepage
            if self.yanked_reason is not None:
                document["yanked_reason"] = self.yanked_reason
        return document


def _parse_platform(value: object, schema: int) -> PlatformConstraint:
    """Parse version-aware platform constraints for one plugin facet.

    Args:
        value: Parsed platform object.
        schema: Parent plugin index schema version.

    Returns:
        Validated immutable platform constraints.

    Notes:
        Schema 1 preserves the permissive legacy shape. Schema 2 requires exact
        keys, bounded unique values, and deterministic tuple ordering.
    """
    document = (
        _exact_object(value, "plugin facet platform", {"systems", "machines", "pythons"})
        if schema == 2
        else _json_object(value, "plugin facet platform")
    )
    systems = _strings(document.get("systems", []), "platform systems")
    machines = _strings(document.get("machines", []), "platform machines")
    pythons = _strings(document.get("pythons", []), "platform Pythons")
    if schema == 2:
        bounded = ((systems, 16), (machines, 32), (pythons, 16))
        if any(len(items) > maximum or len(set(items)) != len(items) for items, maximum in bounded):
            raise PluginStoreError("plugin facet platform constraints exceed the allowed unique entries")
    return PlatformConstraint(systems=systems, machines=machines, pythons=pythons)


def _validate_schema_two_facet(
    raw_artifacts: list[object],
    raw_wheels: list[object],
    load: dict[str, Any],
    capabilities: tuple[str, ...],
) -> None:
    """Apply schema-2-only resource and uniqueness bounds to one facet.

    Args:
        raw_artifacts: Archive declarations.
        raw_wheels: Wheel declarations.
        load: JSON-safe framework load plan.
        capabilities: Declared capability identifiers.

    Returns:
        None.

    Notes:
        Aggregate per-bundle limits are checked after facets are parsed; this
        helper enforces the independent per-facet input and load-plan bounds.
    """
    if not 1 <= len(raw_artifacts) + len(raw_wheels) <= _MAX_GENERATION_INPUTS:
        raise PluginStoreError("plugin facet input count is outside the allowed range")
    if len(json.dumps(load, sort_keys=True, separators=(",", ":")).encode()) > _MAX_LOAD_PLAN_BYTES:
        raise PluginStoreError("plugin facet load plan is too large")
    if (
        len(capabilities) > 128
        or len(set(capabilities)) != len(capabilities)
        or any(item != item.strip() or len(item) > 128 for item in capabilities)
    ):
        raise PluginStoreError("plugin facet capabilities exceed the allowed unique entries")


def _parse_facet(raw_facet: object, position: int, schema: int) -> PluginFacet:
    """Parse one version-aware facet.

    Args:
        raw_facet: Parsed JSON value for the facet.
        position: Facet offset used in validation diagnostics.
        schema: Parent plugin index schema version.

    Returns:
        A validated immutable plugin facet.

    Notes:
        Parsing selects the schema-1 compatibility path or the exact schema-2
        path before constructing the shared immutable facet representation.
    """
    subject = f"plugin index facet {position}"
    facet = (
        _exact_object(
            raw_facet,
            subject,
            {"runtime_kind", "artifacts", "wheels", "platform", "load", "capabilities"},
        )
        if schema == 2
        else _json_object(raw_facet, subject)
    )
    if "requirements" in facet:
        raise PluginStoreError("plugin facet requirements are unsupported; declare hash-verified wheels")
    raw_artifacts = facet.get("artifacts")
    raw_wheels = facet.get("wheels", [])
    if not isinstance(raw_artifacts, list) or not isinstance(raw_wheels, list):
        raise PluginStoreError("plugin facet artifacts and wheels must be arrays")
    load = _json_object(facet.get("load", {}), "plugin facet load plan")
    capabilities = _strings(facet.get("capabilities", []), "plugin facet capabilities")
    if schema == 2:
        _validate_schema_two_facet(raw_artifacts, raw_wheels, load, capabilities)
    return PluginFacet(
        runtime_kind=facet["runtime_kind"],
        artifacts=_artifact_specs(raw_artifacts, "plugin artifact", schema=schema),
        wheels=_artifact_specs(raw_wheels, "plugin wheel", schema=schema),
        platform=_parse_platform(facet.get("platform", {}), schema),
        load=load,
        capabilities=capabilities,
    )


def _schema_two_bundle(
    bundle: dict[str, Any],
    facets: tuple[PluginFacet, ...],
    dependencies: tuple[str, ...],
) -> PluginBundle:
    """Build one schema-2 bundle after validating its discovery metadata.

    Args:
        bundle: Exact-key JSON bundle object.
        facets: Parsed framework facets.
        dependencies: Parsed dependency bundle IDs.

    Returns:
        A complete schema-2 plugin bundle.

    Notes:
        Facet inputs are already individually validated. This step enforces the
        release-wide budget and attaches digest-covered discovery metadata.
    """
    if len(dependencies) > 64 or len(set(dependencies)) != len(dependencies):
        raise PluginStoreError("plugin dependencies exceed the allowed unique entries")
    inputs = tuple(artifact for facet in facets for artifact in (*facet.artifacts, *facet.wheels))
    input_bytes = sum(artifact.bytes or 0 for artifact in inputs)
    if len(inputs) > _MAX_GENERATION_INPUTS or input_bytes > _MAX_GENERATION_INPUT_BYTES:
        raise PluginStoreError("plugin bundle exceeds the generation input budget")
    publisher = _exact_object(bundle["publisher"], "plugin publisher", {"id", "name", "url"})
    license_value = _exact_object(bundle["license"], "plugin license", {"expression"}, {"url"})
    return PluginBundle(
        id=bundle["id"],
        version=bundle["version"],
        facets=facets,
        dependencies=dependencies,
        display_name=bundle["display_name"],
        summary=bundle["summary"],
        publisher=PluginPublisher(publisher["id"], publisher["name"], publisher["url"]),
        license=PluginLicense(
            license_value["expression"],
            license_value["url"] if "url" in license_value else None,
        ),
        repository=bundle["repository"],
        homepage=bundle["homepage"] if "homepage" in bundle else None,
        status=bundle["status"],
        yanked_reason=bundle["yanked_reason"] if "yanked_reason" in bundle else None,
    )


def _parse_bundle(raw_bundle: object, position: int, schema: int) -> PluginBundle:
    """Parse one bundle under its parent index schema.

    Args:
        raw_bundle: Parsed JSON value for the bundle.
        position: Bundle offset used in validation diagnostics.
        schema: Parent plugin index schema version.

    Returns:
        A validated immutable plugin bundle.

    Notes:
        Schema 1 retains its historical minimal representation. Schema 2
        requires exact discovery fields and delegates their aggregate checks to
        `_schema_two_bundle`.
    """
    subject = f"plugin index bundle {position}"
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
    bundle = (
        _exact_object(raw_bundle, subject, required, {"homepage", "yanked_reason"})
        if schema == 2
        else _json_object(raw_bundle, subject)
    )
    raw_facets = bundle.get("facets")
    if not isinstance(raw_facets, list) or (schema == 2 and not 1 <= len(raw_facets) <= 16):
        raise PluginStoreError("plugin index bundle facets must be an array")
    facets = tuple(_parse_facet(value, offset, schema) for offset, value in enumerate(raw_facets))
    dependencies = _strings(bundle.get("dependencies", []), "plugin dependencies")
    if schema == 2:
        return _schema_two_bundle(bundle, facets, dependencies)
    return PluginBundle(
        id=str(bundle["id"]),
        version=str(bundle["version"]),
        facets=facets,
        dependencies=dependencies,
    )


class PluginIndex:
    """Strict reader for a versioned metadata-only plugin index document."""

    def __init__(self, bundles: tuple[PluginBundle, ...], schema: int | None = None) -> None:
        """Initialize the plugin index.

        Args:
            bundles: Validated plugin bundle releases.
            schema: Explicit index schema, or inferred from bundle metadata.

        Returns:
            None.
        """
        if len({bundle.id for bundle in bundles}) != len(bundles):
            raise PluginStoreError("plugin index contains duplicate bundle IDs")
        inferred = 2 if any(bundle.display_name is not None for bundle in bundles) else 1
        self.schema = inferred if schema is None else schema
        if self.schema not in {1, 2}:
            raise PluginStoreError("plugin index schema must be 1 or 2")
        if any((bundle.display_name is not None) != (self.schema == 2) for bundle in bundles):
            raise PluginStoreError("plugin bundle metadata does not match the index schema")
        self._bundles = {bundle.id: bundle for bundle in bundles}

    @classmethod
    def parse(cls, document: object) -> PluginIndex:
        """Parse the plugin index operation.

        Args:
            document: The document value used by the operation.

        Returns:
            The `PluginIndex` result produced by the operation.
        """
        value = _json_object(document, "plugin index")
        schema = value.get("schema")
        if isinstance(schema, bool) or schema not in {1, 2}:
            raise PluginStoreError("plugin index schema must be 1 or 2")
        if schema == 2:
            value = _exact_object(value, "plugin index", {"schema", "bundles"})
        raw_bundles = value.get("bundles")
        if not isinstance(raw_bundles, list) or (schema == 2 and len(raw_bundles) > _MAX_BUNDLES):
            raise PluginStoreError("plugin index bundles must be an array")
        bundles = tuple(_parse_bundle(raw_bundle, position, schema) for position, raw_bundle in enumerate(raw_bundles))
        index = cls(bundles, schema=schema)
        if schema == 2:
            for parsed_bundle in index.bundles():
                _validate_dependency_closure(index, parsed_bundle.id)
        return index

    @property
    def digest(self) -> str:
        """Return the plugin index's digest.

        Returns:
            The `str` result produced by the operation.
        """
        document = {"schema": self.schema, "bundles": [bundle.document() for bundle in self.bundles()]}
        return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def bundles(self) -> tuple[PluginBundle, ...]:
        """Implement the bundles operation for the plugin index.

        Returns:
            The `tuple[PluginBundle, ...]` result produced by the operation.
        """
        return tuple(self._bundles[key] for key in sorted(self._bundles))

    def search(self, query: str = "") -> tuple[PluginBundle, ...]:
        """Search bundles by identity and human-facing schema-2 metadata.

        Args:
            query: Case-insensitive text. Empty or whitespace-only text matches
                every bundle, including visible yanked releases.

        Returns:
            Matching bundles in deterministic ID order.
        """
        needle = query.strip().casefold()
        matches: list[PluginBundle] = []
        for bundle in self.bundles():
            publisher = bundle.publisher
            values = (
                bundle.id,
                bundle.display_name or "",
                bundle.summary or "",
                publisher.id if publisher is not None else "",
                publisher.name if publisher is not None else "",
            )
            if not needle or needle in "\n".join(values).casefold():
                matches.append(bundle)
        return tuple(matches)

    def require(self, bundle_id: str) -> PluginBundle:
        """Return the plugin index operation, failing when it is unavailable.

        Args:
            bundle_id: Stable identifier for the bundle.

        Returns:
            The requested `PluginBundle` value.
        """
        try:
            return self._bundles[_identifier(bundle_id, "plugin bundle id", bundle=True)]
        except KeyError as error:
            raise PluginStoreError(f"plugin bundle {bundle_id!r} is not in the index") from error


def _validate_dependency_closure(index: PluginIndex, root: str) -> None:
    """Validate one schema-2 dependency closure for cycles and size.

    Args:
        index: Parsed plugin index containing every referenced dependency.
        root: Bundle ID whose transitive closure is validated.

    Returns:
        None.

    Notes:
        A depth-first walk uses separate visiting and visited sets to reject
        cycles and cap every root's transitive closure.
    """
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(bundle_id: str) -> None:
        """Visit one dependency and accumulate its validated transitive closure.

        Args:
            bundle_id: Bundle identifier at the current traversal position.

        Returns:
            None.

        Notes:
            `visiting` identifies cycles while `visited` prevents repeated work
            and supplies the closure-size counter.
        """
        if bundle_id in visited:
            return
        if bundle_id in visiting:
            raise PluginStoreError(f"plugin dependency cycle includes {bundle_id!r}")
        visiting.add(bundle_id)
        for dependency in index.require(bundle_id).dependencies:
            visit(dependency)
        visiting.remove(bundle_id)
        visited.add(bundle_id)
        if len(visited) > _MAX_RESOLVED_BUNDLES:
            raise PluginStoreError(f"plugin dependency closure exceeds {_MAX_RESOLVED_BUNDLES} bundles")

    visit(root)


class ArtifactStore:
    """Content-addressed local storage for verified immutable plugin artifacts."""

    def __init__(self, workspace: str | Path) -> None:
        """Initialize the artifact store.

        Args:
            workspace: The workspace value used by the operation.

        Returns:
            None.
        """
        self.root = Path(workspace).resolve() / ".liteyuki" / "plugins" / "store"

    def path_for(self, digest: str) -> Path:
        """Implement the path for operation for the artifact store.

        Args:
            digest: Expected lowercase SHA-256 digest.

        Returns:
            The `Path` result produced by the operation.
        """
        return self.root / _sha256(digest, "artifact") / "artifact"

    def import_file(
        self,
        source: str | Path,
        expected_digest: str | None = None,
        expected_bytes: int | None = None,
    ) -> Path:
        """Import a regular file into immutable content-addressed storage.

        Args:
            source: Existing regular file to copy into the artifact store.
            expected_digest: Optional index digest that the source must match.
            expected_bytes: Optional exact byte length declared by schema 2.

        Returns:
            Stable cache path for the verified artifact bytes.

        Security:
            Source files may change while copied. The digest is calculated
            before and after copying; links and non-regular files are rejected.
            Content-addressed import remains necessary for local and downloaded
            plugin artifacts.
        """
        source_path = Path(source)
        if source_path.is_symlink():
            raise PluginStoreError("plugin artifact source must be a regular file")
        source_path = source_path.resolve(strict=True)
        if not source_path.is_file():
            raise PluginStoreError("plugin artifact source must be a regular file")
        source_size = source_path.stat().st_size
        if source_size > _MAX_ARTIFACT_BYTES:
            raise PluginStoreError("plugin artifact exceeds the 256 MiB limit")
        if expected_bytes is not None and source_size != expected_bytes:
            raise PluginStoreError("plugin artifact byte size does not match the index")
        digest = self._digest(source_path)
        if expected_digest is not None and digest != _sha256(expected_digest, "artifact"):
            raise PluginStoreError("plugin artifact digest does not match the index")
        self._validate_root()
        destination = self.path_for(digest)
        if destination.is_symlink() or (destination.exists() and not destination.is_file()):
            raise PluginStoreError("plugin artifact destination is unsafe")
        if destination.is_file():
            if self._digest(destination) != digest:
                raise PluginStoreError("cached plugin artifact is corrupt")
            if expected_bytes is not None and destination.stat().st_size != expected_bytes:
                raise PluginStoreError("cached plugin artifact byte size does not match the index")
            return destination
        if destination.exists():
            raise PluginStoreError("plugin artifact destination is unsafe")
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

    def fetch(self, artifact: ArtifactSpec) -> Path:
        """Download one declared artifact once, retaining only its verified bytes.

        Args:
            artifact: HTTPS URL and mandatory SHA-256 digest declared by the index.

        Returns:
            Stable cache path containing exactly the verified bytes.

        Security:
            Remote content and redirects are untrusted. Fetching is retained for
            plugin distribution, but redirects must remain credential-free HTTPS,
            downloads are capped at 256 MiB, and bytes are activated only after
            digest verification. See
            `docs/security/trusted-boundaries.md#plugin-artifacts-and-native-code`.
        """

        self._validate_root()
        destination = self.path_for(artifact.sha256)
        if destination.is_symlink() or (destination.exists() and not destination.is_file()):
            raise PluginStoreError(f"cached plugin artifact {artifact.sha256!r} is unsafe")
        if destination.is_file():
            if self._digest(destination) != artifact.sha256:
                raise PluginStoreError(f"cached plugin artifact {artifact.sha256!r} is corrupt")
            if destination.stat().st_size > _MAX_ARTIFACT_BYTES:
                raise PluginStoreError(f"cached plugin artifact {artifact.sha256!r} exceeds the 256 MiB limit")
            if artifact.bytes is not None and destination.stat().st_size != artifact.bytes:
                raise PluginStoreError(f"cached plugin artifact {artifact.sha256!r} has the wrong byte size")
            return destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name("download.tmp")
        try:
            request = Request(artifact.url, headers={"User-Agent": "liteyukibot-v7-plugin-store"})
            with _open_public_url(
                request,
                timeout=30,
                subject="plugin artifact redirect",
            ) as response:
                try:
                    _https_url(response.geturl(), "plugin artifact redirect")
                except PluginStoreError as error:
                    raise PluginStoreError(
                        "plugin artifact redirect must remain public credential-free HTTPS"
                    ) from error
                with temporary.open("xb") as handle:
                    received = 0
                    while chunk := response.read(1024 * 1024):
                        received += len(chunk)
                        if received > _MAX_ARTIFACT_BYTES:
                            raise PluginStoreError("plugin artifact exceeded the 256 MiB limit")
                        if artifact.bytes is not None and received > artifact.bytes:
                            raise PluginStoreError("plugin artifact exceeded its declared byte size")
                        handle.write(chunk)
            return self.import_file(temporary, artifact.sha256, artifact.bytes)
        except (OSError, URLError) as error:
            raise PluginStoreError(f"cannot fetch plugin artifact {artifact.sha256!r}: {error}") from error
        finally:
            temporary.unlink(missing_ok=True)

    def require(self, digest: str) -> Path:
        """Return one verified cached artifact without contacting an artifact source.

        Args:
            digest: Expected lowercase SHA-256 digest.

        Returns:
            The requested `Path` value.

        Security:
            Cached artifacts are rehashed on every trust-boundary lookup so a
            local mutation cannot bypass the index digest before extraction.
        """

        normalized = _sha256(digest, "artifact")
        self._validate_root()
        destination = self.path_for(normalized)
        if destination.is_symlink() or not destination.is_file():
            raise PluginStoreError(f"cached plugin artifact {normalized!r} is unavailable")
        if destination.stat().st_size > _MAX_ARTIFACT_BYTES:
            raise PluginStoreError(f"cached plugin artifact {normalized!r} exceeds the 256 MiB limit")
        if self._digest(destination) != normalized:
            raise PluginStoreError(f"cached plugin artifact {normalized!r} is corrupt")
        return destination

    def collect(self, retained_digests: set[str] | frozenset[str]) -> tuple[str, ...]:
        """Delete content-addressed artifacts not referenced by retained generations.

        Args:
            retained_digests: SHA-256 directory identities still referenced by
                active or rollback generations across every runtime target.

        Returns:
            Sorted digests removed from the local artifact store.

        Security:
            Store entries are validated as real digest-named directories before
            deletion. Symbolic links and unexpected entries abort collection so
            cleanup cannot escape the workspace-owned store.
        """
        retained = {_sha256(digest, "retained artifact") for digest in retained_digests}
        if not self.root.exists():
            return ()
        if self.root.is_symlink() or not self.root.is_dir():
            raise PluginStoreError("plugin artifact store directory is unsafe")
        collected: list[str] = []
        for entry in sorted(self.root.iterdir(), key=lambda path: path.name):
            digest = _sha256(entry.name, "artifact store entry")
            if entry.is_symlink() or not entry.is_dir():
                raise PluginStoreError(f"plugin artifact store entry {digest!r} is unsafe")
            artifact = entry / "artifact"
            if artifact.is_symlink() or not artifact.is_file():
                raise PluginStoreError(f"plugin artifact store entry {digest!r} is incomplete")
            if digest not in retained:
                shutil.rmtree(entry)
                collected.append(digest)
        return tuple(collected)

    def extract_zip(self, digest: str, destination: str | Path) -> Path:
        """Atomically extract a verified plugin ZIP into one generation directory.

        Args:
            digest: Expected lowercase SHA-256 digest.
            destination: Generation payload directory replaced after validation.

        Returns:
            Resolved extraction directory after atomic replacement.

        Security:
            Archives are a path and resource-exhaustion boundary. Extraction is
            retained for wheel/plugin payloads, but digest, member count, path,
            link, individual size, and total size checks run before activation.
            See `docs/security/trusted-boundaries.md#plugin-artifacts-and-native-code`.
        """
        artifact = self.require(digest)
        target = Path(destination).resolve()
        temporary = target.with_name(target.name + ".tmp")
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.mkdir(parents=True)
        try:
            with zipfile.ZipFile(artifact) as archive:
                for member, member_path in _validated_archive_members(archive):
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

    def validate_expanded_total(self, digests: Iterable[str], *, maximum: int = _MAX_ARCHIVE_EXTRACTED_BYTES) -> int:
        """Validate cumulative expanded bytes for generation archive inputs.

        Args:
            digests: Content-addressed ZIP or wheel artifacts in the generation.
            maximum: Maximum cumulative central-directory file size.

        Returns:
            Total declared expanded bytes across unique artifacts.

        Security:
            Per-archive checks alone allow a dependency closure to multiply the
            extraction budget. This preflight validates every central directory
            and applies one cumulative generation ceiling before any runtime
            environment or payload extraction starts.
        """
        total = 0
        for digest in dict.fromkeys(digests):
            try:
                with zipfile.ZipFile(self.require(digest)) as archive:
                    total += sum(member.file_size for member, _path in _validated_archive_members(archive))
            except zipfile.BadZipFile as error:
                raise PluginStoreError(f"plugin artifact {digest!r} is not a valid ZIP archive") from error
            if total > maximum:
                raise PluginStoreError("plugin generation exceeds the cumulative extracted size limit")
        return total

    @staticmethod
    def _digest(path: Path) -> str:
        """Implement the digest operation for the artifact store.

        Args:
            path: Filesystem or logical resource path.

        Returns:
            The `str` result produced by the operation.

        Notes:
            Internal implementation detail for `ArtifactStore._digest`. It delegates to `sha256`, `open`,
            `iter`, `read` while keeping intermediate state local to the owning operation.
        """
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _validate_root(self) -> None:
        """Reject a redirected or replaced artifact-store root."""

        if self.root.is_symlink() or (self.root.exists() and not self.root.is_dir()):
            raise PluginStoreError("plugin artifact store directory is unsafe")


@dataclass(frozen=True, slots=True)
class RuntimeGeneration:
    """Represent the runtime generation contract."""
    id: str
    runtime_id: str
    runtime_kind: str
    created_at: str
    target: PlatformTarget
    bundles: tuple[str, ...]
    artifacts: tuple[str, ...]
    load_plan: dict[str, Any]
    source_id: str | None = None
    index_digest: str | None = None
    roots: tuple[str, ...] = ()
    resolved_bundles: tuple[PluginBundle, ...] = ()
    disabled_roots: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate and normalize the runtime generation after initialization.

        Returns:
            None.
        """
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
        resolution_values = (self.source_id, self.index_digest, self.roots, self.resolved_bundles)
        if any(value is not None and value != () for value in resolution_values) and not all(
            value is not None and value != () for value in resolution_values
        ):
            raise PluginStoreError("runtime generation resolution metadata must be complete")
        if self.source_id is not None:
            if not self.source_id or self.source_id != self.source_id.strip() or any(
                character.isspace() for character in self.source_id
            ):
                raise PluginStoreError("plugin source id must be a non-empty whitespace-free string")
            object.__setattr__(self, "index_digest", _sha256(self.index_digest, "plugin index"))
            roots = tuple(_identifier(item, "plugin root", bundle=True) for item in self.roots)
            if len(set(roots)) != len(roots):
                raise PluginStoreError("runtime generation cannot repeat plugin roots")
            object.__setattr__(self, "roots", roots)
            disabled_roots = tuple(
                _identifier(item, "disabled plugin root", bundle=True) for item in self.disabled_roots
            )
            if len(set(disabled_roots)) != len(disabled_roots):
                raise PluginStoreError("runtime generation cannot repeat disabled plugin roots")
            if not set(disabled_roots).issubset(roots):
                raise PluginStoreError("runtime generation disabled plugin roots must be installed roots")
            object.__setattr__(self, "disabled_roots", disabled_roots)
            if len({bundle.id for bundle in self.resolved_bundles}) != len(self.resolved_bundles):
                raise PluginStoreError("runtime generation cannot repeat resolved bundles")
            if tuple(bundle.id for bundle in self.resolved_bundles) != self.bundles:
                raise PluginStoreError("runtime generation resolved bundles do not match bundle IDs")

    def document(self) -> dict[str, Any]:
        """Return the serialized document for the runtime generation operation.

        Returns:
            The `dict[str, Any]` result produced by the operation.
        """
        return {
            "schema": 2,
            "id": self.id,
            "runtime_id": self.runtime_id,
            "runtime_kind": self.runtime_kind,
            "created_at": self.created_at,
            "target": self.target.document(),
            "bundles": list(self.bundles),
            "artifacts": list(self.artifacts),
            "load_plan": self.load_plan,
            **(
                {
                    "resolution": {
                        "source_id": self.source_id,
                        "index_digest": self.index_digest,
                        "roots": list(self.roots),
                        "disabled_roots": list(self.disabled_roots),
                        "bundles": [bundle.document() for bundle in self.resolved_bundles],
                    }
                }
                if self.source_id is not None
                else {}
            ),
        }

    @property
    def digest(self) -> str:
        """Return the runtime generation's digest.

        Returns:
            The `str` result produced by the operation.
        """
        return hashlib.sha256(json.dumps(self.document(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Deployment:
    """Represent the deployment contract."""
    kernel_profile: str | None
    runtime_generations: dict[str, str]
    previous: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and normalize the deployment after initialization.

        Returns:
            None.
        """
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
        """Return the serialized document for the deployment operation.

        Returns:
            The `dict[str, Any]` result produced by the operation.
        """
        return {
            "schema": 2,
            "kernel_profile": self.kernel_profile,
            "runtimes": dict(sorted(self.runtime_generations.items())),
            "previous_runtimes": dict(sorted(self.previous.items())),
        }


class RuntimeGenerationStore:
    """Persist verified generation manifests and atomically switch deployment pointers."""

    def __init__(self, workspace: str | Path) -> None:
        """Initialize the runtime generation store.

        Args:
            workspace: The workspace value used by the operation.

        Returns:
            None.
        """
        self.workspace = Path(workspace).resolve()
        self.root = self.workspace / ".liteyuki" / "plugins" / "runtimes"
        self.lock = self.workspace / "liteyuki.lock"

    def path_for(self, runtime_id: str, generation_id: str) -> Path:
        """Implement the path for operation for the runtime generation store.

        Args:
            runtime_id: Stable runtime identifier.
            generation_id: Stable identifier for the generation.

        Returns:
            The `Path` result produced by the operation.
        """
        return (
            self.root
            / _identifier(runtime_id, "runtime id")
            / "generations"
            / _identifier(generation_id, "generation id")
        )

    @staticmethod
    def python_path(generation_path: str | Path) -> Path:
        """Implement the python path operation for the runtime generation store.

        Args:
            generation_path: Filesystem path for the generation.

        Returns:
            The `Path` result produced by the operation.
        """
        root = Path(generation_path)
        return root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    def write(self, generation: RuntimeGeneration) -> Path:
        """Write the runtime generation store operation.

        Args:
            generation: Positive protocol or deployment generation.

        Returns:
            The `Path` result produced by the operation.
        """
        path = self.path_for(generation.runtime_id, generation.id)
        manifest = path / "manifest.json"
        if manifest.exists():
            if self.read(generation.runtime_id, generation.id).digest != generation.digest:
                raise PluginStoreError("generation ID already belongs to a different manifest")
            return path
        path.mkdir(parents=True, exist_ok=True)
        self._write_json(manifest, generation.document())
        self._write_json(path / "load-plan.json", generation.load_plan)
        return path

    def read(self, runtime_id: str, generation_id: str) -> RuntimeGeneration:
        """Read the runtime generation store operation.

        Args:
            runtime_id: Stable runtime identifier.
            generation_id: Stable identifier for the generation.

        Returns:
            The `RuntimeGeneration` result produced by the operation.
        """
        path = self.path_for(runtime_id, generation_id) / "manifest.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            schema = value.get("schema")
            if schema not in {1, 2}:
                raise ValueError("unexpected generation schema")
            target = _json_object(value["target"], "generation target")
            bundles = tuple(str(item) for item in value["bundles"])
            source_id: str | None = None
            index_digest: str | None = None
            roots: tuple[str, ...] = ()
            resolved_bundles: tuple[PluginBundle, ...] = ()
            disabled_roots: tuple[str, ...] = ()
            if schema == 2 and "resolution" in value:
                resolution = _json_object(value["resolution"], "generation resolution")
                source_id = str(resolution["source_id"])
                index_digest = str(resolution["index_digest"])
                roots = tuple(str(item) for item in resolution["roots"])
                raw_disabled_roots = resolution.get("disabled_roots", [])
                if not isinstance(raw_disabled_roots, list):
                    raise ValueError("generation disabled roots must be an array")
                disabled_roots = tuple(str(item) for item in raw_disabled_roots)
                raw_bundles = resolution["bundles"]
                if not isinstance(raw_bundles, list):
                    raise ValueError("generation resolution bundles must be an array")
                index_schema = 2 if any(
                    isinstance(raw_bundle, dict) and "display_name" in raw_bundle for raw_bundle in raw_bundles
                ) else 1
                resolved = PluginIndex.parse({"schema": index_schema, "bundles": raw_bundles})
                by_id = {bundle.id: bundle for bundle in resolved.bundles()}
                resolved_bundles = tuple(by_id[item] for item in bundles)
            generation = RuntimeGeneration(
                id=str(value["id"]),
                runtime_id=str(value["runtime_id"]),
                runtime_kind=str(value["runtime_kind"]),
                created_at=str(value["created_at"]),
                target=PlatformTarget(str(target["system"]), str(target["machine"]), str(target["python"])),
                bundles=bundles,
                artifacts=tuple(str(item) for item in value["artifacts"]),
                load_plan=_json_object(value["load_plan"], "generation load plan"),
                source_id=source_id,
                index_digest=index_digest,
                roots=roots,
                resolved_bundles=resolved_bundles,
                disabled_roots=disabled_roots,
            )
            load_plan_path = self.path_for(runtime_id, generation_id) / "load-plan.json"
            if load_plan_path.is_symlink() or not load_plan_path.is_file():
                raise ValueError("generation load plan is unavailable")
            stored_load_plan = _json_object(
                json.loads(load_plan_path.read_text(encoding="utf-8")),
                "generation load plan",
            )
            if stored_load_plan != generation.load_plan:
                raise ValueError("generation load plan does not match its manifest")
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise PluginStoreError(f"runtime generation {generation_id!r} is not verified") from error
        if generation.runtime_id != runtime_id:
            raise PluginStoreError(f"runtime generation {generation_id!r} is not verified")
        return generation

    def active(self) -> Deployment:
        """Implement the active operation for the runtime generation store.

        Returns:
            The `Deployment` result produced by the operation.
        """
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
        """Atomically select a previously verified runtime generation.

        Args:
            runtime_id: Stable runtime identifier.
            generation_id: Stable identifier for the generation.

        Returns:
            New deployment snapshot including rollback history.

        Security:
            Activation changes executable plugin code. It is retained for
            upgrades and rollback, but only `read`-verified immutable generations
            can enter the deployment lock. Native plugins remain trusted code;
            see `docs/security/trusted-boundaries.md#plugin-artifacts-and-native-code`.
        """
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
        """Implement the rollback operation for the runtime generation store.

        Args:
            runtime_id: Stable runtime identifier.

        Returns:
            The `Deployment` result produced by the operation.
        """
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

    def deactivate(self, runtime_id: str) -> Deployment:
        """Implement the deactivate operation for the runtime generation store.

        Args:
            runtime_id: Stable runtime identifier.

        Returns:
            The `Deployment` result produced by the operation.
        """
        current = self.active()
        normalized = _identifier(runtime_id, "runtime id")
        runtimes = dict(current.runtime_generations)
        try:
            old = runtimes.pop(normalized)
        except KeyError as error:
            raise PluginStoreError(f"runtime {runtime_id!r} has no active plugin generation") from error
        previous = dict(current.previous)
        previous[normalized] = old
        deployment = Deployment(current.kernel_profile, runtimes, previous)
        self._write_json(self.lock, deployment.document())
        return deployment

    def list_generations(self, runtime_id: str | None = None) -> tuple[RuntimeGeneration, ...]:
        """List generations.

        Args:
            runtime_id: Stable runtime identifier.

        Returns:
            The `tuple[RuntimeGeneration, ...]` result produced by the operation.
        """
        if self.root.exists() and (self.root.is_symlink() or not self.root.is_dir()):
            raise PluginStoreError("plugin runtime directory is unsafe")
        runtime_ids: tuple[str, ...]
        if runtime_id is not None:
            runtime_ids = (_identifier(runtime_id, "runtime id"),)
        elif not self.root.exists():
            return ()
        else:
            runtime_ids = tuple(self._directory_ids(self.root, "runtime id"))
        generations: list[RuntimeGeneration] = []
        for current_runtime_id in runtime_ids:
            directory = self.root / current_runtime_id / "generations"
            if not directory.exists():
                continue
            for generation_id in self._directory_ids(directory, "generation id"):
                generations.append(self.read(current_runtime_id, generation_id))
        return tuple(generations)

    def collect(self, runtime_id: str | None = None) -> tuple[RuntimeGeneration, ...]:
        """Collect the runtime generation store operation.

        Args:
            runtime_id: Stable runtime identifier.

        Returns:
            The `tuple[RuntimeGeneration, ...]` result produced by the operation.
        """
        deployment = self.active()
        retained = {
            (current_runtime_id, generation_id)
            for mapping in (deployment.runtime_generations, deployment.previous)
            for current_runtime_id, generation_id in mapping.items()
        }
        collected: list[RuntimeGeneration] = []
        for generation in self.list_generations(runtime_id):
            if (generation.runtime_id, generation.id) in retained:
                continue
            path = self.path_for(generation.runtime_id, generation.id)
            if path.is_symlink() or not path.is_dir():
                raise PluginStoreError(f"runtime generation {generation.id!r} has an unsafe directory")
            shutil.rmtree(path)
            collected.append(generation)
        self._prune_empty_generation_directories(runtime_id)
        return tuple(collected)

    def _directory_ids(self, directory: Path, subject: str) -> tuple[str, ...]:
        """Implement the directory ids operation for the runtime generation store.

        Args:
            directory: The directory value used by the operation.
            subject: The subject value used by the operation.

        Returns:
            The `tuple[str, ...]` result produced by the operation.

        Notes:
            Internal implementation detail for `RuntimeGenerationStore._directory_ids`. It delegates to
            `is_symlink`, `is_dir`, `sorted`, `iterdir` while keeping intermediate state local to the owning
            operation.
        """
        if directory.is_symlink() or not directory.is_dir():
            raise PluginStoreError(f"plugin {subject} directory is unsafe")
        identifiers: list[str] = []
        for entry in sorted(directory.iterdir(), key=lambda item: item.name):
            if entry.is_symlink() or not entry.is_dir():
                raise PluginStoreError(f"plugin {subject} directory contains an unsafe entry")
            identifiers.append(_identifier(entry.name, subject))
        return tuple(identifiers)

    def _prune_empty_generation_directories(self, runtime_id: str | None) -> None:
        """Implement the prune empty generation directories operation for the runtime generation store.

        Args:
            runtime_id: Stable runtime identifier.

        Returns:
            None.

        Notes:
            Internal implementation detail for `RuntimeGenerationStore._prune_empty_generation_directories`.
            It delegates to `exists`, `_directory_ids`, `_identifier`, `rmdir` while keeping intermediate
            state local to the owning operation.
        """
        if not self.root.exists():
            return
        runtime_ids = (runtime_id,) if runtime_id is not None else tuple(self._directory_ids(self.root, "runtime id"))
        for current_runtime_id in runtime_ids:
            generations = self.root / _identifier(current_runtime_id, "runtime id") / "generations"
            try:
                generations.rmdir()
            except OSError:
                continue
            try:
                generations.parent.rmdir()
            except OSError:
                continue

    @staticmethod
    def new_generation_id() -> str:
        """Implement the new generation id operation for the runtime generation store.

        Returns:
            The `str` result produced by the operation.
        """
        return "g" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S-") + hashlib.sha256(os.urandom(16)).hexdigest()[:8]

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        """Write json.

        Args:
            path: Filesystem or logical resource path.
            value: Value to validate, transform, or store.

        Returns:
            None.

        Notes:
            Internal implementation detail for `RuntimeGenerationStore._write_json`. It delegates to
            `mkdir`, `with_suffix`, `write_text`, `dumps` while keeping intermediate state local to the
            owning operation.
        """
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
    "PLUGIN_GENERATION_ENV",
    "PluginBundle",
    "PluginFacet",
    "PluginIndex",
    "PluginLicense",
    "PluginPublisher",
    "PluginStoreError",
    "RuntimeGeneration",
    "RuntimeGenerationStore",
]
