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
import threading
import signal
from multiprocessing import Process
from typing import Any, Callable, Optional, Protocol, TYPE_CHECKING, TypeAlias

from liteyuki.comm import Channel, get_channel, set_channels
from liteyuki.log import logger

TARGET_FUNC: TypeAlias = Callable[[Channel, Channel, ...], Any]

if TYPE_CHECKING:
    from liteyuki.bot import LiteyukiBot

TIMEOUT = 10

__all__ = [
        "ProcessManager"
]


class ProcessManager:
    """
    在主进程中被调用
    """

    def __init__(self, bot: "LiteyukiBot"):
        self.bot = bot
        self.targets: dict[str, tuple[callable, tuple, dict]] = {}
        self.processes: dict[str, Process] = {}

        atexit.register(self.terminate_all)
        signal.signal(signal.SIGINT, self._handle_exit)
        signal.signal(signal.SIGTERM, self._handle_exit)

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
                              kwargs=self.targets[name][2])
            self.processes[name] = process

            process.start()

        # 启动进程并监听信号
        _start_process()

        def _start_monitor():
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

        _start_monitor()

    def start_all(self):
        """
        启动所有进程
        """
        for name in self.targets:
            threading.Thread(target=self.start, args=(name,), daemon=True).start()

    def _handle_exit(self, signum, frame):
        logger.info("Received signal, stopping all processes.")
        self.terminate_all()
        exit(0)

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
        kwargs["chan_active"] = chan_active
        kwargs["chan_passive"] = chan_passive
        self.targets[name] = (target, args, kwargs)
        set_channels(
            {
                    f"{name}-active" : chan_active,
                    f"{name}-passive": chan_passive
            }
        )

    def join(self):
        for name, process in self.targets:
            process.join()

    def terminate(self, name: str):
        """
        终止进程并从进程字典中删除
        Args:
            name:

        Returns:

        """
        if name not in self.targets:
            raise logger.warning(f"Process {name} not found.")
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
