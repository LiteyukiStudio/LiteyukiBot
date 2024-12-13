from liteyuki.plugin.model import Plugin, PluginMetadata, PluginType
from liteyuki.plugin.load import load_plugin, load_plugins, _plugins

__all__ = [
        "PluginMetadata",
        "Plugin",
        "PluginType",
        "load_plugin",
        "load_plugins",
]


def get_loaded_plugins() -> dict[str, Plugin]:
    """
    获取已加载的插件
    Returns:
        dict[str, Plugin]: 插件字典
    """
    return _plugins
