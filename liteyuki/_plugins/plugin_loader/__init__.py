import asyncio
import multiprocessing
import time

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


print("轻雪实例", liteyuki)
chan.send(liteyuki, "instance")
# @liteyuki.on_before_start
# def _():
#     print("轻雪启动中")
#
#
# @liteyuki.on_after_start
# async def _():
#     print("轻雪启动完成")
#     chan.send("轻雪启动完成")
