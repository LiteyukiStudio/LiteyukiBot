import asyncio
import multiprocessing
from typing import Any, Coroutine, Optional

import nonebot

import liteyuki
from liteyuki.plugin.load import load_plugin, load_plugins
from src.utils import (
    adapter_manager,
    driver_manager,
)
from src.utils.base.log import logger
from liteyuki.bot.lifespan import (
    Lifespan,
    LIFESPAN_FUNC,
)
from liteyuki.core.spawn_process import nb_run, ProcessingManager

__all__ = [
        "LiteyukiBot",
        "get_bot"
]

_MAIN_PROCESS = multiprocessing.current_process().name == "MainProcess"


class LiteyukiBot:
    def __init__(self, *args, **kwargs):

        global _BOT_INSTANCE
        _BOT_INSTANCE = self  # 引用
        self.running = False
        self.config: dict[str, Any] = kwargs
        self.lifespan: Lifespan = Lifespan()
        self.init(**self.config)  # 初始化

        if not _MAIN_PROCESS:
            pass
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
        if _MAIN_PROCESS:
            load_plugins("liteyuki/plugins")
            asyncio.run(self.lifespan.before_start())
            self._run_nb_in_spawn_process(*args, **kwargs)
        else:
            # 子进程启动

            driver_manager.init(config=self.config)
            adapter_manager.init(self.config)
            adapter_manager.register()
            nonebot.load_plugin("src.liteyuki_main")

    def _run_nb_in_spawn_process(self, *args, **kwargs):
        """
        在新的进程中运行nonebot.run方法
        Args:
            *args:
            **kwargs:

        Returns:
        """

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

            asyncio.run(self.lifespan.after_start())

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
                    continue
                else:
                    should_exit = True

    @staticmethod
    def _run_coroutine(*coro: Coroutine):
        """
        运行协程
        Args:
            coro:

        Returns:

        """
        # 检测是否有现有的事件循环
        new_loop = False
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            new_loop = True
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if new_loop:
            for c in coro:
                loop.run_until_complete(c)
            loop.close()

        else:
            for c in coro:
                loop.create_task(c)

    @property
    def status(self) -> int:
        """
        获取轻雪状态
        Returns:
            int: 0:未启动 1:运行中
        """
        return 1 if self.running else 0

    def restart(self):
        """
        停止轻雪
        Returns:

        """
        logger.info("Stopping LiteyukiBot...")

        logger.debug("Running before_restart functions...")
        self._run_coroutine(self.lifespan.before_restart())
        logger.debug("Running before_shutdown functions...")
        self._run_coroutine(self.lifespan.before_shutdown())

        ProcessingManager.restart()
        self.running = False

    def init(self, *args, **kwargs):
        """
        初始化轻雪, 自动调用
        Returns:

        """
        self.init_config()
        self.init_logger()
        if not _MAIN_PROCESS:
            nonebot.init(**kwargs)
            asyncio.run(self.lifespan.after_nonebot_init())

    def init_logger(self):
        from src.utils.base.log import init_log
        init_log()

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
