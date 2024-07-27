import asyncio
import multiprocessing
import time
from typing import Any, Coroutine, Optional

import nonebot

import liteyuki
from liteyuki.plugin.load import load_plugin, load_plugins
from liteyuki.utils import run_coroutine
from liteyuki.log import logger, init_log

from src.utils import (
    adapter_manager,
    driver_manager,
)

from liteyuki.bot.lifespan import (
    Lifespan,
    LIFESPAN_FUNC,
)

from liteyuki.core.spawn_process import nb_run, ProcessingManager

__all__ = [
        "LiteyukiBot",
        "get_bot"
]

"""是否为主进程"""
IS_MAIN_PROCESS = multiprocessing.current_process().name == "MainProcess"


class LiteyukiBot:
    def __init__(self, *args, **kwargs):
        global _BOT_INSTANCE
        _BOT_INSTANCE = self  # 引用
        if not IS_MAIN_PROCESS:
            self.config: dict[str, Any] = kwargs
            self.lifespan: Lifespan = Lifespan()
            self.init(**self.config)  # 初始化
        else:
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

    def run(self, *args, **kwargs):
        if IS_MAIN_PROCESS:
            self._run_nb_in_spawn_process(*args, **kwargs)
        else:
            # 子进程启动
            load_plugins("liteyuki/plugins")  # 加载轻雪插件
            driver_manager.init(config=self.config)
            adapter_manager.init(self.config)
            adapter_manager.register()
            nonebot.load_plugin("src.liteyuki_main")
            run_coroutine(self.lifespan.after_start())  # 启动前

    def _run_nb_in_spawn_process(self, *args, **kwargs):
        """
        在新的进程中运行nonebot.run方法，该函数在主进程中被调用
        Args:
            *args:
            **kwargs:

        Returns:
        """
        if IS_MAIN_PROCESS:
            timeout_limit: int = 20
            should_exit = False

            while not should_exit:
                ctx = multiprocessing.get_context("spawn")
                event = ctx.Event()
                ProcessingManager.event = event
                process = ctx.Process(
                    target=nb_run,
                    args=(event,) + args,
                    kwargs=kwargs,
                )
                process.start()  # 启动进程

                while not should_exit:
                    if ProcessingManager.event.wait(1):
                        logger.info("Receive reboot event")
                        process.terminate()
                        process.join(timeout_limit)
                        if process.is_alive():
                            logger.warning(
                                f"Process {process.pid} is still alive after {timeout_limit} seconds, force kill it."
                            )
                            process.kill()
                        break
                    elif process.is_alive():
                        liteyuki.chan.send("轻雪进程正常运行", "sub")
                        continue
                    else:
                        should_exit = True

    def restart(self):
        """
        停止轻雪
        Returns:

        """
        logger.info("Stopping LiteyukiBot...")
        logger.debug("Running before_restart functions...")
        run_coroutine(self.lifespan.before_restart())
        logger.debug("Running before_shutdown functions...")
        run_coroutine(self.lifespan.before_shutdown())

        ProcessingManager.restart()

    def init(self, *args, **kwargs):
        """
        初始化轻雪, 自动调用
        Returns:

        """
        self.init_config()
        self.init_logger()
        if not IS_MAIN_PROCESS:
            nonebot.init(**kwargs)
            asyncio.run(self.lifespan.after_nonebot_init())

    def init_logger(self):
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
        注册停止前的函数
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
        注册重启前的函数
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
    return _BOT_INSTANCE
