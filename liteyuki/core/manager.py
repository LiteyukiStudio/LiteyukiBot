# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/7/27 上午11:12
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : manager.py
@Software: PyCharm
"""
import threading
from multiprocessing import Process

from liteyuki.comm import Channel
from liteyuki.log import logger

TIMEOUT = 10

__all__ = [
        "ProcessManager"
]


class ProcessManager:
    """
    在主进程中被调用
    """

    def __init__(self, bot, chan: Channel):
        self.bot = bot
        self.chan = chan
        self.processes: dict[str, tuple[callable, tuple, dict]] = {}

    def start(self, name: str, delay: int = 0):
        """
        开启后自动监控进程
        Args:
            name:
            delay:

        Returns:

        """

        if name not in self.processes:
            raise KeyError(f"Process {name} not found.")

        def _start():
            should_exit = False
            while not should_exit:
                process = Process(target=self.processes[name][0], args=(self.chan, *self.processes[name][1]), kwargs=self.processes[name][2])
                process.start()
                while not should_exit:
                    # 0退出 1重启
                    data = self.chan.receive(name)
                    print("Received data: ", data, name)
                    if data == 1:
                        logger.info("Restarting LiteyukiBot...")
                        process.terminate()
                        process.join(TIMEOUT)
                        if process.is_alive():
                            process.kill()
                        break

                    elif data == 0:
                        logger.info("Stopping LiteyukiBot...")
                        should_exit = True
                        process.terminate()
                        process.join(TIMEOUT)
                        if process.is_alive():
                            process.kill()
                    else:
                        logger.warning("Unknown data received, ignored.")

        if delay:
            threading.Timer(delay, _start).start()
        else:
            threading.Thread(target=_start).start()

    def add_target(self, name: str, target, *args, **kwargs):
        self.processes[name] = (target, args, kwargs)

    def join(self):
        for name, process in self.processes:
            process.join()

    def terminate(self):
        for name, process in self.processes:
            process.terminate()
            process.join(TIMEOUT)
            if process.is_alive():
                process.kill()
        self.processes = []
