import multiprocessing

import nonebot
from nonebot import get_driver

from liteyuki.plugin import PluginMetadata
from liteyuki import get_bot

__plugin_metadata__ = PluginMetadata(
    name="plugin_loader",
    description="轻雪插件加载器",
    usage="",
    type="",
    homepage=""
)

liteyuki = get_bot()


@liteyuki.on_after_start
def _():
    print("轻雪启动完成，运行在进程", multiprocessing.current_process().name)


@liteyuki.on_before_start
def _():
    print("轻雪启动中")


@liteyuki.on_after_nonebot_init
async def _():
    print("NoneBot初始化完成")
    nonebot.load_plugin("src.liteyuki_main")
