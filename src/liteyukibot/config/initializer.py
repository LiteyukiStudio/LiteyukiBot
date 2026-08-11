"""Interactive project initialization from installed package metadata."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from ..init_specs import InitFieldKind, InitFieldSpec
from ..plugins import PluginDefinition, PluginManager
from ..runtime import RuntimeCatalog, RuntimePlugin
from ..services import ServiceKey
from ..status import KERNEL_STATUS_SERVICE

Prompt = Callable[[str, str], str]
Output = Callable[[str], None]
SecretPrompt = Callable[[str], str]


@dataclass(frozen=True, slots=True)
class InitializationPlan:
    """A validated set of ordinary TOML values ready for ConfigWorkspace."""

    data_dir: str
    cache_dir: str
    logging_level: str
    payload_mode: str
    payload_exclude_runtimes: tuple[str, ...]
    plugins: tuple[str, ...]
    plugin_config: dict[str, dict[str, Any]]
    runtimes: dict[str, dict[str, Any]]
    runtime_event_routes: tuple[dict[str, Any], ...]
    secrets: dict[str, str]
    diagnostics: tuple[str, ...]


def build_initialization_plan(
    *,
    prompt: Prompt,
    output: Output,
    secret_prompt: SecretPrompt | None = None,
) -> InitializationPlan:
    """Collect a safe configuration using only package-owned initialization metadata."""

    data_dir = prompt("Data directory", "data")
    cache_dir = prompt("Cache directory", "cache")
    logging_level = prompt("Logging level", "INFO").upper()
    payload_mode = prompt("Payload logging mode (metadata/full)", "metadata").lower()
    payload_exclude_runtimes = _split_values(prompt("Payload exclusion runtime IDs (comma-separated)", ""))

    plugin_definitions, plugin_diagnostics = PluginManager.discover_installed()
    runtime_plugins, runtime_diagnostics = RuntimeCatalog().discover_installed()
    diagnostics = plugin_diagnostics + runtime_diagnostics
    for diagnostic in diagnostics:
        output(f"warning: {diagnostic}")

    selected_plugins = _select_plugins(plugin_definitions, prompt=prompt, output=output)
    plugin_config = _collect_plugin_config(selected_plugins, plugin_definitions, prompt=prompt)
    runtimes, secrets = _select_runtimes(
        runtime_plugins,
        prompt=prompt,
        output=output,
        secret_prompt=secret_prompt,
    )
    routes = _collect_agent_routes(runtimes, runtime_plugins, prompt=prompt)

    return InitializationPlan(
        data_dir=data_dir,
        cache_dir=cache_dir,
        logging_level=logging_level,
        payload_mode=payload_mode,
        payload_exclude_runtimes=payload_exclude_runtimes,
        plugins=selected_plugins,
        plugin_config=plugin_config,
        runtimes=runtimes,
        runtime_event_routes=routes,
        secrets=secrets,
        diagnostics=diagnostics,
    )


def _select_plugins(
    definitions: Mapping[str, PluginDefinition],
    *,
    prompt: Prompt,
    output: Output,
) -> tuple[str, ...]:
    selected: set[str] = set()
    providers: dict[ServiceKey, tuple[str, ...]] = {}
    for plugin_id, definition in definitions.items():
        for service in definition.manifest.provides:
            providers[service] = (*providers.get(service, ()), plugin_id)

    def select(plugin_id: str) -> None:
        if plugin_id in selected:
            return
        definition = definitions[plugin_id]
        selected.add(plugin_id)
        for requirement in definition.manifest.requires:
            if requirement.optional or requirement.key == KERNEL_STATUS_SERVICE:
                continue
            candidates = tuple(sorted(providers.get(requirement.key, ())))
            if not candidates:
                raise ValueError(f"plugin {plugin_id} requires unavailable service {requirement.key}")
            provider = _choose_provider(
                plugin_id,
                requirement.key,
                candidates,
                prompt=prompt,
                output=output,
            )
            if provider is None:
                raise ValueError(f"plugin {plugin_id} requires service {requirement.key}; setup was cancelled")
            select(provider)

    for plugin_id, definition in sorted(definitions.items()):
        if plugin_id in selected:
            continue
        label = definition.manifest.name
        if _confirm(prompt, f"Enable plugin {label} ({plugin_id})", default=False):
            select(plugin_id)

    selected_definitions = {plugin_id: definitions[plugin_id] for plugin_id in selected}
    return PluginManager.resolve_definitions(
        selected_definitions,
        {KERNEL_STATUS_SERVICE: "liteyukibot.kernel"},
    )


def _choose_provider(
    consumer: str,
    service: ServiceKey,
    candidates: tuple[str, ...],
    *,
    prompt: Prompt,
    output: Output,
) -> str | None:
    if len(candidates) == 1:
        provider = candidates[0]
        if _confirm(
            prompt,
            f"Enable required provider {provider} for {consumer} ({service})",
            default=True,
        ):
            return provider
        return None

    output(f"{consumer} requires {service}; available providers: {', '.join(candidates)}")
    value = prompt(f"Provider for {service} (or 'skip')", candidates[0])
    if value == "skip":
        return None
    if value not in candidates:
        raise ValueError(f"unknown provider {value!r} for service {service}")
    return value


def _collect_plugin_config(
    selected: tuple[str, ...],
    definitions: Mapping[str, PluginDefinition],
    *,
    prompt: Prompt,
) -> dict[str, dict[str, Any]]:
    config: dict[str, dict[str, Any]] = {}
    for plugin_id in selected:
        spec = definitions[plugin_id].init_spec
        if spec is None or not spec.fields:
            continue
        values = _collect_fields(spec.fields, prompt=prompt, subject=f"Plugin {plugin_id}")
        if values:
            config[plugin_id] = values
    return config


def _select_runtimes(
    plugins: Mapping[str, RuntimePlugin],
    *,
    prompt: Prompt,
    output: Output,
    secret_prompt: SecretPrompt | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    runtimes: dict[str, dict[str, Any]] = {}
    secrets: dict[str, str] = {}
    for kind, plugin in sorted(plugins.items()):
        spec = plugin.init_spec
        if spec is None:
            output(f"warning: runtime {kind!r} has no initialization metadata and was skipped")
            continue
        secret_fields = tuple(field for field in spec.fields if field.kind is InitFieldKind.SECRET)
        if secret_fields and secret_prompt is None:
            output(f"runtime {kind!r} requires the secure vault and was skipped during this initialization")
            continue
        if not _confirm(prompt, f"Enable runtime {kind}", default=False):
            continue
        runtime_id = spec.default_id
        if runtime_id in runtimes:
            raise ValueError(f"runtime initialization id collision: {runtime_id}")
        options = dict(spec.default_options)
        options.update(_collect_fields(spec.fields, prompt=prompt, subject=f"Runtime {kind}"))
        secret_env: dict[str, str] = {}
        if secret_fields:
            assert secret_prompt is not None
            for field in secret_fields:
                secret_name = f"runtime.{runtime_id}.{field.key}"
                secret_value = secret_prompt(f"Runtime {kind}: {field.label}")
                if not secret_value and field.required:
                    raise ValueError(f"Runtime {kind}: {field.label} is required")
                if secret_value:
                    secrets[secret_name] = secret_value
                    options[field.key] = secret_name
                    assert field.secret_environment is not None
                    secret_env[field.secret_environment] = secret_name
        runtimes[runtime_id] = {
            "kind": kind,
            "enabled": True,
            "heartbeat_interval_seconds": 10.0,
            "stale_after_seconds": 30.0,
            "max_inbound_events": 100,
            "options": options,
            "secret_env": secret_env,
        }
    return runtimes, secrets


def _collect_agent_routes(
    runtimes: Mapping[str, Mapping[str, Any]],
    plugins: Mapping[str, RuntimePlugin],
    *,
    prompt: Prompt,
) -> tuple[dict[str, Any], ...]:
    routes: list[dict[str, Any]] = []
    sources = tuple(
        runtime_id for runtime_id, config in runtimes.items() if plugins[str(config["kind"])].agent_harness is None
    )
    for runtime_id, config in runtimes.items():
        plugin = plugins[str(config["kind"])]
        if plugin.agent_harness is None:
            continue
        for source in sources:
            if _confirm(
                prompt,
                f"Route messages from {source} to agent runtime {runtime_id}",
                default=False,
            ):
                routes.append({"sources": [source], "target": runtime_id, "messages_only": True})
    return tuple(routes)


def _collect_fields(
    fields: tuple[InitFieldSpec, ...],
    *,
    prompt: Prompt,
    subject: str,
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field in fields:
        if field.kind is InitFieldKind.SECRET:
            continue
        values[field.key] = _read_field(field, prompt=prompt, subject=subject)
    return values


def _read_field(field: InitFieldSpec, *, prompt: Prompt, subject: str) -> Any:
    default = _format_default(field.default)
    label = f"{subject}: {field.label}"
    value = prompt(label, default)
    if not value and field.required:
        raise ValueError(f"{subject}: {field.label} is required")
    if field.choices and value not in field.choices:
        raise ValueError(f"{subject}: {field.label} must be one of {', '.join(field.choices)}")
    if field.kind is InitFieldKind.INTEGER:
        try:
            return int(value)
        except ValueError as error:
            raise ValueError(f"{subject}: {field.label} must be an integer") from error
    if field.kind is InitFieldKind.BOOLEAN:
        if value.lower() in {"1", "true", "yes", "y"}:
            return True
        if value.lower() in {"0", "false", "no", "n"}:
            return False
        raise ValueError(f"{subject}: {field.label} must be true or false")
    if field.kind is InitFieldKind.STRING_LIST:
        return list(_split_values(value))
    return value


def _confirm(prompt: Prompt, label: str, *, default: bool) -> bool:
    value = prompt(f"{label} [y/N]" if not default else f"{label} [Y/n]", "y" if default else "n")
    normalized = value.lower()
    if normalized in {"y", "yes", "1", "true"}:
        return True
    if normalized in {"n", "no", "0", "false"}:
        return False
    raise ValueError(f"{label}: expected yes or no")


def _split_values(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _format_default(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, tuple):
        return ", ".join(str(item) for item in value)
    return str(value)


__all__ = ["InitializationPlan", "build_initialization_plan"]
