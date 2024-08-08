from typing import Optional, TYPE_CHECKING

import nonebot

from liteyuki.core.nb import adapter_manager, driver_manager

if TYPE_CHECKING:
    from liteyuki.comm.channel import Channel

timeout_limit: int = 20

"""导出对象，用于主进程与nonebot通信"""
chan_in_spawn_nb: Optional["Channel"] = None


def nb_run(chan, *args, **kwargs):
    """
    初始化NoneBot并运行在子进程
    Args:

        chan:
        *args:
        **kwargs:

    Returns:

    """
    global chan_in_spawn_nb
    chan_in_spawn_nb = chan
    nonebot.init(**kwargs)
    driver_manager.init(config=kwargs)
    adapter_manager.init(kwargs)
    adapter_manager.register()
    nonebot.load_plugin("src.liteyuki_main")
    nonebot.run()


def mb_run(chan, *args, **kwargs):
    """
    初始化MeloBot并运行在子进程
    Args:
        chan
        *args:
        **kwargs:

    Returns:

    """
    # bot = MeloBot(__name__)
    # bot.init(AbstractConnector(cd_time=0))
    # bot.run()
