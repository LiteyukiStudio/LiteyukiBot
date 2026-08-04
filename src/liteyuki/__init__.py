"""LiteyukiBot v6 compatibility API hosted by the v7 runtime."""

from .bot import LiteyukiBot, get_bot, get_config, get_config_with_compat
from .log import init_log, logger
from .plugin import Plugin, PluginMetadata, PluginType, get_loaded_plugins, load_plugin, load_plugins

__all__ = [
    "LiteyukiBot",
    "Plugin",
    "PluginMetadata",
    "PluginType",
    "get_bot",
    "get_config",
    "get_config_with_compat",
    "get_loaded_plugins",
    "init_log",
    "load_plugin",
    "load_plugins",
    "logger",
]

__version__ = "7.0.0a1"
