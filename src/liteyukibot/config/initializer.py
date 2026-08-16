"""Interactive project initialization from installed package metadata."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from ..i18n import I18N_SERVICE, Translator
from ..init_specs import InitFieldKind, InitFieldSpec
from ..plugins import PluginDefinition, PluginManager
from ..resource_packs import ResourceCatalog
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
    logging_console: bool
    logging_json_lines: bool
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
    locale: str = "auto",
    logging_settings: tuple[str, bool, bool, str, tuple[str, ...]] | None = None,
) -> InitializationPlan:
    """Collect a safe configuration using only package-owned initialization metadata."""

    plugin_definitions, plugin_diagnostics = PluginManager.discover_installed()
    runtime_plugins, runtime_diagnostics = RuntimeCatalog().discover_installed()
    declarations = tuple((
        {
            (declaration.package, declaration.root): declaration
            for definition in plugin_definitions.values()
            for declaration in definition.manifest.resource_packs
        }
        | {
            (declaration.package, declaration.root): declaration
        for plugin in runtime_plugins.values()
        for declaration in plugin.resource_packs
        }
    ).values())
    translator, warning = Translator.from_resources(ResourceCatalog.load(".", plugin_packs=declarations), locale)
    data_dir = prompt(translator.text("init.data_dir", "Data directory"), "data")
    cache_dir = prompt(translator.text("init.cache_dir", "Cache directory"), "cache")
    if logging_settings is None:
        logging_level = prompt(translator.text("init.logging_level", "Logging level"), "INFO").upper()
        logging_console = _confirm(
            prompt, translator.text("init.logging_console", "Enable console logs"), default=True
        )
        logging_json_lines = _confirm(
            prompt, translator.text("init.logging_json", "Enable JSON Lines logs"), default=False
        )
        payload_mode = prompt(
            translator.text("init.payload_mode", "Payload logging mode (metadata/full)"),
            "metadata",
        ).lower()
        payload_exclude_runtimes = _split_values(
            prompt(
                translator.text("init.payload_exclude_runtimes", "Payload exclusion runtime IDs (comma-separated)"),
                "",
            )
        )
    else:
        logging_level, logging_console, logging_json_lines, payload_mode, payload_exclude_runtimes = logging_settings
    diagnostics = plugin_diagnostics + runtime_diagnostics
    if warning is not None:
        output(f"warning: {warning}")
    for diagnostic in diagnostics:
        output(f"warning: {diagnostic}")

    selected_plugins = _select_plugins(plugin_definitions, prompt=prompt, output=output, translator=translator)
    plugin_config = _collect_plugin_config(selected_plugins, plugin_definitions, prompt=prompt, translator=translator)
    runtimes, secrets = _select_runtimes(
        runtime_plugins,
        prompt=prompt,
        output=output,
        secret_prompt=secret_prompt,
        translator=translator,
    )
    routes = _collect_agent_routes(runtimes, runtime_plugins, prompt=prompt, translator=translator)

    return InitializationPlan(
        data_dir=data_dir,
        cache_dir=cache_dir,
        logging_level=logging_level,
        logging_console=logging_console,
        logging_json_lines=logging_json_lines,
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
    translator: Translator,
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
            if requirement.optional or requirement.key in {KERNEL_STATUS_SERVICE, I18N_SERVICE}:
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
                translator=translator,
            )
            if provider is None:
                raise ValueError(f"plugin {plugin_id} requires service {requirement.key}; setup was cancelled")
            select(provider)

    for plugin_id, definition in sorted(definitions.items()):
        if plugin_id in selected:
            continue
        label = definition.manifest.name
        if _confirm(
            prompt,
            translator.text("init.enable_plugin", "Enable plugin {name} ({id})", name=label, id=plugin_id),
            default=False,
        ):
            select(plugin_id)

    selected_definitions = {plugin_id: definitions[plugin_id] for plugin_id in selected}
    return PluginManager.resolve_definitions(
        selected_definitions,
        {
            KERNEL_STATUS_SERVICE: "liteyukibot.kernel",
            I18N_SERVICE: "liteyukibot.kernel",
        },
    )


def _choose_provider(
    consumer: str,
    service: ServiceKey,
    candidates: tuple[str, ...],
    *,
    prompt: Prompt,
    output: Output,
    translator: Translator,
) -> str | None:
    if len(candidates) == 1:
        provider = candidates[0]
        if _confirm(
            prompt,
            translator.text(
                "init.enable_provider",
                "Enable required provider {provider} for {consumer} ({service})",
                provider=provider,
                consumer=consumer,
                service=service,
            ),
            default=True,
        ):
            return provider
        return None

    output(
        translator.text(
            "init.available_providers",
            "{consumer} requires {service}; available providers: {providers}",
            consumer=consumer,
            service=service,
            providers=", ".join(candidates),
        )
    )
    value = prompt(
        translator.text("init.provider", "Provider for {service} (or 'skip')", service=service),
        candidates[0],
    )
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
    translator: Translator,
) -> dict[str, dict[str, Any]]:
    config: dict[str, dict[str, Any]] = {}
    for plugin_id in selected:
        spec = definitions[plugin_id].init_spec
        if spec is None or not spec.fields:
            continue
        values = _collect_fields(spec.fields, prompt=prompt, subject=f"Plugin {plugin_id}", translator=translator)
        if values:
            config[plugin_id] = values
    return config


def _select_runtimes(
    plugins: Mapping[str, RuntimePlugin],
    *,
    prompt: Prompt,
    output: Output,
    secret_prompt: SecretPrompt | None,
    translator: Translator,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    runtimes: dict[str, dict[str, Any]] = {}
    secrets: dict[str, str] = {}
    for kind, plugin in sorted(plugins.items()):
        spec = plugin.init_spec
        if spec is None:
            output(
                translator.text(
                    "init.runtime_missing_spec",
                    "warning: runtime {kind} has no initialization metadata and was skipped",
                    kind=kind,
                )
            )
            continue
        secret_fields = tuple(field for field in spec.fields if field.kind is InitFieldKind.SECRET)
        if secret_fields and secret_prompt is None:
            output(
                translator.text(
                    "init.runtime_missing_vault",
                    "runtime {kind} requires the secure vault and was skipped during this initialization",
                    kind=kind,
                )
            )
            continue
        if not _confirm(
            prompt,
            translator.text("init.enable_runtime", "Enable runtime {kind}", kind=kind),
            default=False,
        ):
            continue
        runtime_id = spec.default_id
        if runtime_id in runtimes:
            raise ValueError(f"runtime initialization id collision: {runtime_id}")
        options = dict(spec.default_options)
        options.update(_collect_fields(spec.fields, prompt=prompt, subject=f"Runtime {kind}", translator=translator))
        secret_env: dict[str, str] = {}
        if secret_fields:
            assert secret_prompt is not None
            for field in secret_fields:
                secret_name = f"runtime.{runtime_id}.{field.key}"
                label = _field_label(field, translator)
                secret_value = secret_prompt(f"Runtime {kind}: {label}")
                if not secret_value and field.required:
                    raise ValueError(f"Runtime {kind}: {label} is required")
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
    translator: Translator,
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
                translator.text(
                    "init.route_agent",
                    "Route messages from {source} to agent runtime {target}",
                    source=source,
                    target=runtime_id,
                ),
                default=False,
            ):
                routes.append(
                    {
                        "sources": [source],
                        "target": runtime_id,
                        "messages_only": True,
                        "policy": "required",
                        "completion": "async",
                    }
                )
    return tuple(routes)


def _collect_fields(
    fields: tuple[InitFieldSpec, ...],
    *,
    prompt: Prompt,
    subject: str,
    translator: Translator,
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field in fields:
        if field.kind is InitFieldKind.SECRET:
            continue
        values[field.key] = _read_field(field, prompt=prompt, subject=subject, translator=translator)
    return values


def _read_field(field: InitFieldSpec, *, prompt: Prompt, subject: str, translator: Translator) -> Any:
    default = _format_default(field.default)
    label = f"{subject}: {_field_label(field, translator)}"
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


def _field_label(field: InitFieldSpec, translator: Translator) -> str:
    return translator.text(field.label_key, field.label) if field.label_key is not None else field.label


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
