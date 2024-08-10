import multiprocessing

from nonebot.plugin import PluginMetadata
from liteyuki.comm import get_channel
from .rt_guide import *
from .crt_matchers import *

__plugin_meta__ = PluginMetadata(
    name="CRT生成工具",
    description="一些CRT牌子生成器",
    usage="我觉得你应该会用",
    type="application",
    homepage="https://github.com/snowykami/LiteyukiBot",
    extra={
            "liteyuki"      : True,
            "toggleable"    : True,
            "default_enable": True,
    }
)

# chan = get_channel("nonebot-passive")
#
#
# @chan.on_receive()
# async def _(d):
#     print("CRT子进程接收到数据：", d)
#     chan.send("CRT子进程已接收到数据")
