import nonebot
from nonebot.plugin import PluginMetadata

__author__ = "snowykami"
__plugin_meta__ = PluginMetadata(
    name="轻雪主程序",
    description="轻雪主程序插件，包含了许多初始化的功能",
    usage="",
    homepage="https://github.com/snowykami/LiteyukiBot",
)

fastapi_app = nonebot.get_app()


@fastapi_app.get("/")
async def root():
    return {
            "message": "Hello LiteyukiBot!",
    }
