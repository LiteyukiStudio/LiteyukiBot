from __future__ import annotations

import importlib
import json
import os
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .errors import ConfigIssue, ConfigurationError
from .models import AppSettings

type ConfigMap = dict[str, Any]
type CliOverrides = Mapping[str, Any] | Iterable[str]


@dataclass(frozen=True, slots=True)
class ConfigSource:
    """One configuration layer that supplied a value."""

    kind: str
    source: str


@dataclass(frozen=True, slots=True)
class ConfigProvenance:
    """Immutable source chains indexed by JSON Pointer paths."""

    chains: Mapping[tuple[str, ...], tuple[ConfigSource, ...]]

    def explain(self, pointer: str) -> tuple[ConfigSource, ...]:
        """Implement the explain operation for the config provenance.

        Args:
            pointer: The pointer value used by the operation.

        Returns:
            The `tuple[ConfigSource, ...]` result produced by the operation.
        """
        path = _parse_pointer(pointer)
        exact = self.chains.get(path)
        if exact is not None:
            return exact
        descendants = [
            source
            for candidate, chain in self.chains.items()
            if candidate[: len(path)] == path
            for source in chain
        ]
        if not descendants:
            raise ValueError(f"configuration pointer does not exist: {pointer}")
        return tuple(dict.fromkeys(descendants))


@dataclass(frozen=True, slots=True)
class ConfigInspection:
    """Validated settings plus their complete source provenance."""

    settings: AppSettings
    provenance: ConfigProvenance

    def explain(self, pointer: str) -> ConfigExplanation:
        """Implement the explain operation for the config inspection.

        Args:
            pointer: The pointer value used by the operation.

        Returns:
            The `ConfigExplanation` result produced by the operation.
        """
        return ConfigExplanation(
            pointer=pointer,
            value=_value_at_pointer(self.settings.model_dump(mode="json"), _parse_pointer(pointer)),
            sources=self.provenance.explain(pointer),
        )


@dataclass(frozen=True, slots=True)
class ConfigExplanation:
    """One final value and the ordered layers that supplied it."""

    pointer: str
    value: Any
    sources: tuple[ConfigSource, ...]


class _ProvenanceTracker:
    """Represent the provenance tracker contract."""
    def __init__(self) -> None:
        """Initialize the provenance tracker.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_ProvenanceTracker.__init__`. It performs the local state
            transition directly and is not a stable extension boundary.
        """
        self.chains: dict[tuple[str, ...], list[ConfigSource]] = {}

    def apply(self, value: Mapping[str, Any], source: ConfigSource) -> None:
        """Implement the apply operation for the provenance tracker.

        Args:
            value: Value to validate, transform, or store.
            source: Source value or location to process.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_ProvenanceTracker.apply`. It delegates to `_apply` while
            keeping intermediate state local to the owning operation.
        """
        self._apply(value, source, ())

    def freeze(self) -> ConfigProvenance:
        """Freeze the provenance tracker operation.

        Returns:
            The `ConfigProvenance` result produced by the operation.

        Notes:
            Internal implementation detail for `_ProvenanceTracker.freeze`. It delegates to `items` while
            keeping intermediate state local to the owning operation.
        """
        return ConfigProvenance({path: tuple(chain) for path, chain in self.chains.items()})

    def _apply(self, value: Any, source: ConfigSource, path: tuple[str, ...]) -> None:
        """Implement the apply operation for the provenance tracker.

        Args:
            value: Value to validate, transform, or store.
            source: Source value or location to process.
            path: Filesystem or logical resource path.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_ProvenanceTracker._apply`. It delegates to `append`,
            `setdefault`, `items`, `_apply` while keeping intermediate state local to the owning operation.
        """
        if isinstance(value, Mapping):
            if not value:
                self.chains.setdefault(path, []).append(source)
                return
            for key, child in value.items():
                self._apply(child, source, (*path, str(key)))
            return
        self.chains.setdefault(path, []).append(source)


def _deep_merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> ConfigMap:
    """Implement the deep merge operation for the component.

    Args:
        base: The base value used by the operation.
        overlay: The overlay value used by the operation.

    Returns:
        The `ConfigMap` result produced by the operation.

    Notes:
        Internal implementation detail for `_deep_merge`. It delegates to `items`, `get`, `_deep_merge`
        while keeping intermediate state local to the owning operation.
    """
    merged = dict(base)
    for key, value in overlay.items():
        current = merged.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def _parse_value(value: str) -> Any:
    """Parse value.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `Any` result produced by the operation.

    Notes:
        Internal implementation detail for `_parse_value`. It delegates to `loads` while keeping
        intermediate state local to the owning operation.
    """
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _assign_nested(target: ConfigMap, path: Sequence[str], value: Any) -> None:
    """Implement the assign nested operation for the component.

    Args:
        target: Target value or location for the operation.
        path: Filesystem or logical resource path.
        value: Value to validate, transform, or store.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_assign_nested`. It delegates to `get` while keeping
        intermediate state local to the owning operation.
    """
    cursor = target
    for part in path[:-1]:
        child = cursor.get(part)
        if not isinstance(child, dict):
            child = {}
            cursor[part] = child
        cursor = child
    cursor[path[-1]] = value


def _normalize_override_key(key: str, separator: str) -> tuple[str, ...]:
    """Normalize override key.

    Args:
        key: Stable FIFO ordering key for the queued work.
        separator: The separator value used by the operation.

    Returns:
        The `tuple[str, ...]` result produced by the operation.

    Notes:
        Internal implementation detail for `_normalize_override_key`. It delegates to `lower`, `strip`,
        `split` while keeping intermediate state local to the owning operation.
    """
    return tuple(part.strip().lower() for part in key.split(separator))


def _environment_layer(environ: Mapping[str, str], issues: list[ConfigIssue]) -> ConfigMap:
    """Implement the environment layer operation for the component.

    Args:
        environ: The environ value used by the operation.
        issues: The issues value used by the operation.

    Returns:
        The `ConfigMap` result produced by the operation.

    Notes:
        Internal implementation detail for `_environment_layer`. It delegates to `items`, `startswith`,
        `upper`, `_normalize_override_key` while keeping intermediate state local to the owning
        operation.
    """
    result: ConfigMap = {}
    prefix = "LITEYUKI__"
    for key, raw_value in environ.items():
        if not key.upper().startswith(prefix):
            continue
        path = _normalize_override_key(key[len(prefix) :], "__")
        if not path or any(not part for part in path):
            issues.append(ConfigIssue("environment", "expected LITEYUKI__SECTION__FIELD", (key,)))
            continue
        _assign_nested(result, path, _parse_value(raw_value))
    return result


def _cli_layer(overrides: CliOverrides, issues: list[ConfigIssue]) -> ConfigMap:
    """Implement the cli layer operation for the component.

    Args:
        overrides: The overrides value used by the operation.
        issues: The issues value used by the operation.

    Returns:
        The `ConfigMap` result produced by the operation.

    Notes:
        Internal implementation detail for `_cli_layer`. It delegates to `items`, `append`,
        `_deep_merge`, `lower` while keeping intermediate state local to the owning operation.
    """
    result: ConfigMap = {}
    if isinstance(overrides, Mapping):
        for key, value in overrides.items():
            if not isinstance(key, str):
                issues.append(ConfigIssue("CLI", "override keys must be strings"))
                continue
            if "." not in key:
                if isinstance(value, Mapping):
                    result = _deep_merge(result, {key.lower(): dict(value)})
                else:
                    result[key.lower()] = value
                continue
            path = _normalize_override_key(key, ".")
            if any(not part for part in path):
                issues.append(ConfigIssue("CLI", "expected a dotted setting path", (key,)))
                continue
            _assign_nested(result, path, value)
        return result

    for index, override in enumerate(overrides):
        if not isinstance(override, str) or "=" not in override:
            issues.append(ConfigIssue("CLI", "expected KEY=VALUE", (index,)))
            continue
        key, raw_value = override.split("=", 1)
        path = _normalize_override_key(key, ".")
        if not path or any(not part for part in path):
            issues.append(ConfigIssue("CLI", "expected a dotted setting path", (index,)))
            continue
        _assign_nested(result, path, _parse_value(raw_value))
    return result


def _resolve_path(value: Any, base_directory: Path) -> Any:
    """Resolve path.

    Args:
        value: Value to validate, transform, or store.
        base_directory: The base directory value used by the operation.

    Returns:
        The `Any` result produced by the operation.

    Notes:
        Internal implementation detail for `_resolve_path`. It delegates to `expanduser`, `is_absolute`,
        `resolve` while keeping intermediate state local to the owning operation.
    """
    if not isinstance(value, (str, os.PathLike)):
        return value
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_directory / path
    return path.resolve(strict=False)


def _resolve_declared_paths(data: ConfigMap, base_directory: Path) -> ConfigMap:
    """Resolve declared paths.

    Args:
        data: The data value used by the operation.
        base_directory: The base directory value used by the operation.

    Returns:
        The `ConfigMap` result produced by the operation.

    Notes:
        Internal implementation detail for `_resolve_declared_paths`. It delegates to `get`,
        `_resolve_path`, `items` while keeping intermediate state local to the owning operation.
    """
    result = dict(data)

    core = result.get("core")
    if isinstance(core, Mapping):
        resolved_core = dict(core)
        for key in ("data_dir", "cache_dir"):
            if key in resolved_core:
                resolved_core[key] = _resolve_path(resolved_core[key], base_directory)
        result["core"] = resolved_core

    logging = result.get("logging")
    if isinstance(logging, Mapping):
        resolved_logging = dict(logging)
        if "file" in resolved_logging and resolved_logging["file"] is not None:
            resolved_logging["file"] = _resolve_path(resolved_logging["file"], base_directory)
        result["logging"] = resolved_logging

    profile = result.get("profile")
    if isinstance(profile, Mapping):
        resolved_profile = dict(profile)
        if "database" in resolved_profile and resolved_profile["database"] is not None:
            resolved_profile["database"] = _resolve_path(resolved_profile["database"], base_directory)
        result["profile"] = resolved_profile

    return result


class _FileLoader:
    """Represent the file loader contract."""
    def __init__(self, issues: list[ConfigIssue], tracker: _ProvenanceTracker | None = None) -> None:
        """Initialize the file loader.

        Args:
            issues: The issues value used by the operation.
            tracker: The tracker value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_FileLoader.__init__`. It performs the local state
            transition directly and is not a stable extension boundary.
        """
        self.issues = issues
        self.tracker = tracker
        self._active: list[Path] = []
        self._loaded: dict[str, Path] = {}

    @staticmethod
    def _identity(path: Path) -> str:
        """Implement the identity operation for the file loader.

        Args:
            path: Filesystem or logical resource path.

        Returns:
            The `str` result produced by the operation.

        Notes:
            Internal implementation detail for `_FileLoader._identity`. It delegates to `normcase`,
            `resolve` while keeping intermediate state local to the owning operation.
        """
        return os.path.normcase(str(path.resolve(strict=False)))

    def load_root(self, path: str | os.PathLike[str], *, require_config_version: bool = False) -> ConfigMap:
        """Load root.

        Args:
            path: Filesystem or logical resource path.
            require_config_version: The require config version value used by the operation.

        Returns:
            The `ConfigMap` result produced by the operation.

        Notes:
            Internal implementation detail for `_FileLoader.load_root`. It delegates to `resolve`,
            `expanduser`, `_load_file` while keeping intermediate state local to the owning operation.
        """
        resolved = Path(path).expanduser().resolve(strict=False)
        return self._load_file(resolved, included_by=None, require_config_version=require_config_version)

    def _load_file(
        self, path: Path, *, included_by: Path | None, require_config_version: bool = False
    ) -> ConfigMap:
        """Load file.

        Args:
            path: Filesystem or logical resource path.
            included_by: The included by value used by the operation.
            require_config_version: The require config version value used by the operation.

        Returns:
            The `ConfigMap` result produced by the operation.

        Notes:
            Internal implementation detail for `_FileLoader._load_file`. It delegates to `_identity`,
            `index`, `join`, `append` while keeping intermediate state local to the owning operation.
        """
        identity = self._identity(path)
        active_identities = [self._identity(active) for active in self._active]
        if identity in active_identities:
            cycle_start = active_identities.index(identity)
            cycle = (*self._active[cycle_start:], path)
            chain = " -> ".join(str(item) for item in cycle)
            self.issues.append(ConfigIssue(included_by or path, f"include cycle detected: {chain}", ("include",)))
            return {}
        if identity in self._loaded:
            first_source = self._loaded[identity]
            self.issues.append(
                ConfigIssue(
                    included_by or path,
                    f"configuration file is included more than once; first loaded as {first_source}",
                    ("include",),
                )
            )
            return {}

        parsed = self._parse_file(path)
        if parsed is None:
            return {}
        if require_config_version and parsed.get("config_version") != 7:
            self.issues.append(ConfigIssue(path, "root configuration requires config_version = 7"))
        self._loaded[identity] = path
        self._active.append(path)
        try:
            include_value = parsed.pop("include", [])
            included = self._load_includes(include_value, path)
            own_values = _resolve_declared_paths(parsed, path.parent)
            if self.tracker is not None:
                self.tracker.apply(own_values, ConfigSource("file", str(path)))
            return _deep_merge(included, own_values)
        finally:
            self._active.pop()

    def _load_includes(self, include_value: Any, declaring_file: Path) -> ConfigMap:
        """Load includes.

        Args:
            include_value: The include value value used by the operation.
            declaring_file: The declaring file value used by the operation.

        Returns:
            The `ConfigMap` result produced by the operation.

        Notes:
            Internal implementation detail for `_FileLoader._load_includes`. It delegates to `append`,
            `enumerate`, `strip`, `expanduser` while keeping intermediate state local to the owning
            operation.
        """
        if not isinstance(include_value, list):
            self.issues.append(ConfigIssue(declaring_file, "include must be an array of file paths", ("include",)))
            return {}
        merged: ConfigMap = {}
        for index, raw_path in enumerate(include_value):
            if not isinstance(raw_path, str) or not raw_path.strip():
                self.issues.append(
                    ConfigIssue(declaring_file, "include entries must be non-empty file paths", ("include", index))
                )
                continue
            included_path = Path(raw_path).expanduser()
            if not included_path.is_absolute():
                included_path = declaring_file.parent / included_path
            values = self._load_file(included_path.resolve(strict=False), included_by=declaring_file)
            merged = _deep_merge(merged, values)
        return merged

    def _parse_file(self, path: Path) -> ConfigMap | None:
        """Parse file.

        Args:
            path: Filesystem or logical resource path.

        Returns:
            The `ConfigMap | None` result produced by the operation.

        Notes:
            Internal implementation detail for `_FileLoader._parse_file`. It delegates to `read_bytes`,
            `append`, `lower`, `loads` while keeping intermediate state local to the owning operation.
        """
        try:
            raw = path.read_bytes()
        except OSError as error:
            reason = error.strerror or type(error).__name__
            self.issues.append(ConfigIssue(path, f"cannot read configuration file: {reason}"))
            return None

        suffix = path.suffix.lower()
        try:
            if suffix == ".toml":
                value = tomllib.loads(raw.decode("utf-8"))
            elif suffix == ".json":
                value = json.loads(raw.decode("utf-8-sig"))
            elif suffix in {".yaml", ".yml"}:
                value = self._parse_yaml(raw, path)
                if value is None:
                    return None
            else:
                self.issues.append(
                    ConfigIssue(path, "unsupported format; expected .toml, .json, .yaml, or .yml")
                )
                return None
        except (UnicodeDecodeError, tomllib.TOMLDecodeError, json.JSONDecodeError) as error:
            self.issues.append(ConfigIssue(path, f"cannot parse {suffix or 'configuration'} file: {error}"))
            return None

        if value is None:
            return {}
        if not isinstance(value, dict):
            self.issues.append(ConfigIssue(path, "configuration document must contain an object at its root"))
            return None
        if any(not isinstance(key, str) for key in value):
            self.issues.append(ConfigIssue(path, "top-level configuration keys must be strings"))
            return None
        return dict(value)

    def _parse_yaml(self, raw: bytes, path: Path) -> Any:
        """Parse yaml.

        Args:
            raw: The raw value used by the operation.
            path: Filesystem or logical resource path.

        Returns:
            The `Any` result produced by the operation.

        Notes:
            Internal implementation detail for `_FileLoader._parse_yaml`. It delegates to `import_module`,
            `append`, `safe_load`, `decode` while keeping intermediate state local to the owning operation.
        """
        try:
            yaml = importlib.import_module("yaml")
        except ModuleNotFoundError as error:
            if error.name not in {None, "yaml"}:
                self.issues.append(ConfigIssue(path, f"cannot import YAML support: missing dependency {error.name}"))
                return None
            self.issues.append(
                ConfigIssue(
                    path,
                    "YAML support is not installed; run `uv add 'liteyukibot-v7[yaml]'` or use TOML/JSON",
                )
            )
            return None
        try:
            return yaml.safe_load(raw.decode("utf-8-sig"))
        except UnicodeDecodeError as error:
            self.issues.append(ConfigIssue(path, f"cannot decode YAML file as UTF-8: {error}"))
        except Exception as error:  # PyYAML exposes parser-specific exception classes dynamically.
            self.issues.append(ConfigIssue(path, f"cannot parse YAML file: {error}"))
        return None


def load_settings(
    primary_path: str | os.PathLike[str] | None = None,
    *,
    config_paths: Iterable[str | os.PathLike[str]] = (),
    environ: Mapping[str, str] | None = None,
    cli_overrides: CliOverrides = (),
) -> AppSettings:
    """Load and validate one immutable configuration snapshot.

    ``config_paths`` preserves the order of repeated CLI ``--config`` options.
    Iterable ``cli_overrides`` values use ``section.field=JSON_VALUE`` syntax;
    mappings may contain either nested values or dotted keys.

    Args:
        primary_path: Filesystem path for the primary.
        config_paths: The config paths value used by the operation.
        environ: The environ value used by the operation.
        cli_overrides: The cli overrides value used by the operation.

    Returns:
        The `AppSettings` result produced by the operation.
    """

    return _load_settings(
        primary_path,
        config_paths=config_paths,
        environ=environ,
        cli_overrides=cli_overrides,
        tracker=None,
    )[0]


def inspect_settings(
    primary_path: str | os.PathLike[str] | None = None,
    *,
    config_paths: Iterable[str | os.PathLike[str]] = (),
    environ: Mapping[str, str] | None = None,
    cli_overrides: CliOverrides = (),
) -> ConfigInspection:
    """Load settings and preserve the full source chain for every value.

    Args:
        primary_path: Filesystem path for the primary.
        config_paths: The config paths value used by the operation.
        environ: The environ value used by the operation.
        cli_overrides: The cli overrides value used by the operation.

    Returns:
        The `ConfigInspection` result produced by the operation.
    """

    tracker = _ProvenanceTracker()
    tracker.apply(AppSettings().model_dump(mode="json"), ConfigSource("default", "kernel defaults"))
    settings, provenance = _load_settings(
        primary_path,
        config_paths=config_paths,
        environ=environ,
        cli_overrides=cli_overrides,
        tracker=tracker,
    )
    assert provenance is not None
    return ConfigInspection(settings, provenance)


def _load_settings(
    primary_path: str | os.PathLike[str] | None,
    *,
    config_paths: Iterable[str | os.PathLike[str]],
    environ: Mapping[str, str] | None,
    cli_overrides: CliOverrides,
    tracker: _ProvenanceTracker | None,
) -> tuple[AppSettings, ConfigProvenance | None]:
    """Load settings.

    Args:
        primary_path: Filesystem path for the primary.
        config_paths: The config paths value used by the operation.
        environ: The environ value used by the operation.
        cli_overrides: The cli overrides value used by the operation.
        tracker: The tracker value used by the operation.

    Returns:
        The `tuple[AppSettings, ConfigProvenance | None]` result produced by the operation.

    Notes:
        Internal implementation detail for `_load_settings`.
    """
    issues: list[ConfigIssue] = []
    loader = _FileLoader(issues, tracker)
    merged: ConfigMap = {}
    path_base = Path.cwd()

    if primary_path is not None:
        path_base = Path(primary_path).expanduser().resolve(strict=False).parent
        primary_values = loader.load_root(primary_path, require_config_version=True)
        merged = _deep_merge(merged, primary_values)
    for config_path in config_paths:
        merged = _deep_merge(merged, loader.load_root(config_path))
    environment_values = _environment_layer(os.environ if environ is None else environ, issues)
    if tracker is not None:
        tracker.apply(environment_values, ConfigSource("environment", "LITEYUKI__"))
    merged = _deep_merge(merged, _resolve_declared_paths(environment_values, path_base))
    command_line_values = _cli_layer(cli_overrides, issues)
    if tracker is not None:
        tracker.apply(command_line_values, ConfigSource("command_line", "--set"))
    merged = _deep_merge(merged, _resolve_declared_paths(command_line_values, path_base))
    _reject_removed_sections(merged, issues)

    try:
        settings = AppSettings.model_validate(merged)
    except ValidationError as error:
        for detail in error.errors(include_url=False, include_context=False, include_input=False):
            issues.append(
                ConfigIssue(
                    "merged configuration",
                    str(detail["msg"]),
                    tuple(detail["loc"]),
                )
            )
        settings = None

    if issues:
        raise ConfigurationError(issues)
    if settings is None:  # Kept explicit for type checkers; validation errors are handled above.
        raise RuntimeError("configuration validation failed without an issue")
    return settings, None if tracker is None else tracker.freeze()


def _reject_removed_sections(merged: Mapping[str, Any], issues: list[ConfigIssue]) -> None:
    """Report configuration sections that no longer have an active owner."""
    removed = (
        "broker",
        "runtime",
        "runtimes",
        "daemon",
        "webui",
        "http",
        "lyip",
        "agent",
        "plugins",
        "development",
        "vault",
    )
    for name in removed:
        if name in merged:
            issues.append(
                ConfigIssue(
                    "merged configuration",
                    f"configuration section [{name}] was removed in config_version 7",
                    (name,),
                )
            )


def _parse_pointer(pointer: str) -> tuple[str, ...]:
    """Parse pointer.

    Args:
        pointer: The pointer value used by the operation.

    Returns:
        The `tuple[str, ...]` result produced by the operation.

    Notes:
        Internal implementation detail for `_parse_pointer`. It delegates to `startswith`, `split`,
        `append`, `join` while keeping intermediate state local to the owning operation.
    """
    if pointer == "":
        return ()
    if not pointer.startswith("/"):
        raise ValueError("configuration pointer must be an RFC 6901 JSON Pointer")
    parts: list[str] = []
    for part in pointer[1:].split("/"):
        decoded: list[str] = []
        index = 0
        while index < len(part):
            character = part[index]
            if character != "~":
                decoded.append(character)
                index += 1
                continue
            if index + 1 >= len(part) or part[index + 1] not in {"0", "1"}:
                raise ValueError("configuration pointer contains an invalid escape")
            decoded.append("~" if part[index + 1] == "0" else "/")
            index += 2
        parts.append("".join(decoded))
    return tuple(parts)


def _value_at_pointer(value: Any, path: tuple[str, ...]) -> Any:
    """Implement the value at pointer operation for the component.

    Args:
        value: Value to validate, transform, or store.
        path: Filesystem or logical resource path.

    Returns:
        The `Any` result produced by the operation.

    Notes:
        Internal implementation detail for `_value_at_pointer`. It delegates to `join`, `isdigit`, `int`
        while keeping intermediate state local to the owning operation.
    """
    current = value
    for part in path:
        if isinstance(current, Mapping):
            try:
                current = current[part]
            except KeyError as error:
                raise ValueError(f"configuration pointer does not exist: /{'/'.join(path)}") from error
            continue
        if isinstance(current, (list, tuple)) and part.isdigit():
            index = int(part)
            try:
                current = current[index]
            except IndexError as error:
                raise ValueError(f"configuration pointer does not exist: /{'/'.join(path)}") from error
            continue
        raise ValueError(f"configuration pointer does not exist: /{'/'.join(path)}")
    return current
