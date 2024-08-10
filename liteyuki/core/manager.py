# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/7/27 上午11:12
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : manager.py
@Software: PyCharm
"""
import asyncio
import threading
from multiprocessing import Process
from typing import TYPE_CHECKING

from liteyuki.comm import Channel, get_channel, set_channels
from liteyuki.log import logger

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

        set_channels({
                "nonebot-active" : Channel(_id="nonebot-active"),
                "melobot-active" : Channel(_id="melobot-active"),
                "nonebot-passive": Channel(_id="nonebot-passive"),
                "melobot-passive": Channel(_id="melobot-passive"),
        })

    def start(self, name: str, delay: int = 0):
        """
        开启后自动监控进程，并添加到进程字典中
        Args:
            name:
            delay:

        Returns:

        """
        if name not in self.targets:
            raise KeyError(f"Process {name} not found.")

        def _start():
            should_exit = False
            while not should_exit:
                chan_active = get_channel(f"{name}-active")
                chan_passive = get_channel(f"{name}-passive")
                process = Process(target=self.targets[name][0], args=(chan_active, chan_passive, *self.targets[name][1]),
                                  kwargs=self.targets[name][2])
                self.processes[name] = process
                process.start()
                while not should_exit:
                    # 0退出 1重启
                    data = chan_active.receive()
                    if data == 1:
                        logger.info(f"Restarting process {name}")
                        asyncio.run(self.bot.lifespan.before_shutdown())
                        asyncio.run(self.bot.lifespan.before_restart())
                        self.terminate(name)
                        break

                    elif data == 0:
                        logger.info(f"Stopping process {name}")
                        asyncio.run(self.bot.lifespan.before_shutdown())
                        should_exit = True
                        self.terminate(name)
                    else:
                        logger.warning("Unknown data received, ignored.")

        if delay:
            threading.Timer(delay, _start).start()
        else:
            threading.Thread(target=_start).start()

    def add_target(self, name: str, target, *args, **kwargs):
        self.targets[name] = (target, args, kwargs)

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

    def terminate_all(self):
        for name in self.targets:
            self.terminate(name)
