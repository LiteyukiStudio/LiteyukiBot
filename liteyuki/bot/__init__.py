import threading
import time
import asyncio
from typing import Any, Optional
from multiprocessing import freeze_support

from liteyuki.bot.lifespan import (LIFESPAN_FUNC, Lifespan)
from liteyuki.comm.channel import Channel
from liteyuki.core import IS_MAIN_PROCESS
from liteyuki.core.manager import ProcessManager
from liteyuki.core.spawn_process import mb_run, nb_run
from liteyuki.log import init_log, logger
from liteyuki.plugin import load_plugins
from liteyuki.utils import run_coroutine

__all__ = [
        "LiteyukiBot",
        "get_bot"
]

"""是否为主进程"""


class LiteyukiBot:
    def __init__(self, *args, **kwargs):
        global _BOT_INSTANCE
        _BOT_INSTANCE = self  # 引用
        self.config: dict[str, Any] = kwargs
        self.init(**self.config)  # 初始化

        self.lifespan: Lifespan = Lifespan()
        self.chan = Channel()  # 进程通信通道
        self.pm: ProcessManager = ProcessManager(bot=self, chan=self.chan)
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop_thread = threading.Thread(target=self.loop.run_forever, daemon=True)

        print("\033[34m" + r"""
 __        ______  ________  ________  __      __  __    __  __    __  ______ 
/  |      /      |/        |/        |/  \    /  |/  |  /  |/  |  /  |/      |
$$ |      $$$$$$/ $$$$$$$$/ $$$$$$$$/ $$  \  /$$/ $$ |  $$ |$$ | /$$/ $$$$$$/ 
$$ |        $$ |     $$ |   $$ |__     $$  \/$$/  $$ |  $$ |$$ |/$$/    $$ |  
$$ |        $$ |     $$ |   $$    |     $$  $$/   $$ |  $$ |$$  $$<     $$ |  
$$ |        $$ |     $$ |   $$$$$/       $$$$/    $$ |  $$ |$$$$$  \    $$ |  
$$ |_____  _$$ |_    $$ |   $$ |_____     $$ |    $$ \__$$ |$$ |$$  \  _$$ |_ 
$$       |/ $$   |   $$ |   $$       |    $$ |    $$    $$/ $$ | $$  |/ $$   |
$$$$$$$$/ $$$$$$/    $$/    $$$$$$$$/     $$/      $$$$$$/  $$/   $$/ $$$$$$/ 
            """ + "\033[0m")

    def run(self):
        load_plugins("liteyuki/plugins")  # 加载轻雪插件

        self.loop_thread.start()  # 启动事件循环
        asyncio.run(self.lifespan.before_start())  # 启动前钩子

        self.pm.add_target("nonebot", nb_run, **self.config)
        self.pm.start("nonebot")

        self.pm.add_target("melobot", mb_run, **self.config)
        self.pm.start("melobot")

        asyncio.run(self.lifespan.after_start())  # 启动后钩子

    def restart(self, name: Optional[str] = None):
        """
        停止轻雪
        Args:
            name: 进程名称, 默认为None, 所有进程
        Returns:

        """
        logger.info("Stopping LiteyukiBot...")

        self.loop.create_task(self.lifespan.before_shutdown())  # 重启前钩子
        self.loop.create_task(self.lifespan.before_shutdown())  # 停止前钩子

        if name:
            self.chan.send(1, name)
        else:
            for name in self.pm.targets:
                self.chan.send(1, name)

    def init(self, *args, **kwargs):
        """
        初始化轻雪, 自动调用
        Returns:

        """
        self.init_config()
        self.init_logger()

    def init_logger(self):
        # 修改nonebot的日志配置
        init_log(config=self.config)

    def init_config(self):
        pass

    def on_before_start(self, func: LIFESPAN_FUNC):
        """
        注册启动前的函数
        Args:
            func:

        Returns:

        """
        return self.lifespan.on_before_start(func)

    def on_after_start(self, func: LIFESPAN_FUNC):
        """
        注册启动后的函数
        Args:
            func:

        Returns:

        """
        return self.lifespan.on_after_start(func)

    def on_before_shutdown(self, func: LIFESPAN_FUNC):
        """
        注册停止前的函数，为子进程停止时调用
        Args:
            func:

        Returns:

        """
        return self.lifespan.on_before_shutdown(func)

    def on_after_shutdown(self, func: LIFESPAN_FUNC):
        """
        注册停止后的函数：未实现
        Args:
            func:

        Returns:

        """
        return self.lifespan.on_after_shutdown(func)

    def on_before_restart(self, func: LIFESPAN_FUNC):
        """
        注册重启前的函数，为子进程重启时调用
        Args:
            func:

        Returns:

        """

        return self.lifespan.on_before_restart(func)

    def on_after_restart(self, func: LIFESPAN_FUNC):
        """
        注册重启后的函数：未实现
        Args:
            func:

        Returns:

        """
        return self.lifespan.on_after_restart(func)

    def on_after_nonebot_init(self, func: LIFESPAN_FUNC):
        """
        注册nonebot初始化后的函数
        Args:
            func:

        Returns:

        """
        return self.lifespan.on_after_nonebot_init(func)


_BOT_INSTANCE: Optional[LiteyukiBot] = None


def get_bot() -> Optional[LiteyukiBot]:
    """
    获取轻雪实例
    Returns:
        LiteyukiBot: 当前的轻雪实例
    """
    if IS_MAIN_PROCESS:
        return _BOT_INSTANCE
    else:
        # 从多进程上下文中获取
        pass
