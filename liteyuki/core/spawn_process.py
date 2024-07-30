import threading
from multiprocessing import Event, Queue
from typing import Optional

import nonebot

import liteyuki
from liteyuki.core.nb import adapter_manager, driver_manager

timeout_limit: int = 20

"""导出对象，用于进程通信"""
chan_in_spawn: Optional["liteyuki.Channel"] = None


def nb_run(chan, *args, **kwargs):
    """
    初始化NoneBot并运行在子进程
    Args:

        *args:
        **kwargs:

    Returns:

    """
    global chan_in_spawn
    chan_in_spawn = chan
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
