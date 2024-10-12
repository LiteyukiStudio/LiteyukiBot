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
import multiprocessing
import threading
from multiprocessing import Process
from typing import Any, Callable, TYPE_CHECKING, TypeAlias

from croterline.context import Context
from croterline.process import SubProcess, ProcessFuncType

from liteyuki.log import logger
from liteyuki.utils import IS_MAIN_PROCESS

if TYPE_CHECKING:
    from liteyuki.bot.lifespan import Lifespan
    from liteyuki.comm.storage import KeyValueStore

from liteyuki.comm import Channel

if IS_MAIN_PROCESS:
    from liteyuki.comm.channel import get_channel, publish_channel, get_channels
    from liteyuki.comm.storage import shared_memory
    from liteyuki.comm.channel import (
        channel_deliver_active_channel,
        channel_deliver_passive_channel,
    )
else:
    from liteyuki.comm import channel
    from liteyuki.comm import storage

TARGET_FUNC: TypeAlias = Callable[..., Any]
TIMEOUT = 10

__all__ = ["ProcessManager", "sub_process_manager"]
multiprocessing.set_start_method("spawn", force=True)


class ChannelDeliver:
    def __init__(
        self,
        active: Channel[Any],
        passive: Channel[Any],
        channel_deliver_active: Channel[Channel[Any]],
        channel_deliver_passive: Channel[tuple[str, dict]],
        publish: Channel[tuple[str, Any]],
    ):
        self.active = active
        self.passive = passive
        self.channel_deliver_active = channel_deliver_active
        self.channel_deliver_passive = channel_deliver_passive
        self.publish = publish


# 函数处理一些跨进程通道的
def _delivery_channel_wrapper(
    func: TARGET_FUNC, cd: ChannelDeliver, sm: "KeyValueStore", *args, **kwargs
):
    """
    子进程入口函数
    处理一些操作
    """
    # 给子进程设置通道
    if IS_MAIN_PROCESS:
        raise RuntimeError("Function should only be called in a sub process.")

    channel.active_channel = cd.active  # 子进程主动通道
    channel.passive_channel = cd.passive  # 子进程被动通道
    channel.channel_deliver_active_channel = (
        cd.channel_deliver_active
    )  # 子进程通道传递主动通道
    channel.channel_deliver_passive_channel = (
        cd.channel_deliver_passive
    )  # 子进程通道传递被动通道
    channel.publish_channel = cd.publish  # 子进程发布通道

    # 给子进程创建共享内存实例

    storage.shared_memory = sm

    func(*args, **kwargs)


class ProcessManager:
    """
    进程管理器
    """

    def __init__(self, lifespan: "Lifespan"):
        self.lifespan = lifespan
        self.targets: dict[str, tuple[Callable, tuple, dict]] = {}
        self.processes: dict[str, Process] = {}

    def _run_process(self, name: str):
        """
        开启后自动监控进程，并添加到进程字典中，会阻塞，请创建task
        Args:
            name:
        Returns:
        """
        if name not in self.targets:
            raise KeyError(f"Process {name} not found.")

        chan_active = get_channel(f"{name}-active")

        def _start_process():
            process = Process(
                target=self.targets[name][0],
                args=self.targets[name][1],
                kwargs=self.targets[name][2],
                daemon=True,
            )
            self.processes[name] = process
            process.start()

        # 启动进程并监听信号
        _start_process()
        while True:
            data = chan_active.receive()
            if data == 0:
                # 停止
                logger.info(f"Stopping process {name}")
                self.terminate(name)
                break
            elif data == 1:
                # 重启
                logger.info(f"Restarting process {name}")
                self.terminate(name)
                _start_process()
                continue
            else:
                logger.warning("Unknown data received, ignored.")

    def start_all(self):
        """
        对外启动方法，启动所有进程，创建asyncio task
        """
        # [asyncio.create_task(self._run_process(name)) for name in self.targets]

        for name in self.targets:
            logger.debug(f"Starting process {name}")
            threading.Thread(
                target=self._run_process, args=(name,), daemon=True
            ).start()

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
        chan_active: Channel = Channel(name=f"{name}-active")
        chan_passive: Channel = Channel(name=f"{name}-passive")

        channel_deliver = ChannelDeliver(
            active=chan_active,
            passive=chan_passive,
            channel_deliver_active=channel_deliver_active_channel,
            channel_deliver_passive=channel_deliver_passive_channel,
            publish=publish_channel,
        )

        self.targets[name] = (
            _delivery_channel_wrapper,
            (target, channel_deliver, shared_memory, *args),
            kwargs,
        )
        # 主进程通道

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
            logger.warning(f"Process {name} not found.")
        return self.processes[name].is_alive()


# new version


class _SubProcessManager:

    def __init__(self):
        self.processes: dict[str, SubProcess] = {}

    def new_process(
        self, name: str, *args, **kwargs
    ) -> Callable[[ProcessFuncType], None]:
        def decorator(func: ProcessFuncType):
            self.processes[name] = SubProcess(name, func, *args, **kwargs)

        return decorator

    def add(self, name: str, func: ProcessFuncType, *args, **kwargs):
        """
        添加子进程
        Args:
            func: 子进程函数
            name: 子进程名称
            args: 子进程函数参数
            kwargs: 子进程函数关键字参数
        Returns:
        """
        self.processes[name] = SubProcess(name, func, *args, **kwargs)

    def start(self, name: str):
        """
        启动指定子进程
        Args:
            name: 子进程名称
        Returns:
        """
        if name not in self.processes:
            raise KeyError(f"Process {name} not found.")
        self.processes[name].start()

    def start_all(self):
        """
        启动所有子进程
        """
        for name, process in self.processes.items():
            process.start()
            logger.debug(f"Starting process {name}")


sub_process_manager = _SubProcessManager()
