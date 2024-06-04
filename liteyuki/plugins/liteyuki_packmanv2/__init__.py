from nonebot.plugin import PluginMetadata

__author__ = "snowykami"
__plugin_meta__ = PluginMetadata(
    name="轻雪包管理器v2",
    description="详细看文档",
    usage=(
            "npm list\n"
            "npm enable/disable <plugin_name>\n"
            "npm search <keywords...>\n"
            "npm install/uninstall <plugin_name>\n"
    ),
    type="application",
    homepage="https://github.com/snowykami/LiteyukiBot",
    extra={
            "liteyuki": True,
            "toggleable"     : False,
            "default_enable" : False,
    }
)
