from typing import Optional, TYPE_CHECKING

import nonebot

from liteyuki.core.nb import adapter_manager, driver_manager
from liteyuki.comm.channel import set_channel

if TYPE_CHECKING:
    from liteyuki.comm.channel import Channel

timeout_limit: int = 20

"""导出对象，用于主进程与nonebot通信"""
_channels = {}


def nb_run(chan_active: "Channel", chan_passive: "Channel", *args, **kwargs):
    """
    初始化NoneBot并运行在子进程
    Args:

        chan_active:
        chan_passive:
        **kwargs:

    Returns:

    """
    set_channel("nonebot-active", chan_active)
    set_channel("nonebot-passive", chan_passive)
    nonebot.init(**kwargs)
    driver_manager.init(config=kwargs)
    adapter_manager.init(kwargs)
    adapter_manager.register()
    nonebot.load_plugin("src.liteyuki_main")
    nonebot.run()


def mb_run(chan_active: "Channel", chan_passive: "Channel", *args, **kwargs):
    """
    初始化MeloBot并运行在子进程
    Args:
        chan_active
        chan_passive
        *args:
        **kwargs:

    Returns:

    """
    set_channel("melobot-active", chan_active)
    set_channel("melobot-passive", chan_passive)

    # bot = MeloBot(__name__)
    # bot.init(AbstractConnector(cd_time=0))
    # bot.run()
