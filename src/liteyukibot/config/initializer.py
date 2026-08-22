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
    """Collect a safe configuration using only package-owned initialization metadata.

    Args:
        prompt: The prompt value used by the operation.
        output: The output value used by the operation.
        secret_prompt: The secret prompt value used by the operation.
        locale: The locale value used by the operation.
        logging_settings: The logging settings value used by the operation.

    Returns:
        The `InitializationPlan` result produced by the operation.
    """

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
        runtime_event_routes=(),
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
    """Select plugins.

    Args:
        definitions: The definitions value used by the operation.
        prompt: The prompt value used by the operation.
        output: The output value used by the operation.
        translator: The translator value used by the operation.

    Returns:
        The `tuple[str, ...]` result produced by the operation.

    Notes:
        Internal implementation detail for `_select_plugins`. It delegates to `items`, `get`, `sorted`,
        `_confirm` while keeping intermediate state local to the owning operation.
    """
    selected: set[str] = set()
    providers: dict[ServiceKey, tuple[str, ...]] = {}
    for plugin_id, definition in definitions.items():
        for service in definition.manifest.provides:
            providers[service] = (*providers.get(service, ()), plugin_id)

    def select(plugin_id: str) -> None:
        """Select the select plugins operation.

        Args:
            plugin_id: Stable identifier for the plugin.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_select_plugins.select`. It delegates to `add`, `sorted`,
            `get`, `_choose_provider` while keeping intermediate state local to the owning operation.
        """
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
    """Implement the choose provider operation for the component.

    Args:
        consumer: The consumer value used by the operation.
        service: Service implementation used by the operation.
        candidates: The candidates value used by the operation.
        prompt: The prompt value used by the operation.
        output: The output value used by the operation.
        translator: The translator value used by the operation.

    Returns:
        The `str | None` result produced by the operation.

    Notes:
        Internal implementation detail for `_choose_provider`. It delegates to `_confirm`, `text`,
        `output`, `join` while keeping intermediate state local to the owning operation.
    """
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
    """Collect plugin config.

    Args:
        selected: The selected value used by the operation.
        definitions: The definitions value used by the operation.
        prompt: The prompt value used by the operation.
        translator: The translator value used by the operation.

    Returns:
        The `dict[str, dict[str, Any]]` result produced by the operation.

    Notes:
        Internal implementation detail for `_collect_plugin_config`. It delegates to `_collect_fields`
        while keeping intermediate state local to the owning operation.
    """
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
    """Select runtimes.

    Args:
        plugins: The plugins value used by the operation.
        prompt: The prompt value used by the operation.
        output: The output value used by the operation.
        secret_prompt: The secret prompt value used by the operation.
        translator: The translator value used by the operation.

    Returns:
        The `tuple[dict[str, dict[str, Any]], dict[str, str]]` result produced by the operation.

    Notes:
        Internal implementation detail for `_select_runtimes`. It delegates to `sorted`, `items`,
        `output`, `text` while keeping intermediate state local to the owning operation.
    """
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


def _collect_fields(
    fields: tuple[InitFieldSpec, ...],
    *,
    prompt: Prompt,
    subject: str,
    translator: Translator,
) -> dict[str, Any]:
    """Collect fields.

    Args:
        fields: Structured fields attached to the operation.
        prompt: The prompt value used by the operation.
        subject: The subject value used by the operation.
        translator: The translator value used by the operation.

    Returns:
        The `dict[str, Any]` result produced by the operation.

    Notes:
        Internal implementation detail for `_collect_fields`. It delegates to `_read_field` while
        keeping intermediate state local to the owning operation.
    """
    values: dict[str, Any] = {}
    for field in fields:
        if field.kind is InitFieldKind.SECRET:
            continue
        values[field.key] = _read_field(field, prompt=prompt, subject=subject, translator=translator)
    return values


def _read_field(field: InitFieldSpec, *, prompt: Prompt, subject: str, translator: Translator) -> Any:
    """Read field.

    Args:
        field: The field value used by the operation.
        prompt: The prompt value used by the operation.
        subject: The subject value used by the operation.
        translator: The translator value used by the operation.

    Returns:
        The `Any` result produced by the operation.

    Notes:
        Internal implementation detail for `_read_field`. It delegates to `_format_default`,
        `_field_label`, `prompt`, `join` while keeping intermediate state local to the owning operation.
    """
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
    """Implement the field label operation for the component.

    Args:
        field: The field value used by the operation.
        translator: The translator value used by the operation.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_field_label`. It delegates to `text` while keeping
        intermediate state local to the owning operation.
    """
    return translator.text(field.label_key, field.label) if field.label_key is not None else field.label


def _confirm(prompt: Prompt, label: str, *, default: bool) -> bool:
    """Implement the confirm operation for the component.

    Args:
        prompt: The prompt value used by the operation.
        label: The label value used by the operation.
        default: The default value used by the operation.

    Returns:
        Whether the requested condition is satisfied.

    Notes:
        Internal implementation detail for `_confirm`. It delegates to `prompt`, `lower` while keeping
        intermediate state local to the owning operation.
    """
    value = prompt(f"{label} [y/N]" if not default else f"{label} [Y/n]", "y" if default else "n")
    normalized = value.lower()
    if normalized in {"y", "yes", "1", "true"}:
        return True
    if normalized in {"n", "no", "0", "false"}:
        return False
    raise ValueError(f"{label}: expected yes or no")


def _split_values(value: str) -> tuple[str, ...]:
    """Implement the split values operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `tuple[str, ...]` result produced by the operation.

    Notes:
        Internal implementation detail for `_split_values`. It delegates to `strip`, `split` while
        keeping intermediate state local to the owning operation.
    """
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _format_default(value: Any) -> str:
    """Implement the format default operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_format_default`. It delegates to `join` while keeping
        intermediate state local to the owning operation.
    """
    if value is None:
        return ""
    if isinstance(value, tuple):
        return ", ".join(str(item) for item in value)
    return str(value)


__all__ = ["InitializationPlan", "build_initialization_plan"]
