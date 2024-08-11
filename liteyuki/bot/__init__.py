import asyncio
import os
import platform
import sys
import threading
import time
from typing import Any, Iterable, Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from liteyuki.bot.lifespan import (LIFESPAN_FUNC, Lifespan)
from liteyuki.comm import get_channel
from liteyuki.core import IS_MAIN_PROCESS
from liteyuki.core.manager import ProcessManager
from liteyuki.log import init_log, logger
from liteyuki.plugin import load_plugins

__all__ = [
        "LiteyukiBot",
        "get_bot",
        "get_config",
]


class LiteyukiBot:
    def __init__(self, *args, **kwargs):
        global _BOT_INSTANCE
        _BOT_INSTANCE = self  # 引用

        self.lifespan = Lifespan()

        self.config: dict[str, Any] = kwargs

        self.init(**self.config)  # 初始化

        self.process_manager: ProcessManager = ProcessManager(bot=self)
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop_thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.stop_event = threading.Event()
        self.call_restart_count = 0

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
        load_plugins("liteyuki/plugins")  # 加载轻雪插件
        logger.info("Liteyuki is initializing...")

    def run(self):
        """
        启动逻辑
        """
        self.loop_thread.start()  # 启动事件循环
        asyncio.run(self.lifespan.before_start())  # 启动前钩子

        asyncio.run(self.lifespan.after_start())  # 启动后钩子
        self.start_watcher()  # 启动文件监视器,后续准备插件化
        self.keep_running()

    def start_watcher(self):
        pass

    def restart(self, delay: int = 0):
        """
        重启轻雪本体
        Returns:

        """

        if self.call_restart_count < 1:
            executable = sys.executable
            args = sys.argv
            logger.info("Restarting LiteyukiBot...")
            time.sleep(delay)
            if platform.system() == "Windows":
                cmd = "start"
            elif platform.system() == "Linux":
                cmd = "nohup"
            elif platform.system() == "Darwin":
                cmd = "open"
            else:
                cmd = "nohup"
            self.process_manager.terminate_all()
            # 进程退出后重启
            threading.Thread(target=os.system, args=(f"{cmd} {executable} {' '.join(args)}",)).start()
            sys.exit(0)
        self.call_restart_count += 1

    def restart_process(self, name: Optional[str] = None):
        """
        停止轻雪
        Args:
            name: 进程名称, 默认为None, 所有进程
        Returns:

        """
        logger.info(f"Stopping process {name}...")

        self.loop.create_task(self.lifespan.before_shutdown())  # 重启前钩子
        self.loop.create_task(self.lifespan.before_shutdown())  # 停止前钩子

        # if name:
        #     self.process_manager.terminate(name)
        # else:
        #     self.process_manager.terminate_all()
        if name:
            chan_active = get_channel(f"{name}-active")
            chan_active.send(1)
        else:
            for process_name in self.process_manager.processes:
                chan_active = get_channel(f"{process_name}-active")
                chan_active.send(1)

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

    def keep_running(self):
        self.stop_event.wait()


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


def get_config(key: str, default: Any = None) -> Any:
    """
    获取配置
    Args:
        key: 配置键
        default: 默认值

    Returns:
        Any: 配置值
    """
    return _BOT_INSTANCE.config.get(key, default)


def get_config_with_compat(key: str, compat_keys: tuple[str], default: Any = None) -> Any:
    """
    获取配置，兼容旧版本
    Args:
        key: 配置键
        compat_keys: 兼容键
        default: 默认值

    Returns:
        Any: 配置值
    """
    if key in _BOT_INSTANCE.config:
        return _BOT_INSTANCE.config[key]
    for compat_key in compat_keys:
        if compat_key in _BOT_INSTANCE.config:
            logger.warning(f"Config key {compat_key} will be deprecated, use {key} instead.")
            return _BOT_INSTANCE.config[compat_key]
    return default

