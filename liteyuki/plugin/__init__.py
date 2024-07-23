from liteyuki.plugin.model import Plugin, PluginMetadata
from liteyuki.plugin.load import load_plugin, _plugins

__all__ = [
        "PluginMetadata",
        "Plugin",
        "load_plugin",
]


def get_loaded_plugins() -> dict[str, Plugin]:
    """
    获取已加载的插件
    Returns:
        dict[str, Plugin]: 插件字典
    """
    return _plugins
