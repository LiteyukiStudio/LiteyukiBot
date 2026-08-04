from __future__ import annotations

import importlib
import json
import os
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .errors import ConfigIssue, ConfigurationError
from .models import AppSettings

type ConfigMap = dict[str, Any]
type CliOverrides = Mapping[str, Any] | Iterable[str]


def _deep_merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> ConfigMap:
    merged = dict(base)
    for key, value in overlay.items():
        current = merged.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def _parse_value(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _assign_nested(target: ConfigMap, path: Sequence[str], value: Any) -> None:
    cursor = target
    for part in path[:-1]:
        child = cursor.get(part)
        if not isinstance(child, dict):
            child = {}
            cursor[part] = child
        cursor = child
    cursor[path[-1]] = value


def _normalize_override_key(key: str, separator: str) -> tuple[str, ...]:
    return tuple(part.strip().lower() for part in key.split(separator))


def _environment_layer(environ: Mapping[str, str], issues: list[ConfigIssue]) -> ConfigMap:
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
    if not isinstance(value, (str, os.PathLike)):
        return value
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_directory / path
    return path.resolve(strict=False)


def _resolve_declared_paths(data: ConfigMap, base_directory: Path) -> ConfigMap:
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

    runtimes = result.get("runtimes")
    if isinstance(runtimes, Mapping):
        resolved_runtimes: ConfigMap = {}
        for runtime_id, runtime in runtimes.items():
            if isinstance(runtime, Mapping):
                resolved_runtime = dict(runtime)
                if "working_directory" in resolved_runtime and resolved_runtime["working_directory"] is not None:
                    resolved_runtime["working_directory"] = _resolve_path(
                        resolved_runtime["working_directory"], base_directory
                    )
                resolved_runtimes[str(runtime_id)] = resolved_runtime
            else:
                resolved_runtimes[str(runtime_id)] = runtime
        result["runtimes"] = resolved_runtimes

    return result


class _FileLoader:
    def __init__(self, issues: list[ConfigIssue]) -> None:
        self.issues = issues
        self._active: list[Path] = []
        self._loaded: dict[str, Path] = {}

    @staticmethod
    def _identity(path: Path) -> str:
        return os.path.normcase(str(path.resolve(strict=False)))

    def load_root(self, path: str | os.PathLike[str]) -> ConfigMap:
        resolved = Path(path).expanduser().resolve(strict=False)
        return self._load_file(resolved, included_by=None)

    def _load_file(self, path: Path, *, included_by: Path | None) -> ConfigMap:
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
        self._loaded[identity] = path
        self._active.append(path)
        try:
            include_value = parsed.pop("include", [])
            included = self._load_includes(include_value, path)
            own_values = _resolve_declared_paths(parsed, path.parent)
            return _deep_merge(included, own_values)
        finally:
            self._active.pop()

    def _load_includes(self, include_value: Any, declaring_file: Path) -> ConfigMap:
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
        try:
            yaml = importlib.import_module("yaml")
        except ModuleNotFoundError as error:
            if error.name not in {None, "yaml"}:
                self.issues.append(ConfigIssue(path, f"cannot import YAML support: missing dependency {error.name}"))
                return None
            self.issues.append(
                ConfigIssue(
                    path,
                    "YAML support is not installed; run `uv add 'liteyukibot[yaml]'` or use TOML/JSON",
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
    """

    issues: list[ConfigIssue] = []
    loader = _FileLoader(issues)
    merged: ConfigMap = {}

    if primary_path is not None:
        merged = _deep_merge(merged, loader.load_root(primary_path))
    for config_path in config_paths:
        merged = _deep_merge(merged, loader.load_root(config_path))

    environment_values = _environment_layer(os.environ if environ is None else environ, issues)
    merged = _deep_merge(merged, _resolve_declared_paths(environment_values, Path.cwd()))
    command_line_values = _cli_layer(cli_overrides, issues)
    merged = _deep_merge(merged, _resolve_declared_paths(command_line_values, Path.cwd()))

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
    return settings
