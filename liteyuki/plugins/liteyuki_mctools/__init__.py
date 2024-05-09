from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="Minecraft工具箱",
    description="一些Minecraft相关工具箱",
    usage="我觉得你应该会用",
    type="application",
    homepage="https://github.com/snowykami/LiteyukiBot",
    extra={
            "liteyuki"      : True,
            "toggleable"    : True,
            "default_enable": True,
    }
)
