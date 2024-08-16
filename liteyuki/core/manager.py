# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/7/27 上午11:12
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : manager.py
@Software: PyCharm
"""

import atexit
import signal
import sys
import threading
from multiprocessing import Process
from typing import Any, Callable, TYPE_CHECKING, TypeAlias

from liteyuki.comm import Channel, get_channel, set_channels
from liteyuki.comm.storage import shared_memory
from liteyuki.log import logger
from liteyuki.utils import IS_MAIN_PROCESS

TARGET_FUNC: TypeAlias = Callable[..., Any]

if TYPE_CHECKING:
    from liteyuki.bot import LiteyukiBot
    from liteyuki.comm.storage import KeyValueStore

TIMEOUT = 10

__all__ = [
        "ProcessManager"
]


# Update the delivery_channel_wrapper function to return the top-level wrapper
def _delivery_channel_wrapper(func: TARGET_FUNC, chan_active: Channel, chan_passive: Channel, sm: "KeyValueStore", *args, **kwargs):
    """
    子进程入口函数
    """
    # 给子进程设置通道
    if IS_MAIN_PROCESS:
        raise RuntimeError("Function should only be called in a sub process.")

    from liteyuki.comm import channel
    channel.active_channel = chan_active
    channel.passive_channel = chan_passive

    # 给子进程创建共享内存实例
    from liteyuki.comm import storage
    storage.shared_memory = sm

    func(*args, **kwargs)


class ProcessManager:
    """
    进程管理器
    """

    def __init__(self, bot: "LiteyukiBot"):
        self.bot = bot
        self.targets: dict[str, tuple[callable, tuple, dict]] = {}
        self.processes: dict[str, Process] = {}

    def start(self, name: str):
        """
        开启后自动监控进程，并添加到进程字典中
        Args:
            name:
        Returns:

        """
        if name not in self.targets:
            raise KeyError(f"Process {name} not found.")

        chan_active = get_channel(f"{name}-active")

        def _start_process():
            process = Process(target=self.targets[name][0], args=self.targets[name][1],
                              kwargs=self.targets[name][2], daemon=True)
            self.processes[name] = process
            process.start()

        # 启动进程并监听信号
        _start_process()

        while True:
            data = chan_active.receive()
            if data == 0:
                # 停止
                logger.info(f"Stopping process {name}")
                self.bot.lifespan.before_process_shutdown()
                self.terminate(name)
                break
            elif data == 1:
                # 重启
                logger.info(f"Restarting process {name}")
                self.bot.lifespan.before_process_shutdown()
                self.bot.lifespan.before_process_restart()
                self.terminate(name)
                _start_process()
                continue
            else:
                logger.warning("Unknown data received, ignored.")

    def start_all(self):
        """
        启动所有进程
        """
        for name in self.targets:
            threading.Thread(target=self.start, args=(name,), daemon=True).start()

    def add_target(self, name: str, target: TARGET_FUNC, args: tuple = (), kwargs=None):
        """
        添加进程
        Args:
            name: 进程名，用于获取和唯一标识
            target: 进程函数
            args: 进程函数参数
            kwargs: 进程函数关键字参数，通常会默认传入chan_active和chan_passive
        """
        if kwargs is None:
            kwargs = {}
        chan_active = Channel(_id=f"{name}-active")
        chan_passive = Channel(_id=f"{name}-passive")

        self.targets[name] = (_delivery_channel_wrapper, (target, chan_active, chan_passive, shared_memory, *args), kwargs)
        # 主进程通道
        set_channels(
            {
                    f"{name}-active" : chan_active,
                    f"{name}-passive": chan_passive
            }
        )

    def join_all(self):
        for name, process in self.targets:
            process.join()

    def terminate(self, name: str):
        """
        终止进程并从进程字典中删除
        Args:
            name:

        Returns:

        """
        if name not in self.processes:
            logger.warning(f"Process {name} not found.")
            return
        process = self.processes[name]
        process.terminate()
        process.join(TIMEOUT)
        if process.is_alive():
            process.kill()
        logger.success(f"Process {name} terminated.")

    def terminate_all(self):
        for name in self.targets:
            self.terminate(name)

    def is_process_alive(self, name: str) -> bool:
        """
        检查进程是否存活
        Args:
            name:

        Returns:

        """
        if name not in self.targets:
            raise logger.warning(f"Process {name} not found.")
        return self.processes[name].is_alive()
