import asyncio
import atexit
import os
import platform
import signal
import sys
import threading
import time
from typing import Any, Optional

from liteyuki.bot.lifespan import LIFESPAN_FUNC, Lifespan, PROCESS_LIFESPAN_FUNC
from liteyuki.comm.channel import get_channel
from liteyuki.core.manager import ProcessManager
from liteyuki.log import init_log, logger
from liteyuki.plugin import load_plugin
from liteyuki.utils import IS_MAIN_PROCESS

# new version
from liteyuki.core.manager import sub_process_manager

__all__ = [
    "LiteyukiBot",
    "get_bot",
    "get_config",
    "get_config_with_compat",
]


class LiteyukiBot:
    def __init__(self, **kwargs) -> None:
        """
        初始化轻雪实例
        Args:
            **kwargs: 配置
        """
        """常规操作"""
        print_logo()
        global _BOT_INSTANCE
        _BOT_INSTANCE = self  # 引用

        """配置"""
        self.config: dict[str, Any] = kwargs

        """初始化"""
        self.init(**self.config)  # 初始化
        logger.info("Liteyuki is initializing...")

        """生命周期管理"""
        self.lifespan = Lifespan()
        self.process_manager: ProcessManager = ProcessManager(lifespan=self.lifespan)

        """事件循环"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.stop_event = threading.Event()
        self.call_restart_count = 0

        """加载插件加载器"""
        load_plugin("liteyuki.plugins.plugin_loader")  # 加载轻雪插件

    async def _run(self):
        """
        启动逻辑
        """
        await self.lifespan.before_start()  # 启动前钩子
        sub_process_manager.start_all()
        await self.lifespan.after_start()  # 启动后钩子
        await self.keep_alive()

    def run(self):
        """
        外部启动接口
        """
        self.process_manager.start_all()
        try:
            asyncio.run(self._run())
        except KeyboardInterrupt:
            logger.opt(colors=True).info("<y>Liteyuki is stopping...</y>")
            self.stop()
        logger.opt(colors=True).info("<y>Liteyuki is stopped...</y>")

    async def keep_alive(self):
        """
        保持轻雪运行
        """
        logger.info("Liteyuki is keeping alive...")
        try:
            while not self.stop_event.is_set():
                await asyncio.sleep(0.1)
        except Exception:
            logger.info("Liteyuki is exiting...")
            self.stop()

    def restart(self, delay: int = 0):
        """
        重启轻雪本体
        Args:
            delay ([`int`](https%3A//docs.python.org/3/library/functions.html#int), optional): 延迟重启时间. Defaults to 0.
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
            threading.Thread(
                target=os.system,
                args=(f"{cmd} {executable} {' '.join(args)}",),
                daemon=True,
            ).start()
            sys.exit(0)
        self.call_restart_count += 1

    def restart_process(self, name: Optional[str] = None):
        """
        停止轻雪
        Args:
            name ([`Optional`](https%3A//docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https%3A//docs.python.org/3/library/stdtypes.html#str)]): 进程名. Defaults to None.
        Returns:
        """
        if name is not None:
            chan_active = get_channel(f"{name}-active")
            chan_active.send(1)
        else:
            for process_name in self.process_manager.processes:
                chan_active = get_channel(f"{process_name}-active")
                chan_active.send(1)

    def init(self, *args, **kwargs):
        """
        初始化轻雪, 自动调用
        Args:
            *args: 参数
            **kwargs: 关键字参数
        """
        self.init_logger()

    def init_logger(self):
        """
        初始化日志
        """
        init_log(config=self.config)

    def stop(self):
        """
        停止轻雪
        """
        self.process_manager.terminate_all()
        self.stop_event.set()

    def on_before_start(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC:
        """
        注册启动前的函数
        Args:
            func ([`LIFESPAN_FUNC`](./lifespan#var-lifespan-func)): 生命周期函数
        Returns:
            [`LIFESPAN_FUNC`](./lifespan#var-lifespan-func): 生命周期函数
        """
        return self.lifespan.on_before_start(func)

    def on_after_start(self, func: LIFESPAN_FUNC):
        """
        注册启动后的函数
        Args:
            func ([`LIFESPAN_FUNC`](./lifespan#var-lifespan-func)): 生命周期函数
        Returns:
            [`LIFESPAN_FUNC`](./lifespan#var-lifespan-func): 生命周期函数
        """
        return self.lifespan.on_after_start(func)

    def on_after_shutdown(self, func: LIFESPAN_FUNC):
        """
        注册停止后的函数：未实现
        Args:
            func ([`LIFESPAN_FUNC`](./lifespan#var-lifespan-func)): 生命周期函数
        Returns:
            [`LIFESPAN_FUNC`](./lifespan#var-lifespan-func): 生命周期函数
        """
        return self.lifespan.on_after_shutdown(func)

    def on_before_process_shutdown(self, func: PROCESS_LIFESPAN_FUNC):
        """
        注册进程停止前的函数，为子进程停止时调用
        Args:
            func ([`PROCESS_LIFESPAN_FUNC`](./lifespan#var-process-lifespan-func)): 生命周期函数
        Returns:
            [`PROCESS_LIFESPAN_FUNC`](./lifespan#var-process-lifespan-func): 生命周期函数
        """
        return self.lifespan.on_before_process_shutdown(func)

    def on_before_process_restart(
        self, func: PROCESS_LIFESPAN_FUNC
    ) -> PROCESS_LIFESPAN_FUNC:
        """
        注册进程重启前的函数，为子进程重启时调用
        Args:
            func ([`PROCESS_LIFESPAN_FUNC`](./lifespan#var-process-lifespan-func)): 生命周期函数
        Returns:
            [`PROCESS_LIFESPAN_FUNC`](./lifespan#var-process-lifespan-func): 生命周期函数
        """

        return self.lifespan.on_before_process_restart(func)

    def on_after_restart(self, func: LIFESPAN_FUNC):
        """
        注册重启后的函数：未实现
        Args:
            func ([`LIFESPAN_FUNC`](./lifespan#var-lifespan-func)): 生命周期函数
        Returns:
            [`LIFESPAN_FUNC`](./lifespan#var-lifespan-func): 生命周期函数
        """
        return self.lifespan.on_after_restart(func)


_BOT_INSTANCE: LiteyukiBot | None = None


def get_bot() -> LiteyukiBot:
    """
    获取轻雪实例
    Returns:
        [`LiteyukiBot`](#class-liteyukibot): 轻雪实例
    """

    if IS_MAIN_PROCESS:
        if _BOT_INSTANCE is None:
            raise RuntimeError("Liteyuki instance not initialized.")
        return _BOT_INSTANCE
    else:
        raise RuntimeError("Can't get bot instance in sub process.")


def get_config(key: str, default: Any = None) -> Any:
    """
    获取配置
    Args:
        key ([`str`](https%3A//docs.python.org/3/library/stdtypes.html#str)): 配置键
        default ([`Any`](https%3A//docs.python.org/3/library/functions.html#any), optional): 默认值. Defaults to None.
    Returns:
        [`Any`](https%3A//docs.python.org/3/library/functions.html#any): 配置值
    """
    return get_bot().config.get(key, default)


def get_config_with_compat(
    key: str, compat_keys: tuple[str], default: Any = None
) -> Any:
    """
    获取配置，兼容旧版本
    Args:
        key ([`str`](https%3A//docs.python.org/3/library/stdtypes.html#str)): 配置键
        compat_keys ([`tuple`](https%3A//docs.python.org/3/library/stdtypes.html#tuple)[`str`](https%3A//docs.python.org/3/library/stdtypes.html#str)): 兼容键
        default ([`Any`](https%3A//docs.python.org/3/library/functions.html#any), optional): 默认值. Defaults to None.

    Returns:
        [`Any`](https%3A//docs.python.org/3/library/functions.html#any): 配置值
    """
    if key in get_bot().config:
        return get_bot().config[key]
    for compat_key in compat_keys:
        if compat_key in get_bot().config:
            logger.warning(
                f'Config key "{compat_key}" will be deprecated, use "{key}" instead.'
            )
            return get_bot().config[compat_key]
    return default


def print_logo():
    """@litedoc-hide"""
    print(
        "\033[34m"
        + r"""
     __        ______  ________  ________  __      __  __    __  __    __  ______ 
    /  |      /      |/        |/        |/  \    /  |/  |  /  |/  |  /  |/      |
    $$ |      $$$$$$/ $$$$$$$$/ $$$$$$$$/ $$  \  /$$/ $$ |  $$ |$$ | /$$/ $$$$$$/ 
    $$ |        $$ |     $$ |   $$ |__     $$  \/$$/  $$ |  $$ |$$ |/$$/    $$ |  
    $$ |        $$ |     $$ |   $$    |     $$  $$/   $$ |  $$ |$$  $$<     $$ |  
    $$ |        $$ |     $$ |   $$$$$/       $$$$/    $$ |  $$ |$$$$$  \    $$ |  
    $$ |_____  _$$ |_    $$ |   $$ |_____     $$ |    $$ \__$$ |$$ |$$  \  _$$ |_ 
    $$       |/ $$   |   $$ |   $$       |    $$ |    $$    $$/ $$ | $$  |/ $$   |
    $$$$$$$$/ $$$$$$/    $$/    $$$$$$$$/     $$/      $$$$$$/  $$/   $$/ $$$$$$/ 
                """
        + "\033[0m"
    )
