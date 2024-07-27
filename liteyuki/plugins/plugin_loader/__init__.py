import asyncio
import multiprocessing
import time

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from liteyuki.plugin import PluginMetadata
from liteyuki import get_bot, chan

__plugin_metadata__ = PluginMetadata(
    name="plugin_loader",
    description="轻雪插件加载器",
    usage="",
    type="liteyuki-main",
    homepage=""
)

from src.utils import TempConfig, common_db

liteyuki = get_bot()


@liteyuki.on_after_start
def _():
    temp_data = common_db.where_one(TempConfig(), default=TempConfig())
    # 储存重启计时信息
    if temp_data.data.get("reload", False):
        delta_time = time.time() - temp_data.data.get("reload_time", 0)
        temp_data.data["delta_time"] = delta_time
        common_db.save(temp_data)  # 更新数据


@liteyuki.on_before_start
def _():
    print("轻雪启动中")


@liteyuki.on_after_start
async def _():
    print("轻雪启动完成")
    chan.send("轻雪启动完成")


@liteyuki.on_after_nonebot_init
async def _():
    print("NoneBot初始化完成")


@chan.on_receive(receiver="main")
async def _(data):
    print("收到消息", data)
    await asyncio.sleep(5)

