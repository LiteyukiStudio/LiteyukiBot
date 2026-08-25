"""Explicit v6 plugin imports without package installation or hot reload."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from liteyuki.log import logger

from .model import Plugin, PluginMetadata, PluginType

_plugins: dict[str, Plugin] = {}


def load_plugin(module_path: str | Path) -> Plugin | None:
    """Load plugin.

    Args:
        module_path: Filesystem path for the module.

    Returns:
        The `Plugin | None` result produced by the operation.
    """
    module_name = _module_name(module_path)
    try:
        module = import_module(module_name)
    except Exception:
        logger.exception('Failed to load Liteyuki v6 plugin "{}"', module_name)
        return None

    candidate = next(
        (
            module.__dict__[key]
            for key in ("__plugin_metadata__", "__liteyuki_plugin_meta__", "__plugin_meta__")
            if key in module.__dict__
        ),
        None,
    )
    metadata = _coerce_metadata(candidate, module_name)
    plugin = Plugin(name=module.__name__, module=module, module_name=module_name, metadata=metadata)
    _plugins[module.__name__] = plugin
    logger.success('Loaded Liteyuki v6 plugin "{}"', metadata.name)
    return plugin


def load_plugins(*plugin_dirs: str, ignore_warning: bool = True) -> set[Plugin]:
    """Load plugins.

    Args:
        ignore_warning: The ignore warning value used by the operation.
        *plugin_dirs: The plugin dirs value used by the operation.

    Returns:
        The `set[Plugin]` result produced by the operation.
    """
    loaded: set[Plugin] = set()
    for raw_directory in plugin_dirs:
        directory = Path(raw_directory)
        if not directory.is_dir():
            if not ignore_warning:
                logger.warning('Plugin directory "{}" does not exist', directory)
            continue
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.suffix == ".py" and path.name != "__init__.py":
                candidate: str | Path = path
            elif path.is_dir() and (path / "__init__.py").is_file():
                candidate = path
            else:
                continue
            plugin = load_plugin(candidate)
            if plugin is not None:
                loaded.add(plugin)
    return loaded


def get_loaded_plugins() -> dict[str, Plugin]:
    """Return loaded plugins.

    Returns:
        The requested `dict[str, Plugin]` value.
    """
    return dict(_plugins)


def _module_name(value: str | Path) -> str:
    """Implement the module name operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_module_name`. It delegates to `resolve`, `cwd`,
        `relative_to`, `with_suffix` while keeping intermediate state local to the owning operation.
    """
    if isinstance(value, str):
        return value
    resolved = value.resolve(strict=False)
    cwd = Path.cwd().resolve()
    try:
        relative = resolved.relative_to(cwd)
    except ValueError as error:
        raise ValueError(f"local v6 plugin path must be under the working directory: {value}") from error
    if relative.name == "__init__.py":
        relative = relative.parent
    elif relative.suffix == ".py":
        relative = relative.with_suffix("")
    return ".".join(relative.parts)


def _coerce_metadata(candidate: object, module_name: str) -> PluginMetadata:
    """Implement the coerce metadata operation for the component.

    Args:
        candidate: The candidate value used by the operation.
        module_name: The module name value used by the operation.

    Returns:
        The `PluginMetadata` result produced by the operation.

    Notes:
        Internal implementation detail for `_coerce_metadata`. It delegates to `getattr` while keeping
        intermediate state local to the owning operation.
    """
    if isinstance(candidate, PluginMetadata):
        return candidate
    if candidate is None:
        return PluginMetadata(name=module_name)
    return PluginMetadata(
        name=str(getattr(candidate, "name", module_name)),
        description=str(getattr(candidate, "description", "")),
        usage=str(getattr(candidate, "usage", "")),
        author=str(getattr(candidate, "author", "")),
        homepage=str(getattr(candidate, "homepage", "")),
    )


__all__ = [
    "Plugin",
    "PluginMetadata",
    "PluginType",
    "get_loaded_plugins",
    "load_plugin",
    "load_plugins",
]
