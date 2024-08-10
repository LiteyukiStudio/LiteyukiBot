# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/7/26 下午11:21
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : channel.py
@Software: PyCharm

本模块定义了一个通用的通道类，用于进程间通信
"""
import functools
import multiprocessing
import threading
from multiprocessing import Pipe
from typing import Any, Optional, Callable, Awaitable, List, TypeAlias
from uuid import uuid4

from liteyuki.utils import is_coroutine_callable, run_coroutine

SYNC_ON_RECEIVE_FUNC: TypeAlias = Callable[[Any], Any]
ASYNC_ON_RECEIVE_FUNC: TypeAlias = Callable[[Any], Awaitable[Any]]
ON_RECEIVE_FUNC: TypeAlias = SYNC_ON_RECEIVE_FUNC | ASYNC_ON_RECEIVE_FUNC

SYNC_FILTER_FUNC: TypeAlias = Callable[[Any], bool]
ASYNC_FILTER_FUNC: TypeAlias = Callable[[Any], Awaitable[bool]]
FILTER_FUNC: TypeAlias = SYNC_FILTER_FUNC | ASYNC_FILTER_FUNC

IS_MAIN_PROCESS = multiprocessing.current_process().name == "MainProcess"

_channel: dict[str, "Channel"] = {}
_callback_funcs: dict[str, ON_RECEIVE_FUNC] = {}


class Channel:
    """
    通道类，用于进程间通信，进程内不可用，仅限主进程和子进程之间通信
    有两种接收工作方式，但是只能选择一种，主动接收和被动接收，主动接收使用 `receive` 方法，被动接收使用 `on_receive` 装饰器
    """

    def __init__(self, _id: str):
        self.main_send_conn, self.sub_receive_conn = Pipe()
        self.sub_send_conn, self.main_receive_conn = Pipe()
        self._closed = False
        self._on_main_receive_funcs: list[str] = []
        self._on_sub_receive_funcs: list[str] = []
        self.name: str = _id

        self.is_main_receive_loop_running = False
        self.is_sub_receive_loop_running = False

    def __str__(self):
        return f"Channel({self.name})"

    def send(self, data: Any):
        """
        发送数据
        Args:
            data: 数据
        """
        if self._closed:
            raise RuntimeError("Cannot send to a closed channel")
        if IS_MAIN_PROCESS:
            print("主进程发送数据：", data)
            self.main_send_conn.send(data)
        else:
            print("子进程发送数据：", data)
            self.sub_send_conn.send(data)

    def receive(self) -> Any:
        """
        接收数据
        Args:
        """
        if self._closed:
            raise RuntimeError("Cannot receive from a closed channel")

        while True:
            # 判断receiver是否为None或者receiver是否等于接收者，是则接收数据，否则不动数据
            if IS_MAIN_PROCESS:
                data = self.main_receive_conn.recv()
                print("主进程接收数据：", data)
            else:
                data = self.sub_receive_conn.recv()
                print("子进程接收数据：", data)

            return data

    def close(self):
        """
        关闭通道
        """
        self._closed = True
        self.sub_receive_conn.close()
        self.main_send_conn.close()
        self.sub_send_conn.close()
        self.main_receive_conn.close()

    def on_receive(self, filter_func: Optional[FILTER_FUNC] = None) -> Callable[[ON_RECEIVE_FUNC], ON_RECEIVE_FUNC]:
        """
        接收数据并执行函数
        Args:
            filter_func: 过滤函数，为None则不过滤
        Returns:
            装饰器，装饰一个函数在接收到数据后执行
        """
        if (not self.is_sub_receive_loop_running) and not IS_MAIN_PROCESS:
            threading.Thread(target=self._start_sub_receive_loop).start()

        if (not self.is_main_receive_loop_running) and IS_MAIN_PROCESS:
            threading.Thread(target=self._start_main_receive_loop).start()

        def decorator(func: ON_RECEIVE_FUNC) -> ON_RECEIVE_FUNC:
            async def wrapper(data: Any) -> Any:
                if filter_func is not None:
                    if is_coroutine_callable(filter_func):
                        if not await filter_func(data):
                            return
                    else:
                        if not filter_func(data):
                            return
                return await func(data)

            function_id = str(uuid4())
            _callback_funcs[function_id] = wrapper
            if IS_MAIN_PROCESS:
                self._on_main_receive_funcs.append(function_id)
            else:
                self._on_sub_receive_funcs.append(function_id)
            return func

        return decorator

    def _run_on_main_receive_funcs(self, data: Any):
        """
        运行接收函数
        Args:
            data: 数据
        """
        for func_id in self._on_main_receive_funcs:
            func = _callback_funcs[func_id]
            run_coroutine(func(data))

    def _run_on_sub_receive_funcs(self, data: Any):
        """
        运行接收函数
        Args:
            data: 数据
        """
        for func_id in self._on_sub_receive_funcs:
            func = _callback_funcs[func_id]
            run_coroutine(func(data))

    def _start_main_receive_loop(self):
        """
        开始接收数据
        """
        self.is_main_receive_loop_running = True
        while not self._closed:
            data = self.main_receive_conn.recv()
            self._run_on_main_receive_funcs(data)

    def _start_sub_receive_loop(self):
        """
        开始接收数据
        """
        self.is_sub_receive_loop_running = True
        while not self._closed:
            data = self.sub_receive_conn.recv()
            self._run_on_sub_receive_funcs(data)

    def __iter__(self):
        return self

    def __next__(self) -> Any:
        return self.receive()


"""默认通道实例，可直接从模块导入使用"""
chan = Channel("default")


def set_channel(name: str, channel: Channel):
    """
    设置通道实例
    Args:
        name: 通道名称
        channel: 通道实例
    """
    _channel[name] = channel


def set_channels(channels: dict[str, Channel]):
    """
    设置通道实例
    Args:
        channels: 通道名称
    """
    for name, channel in channels.items():
        _channel[name] = channel


def get_channel(name: str) -> Optional[Channel]:
    """
    获取通道实例
    Args:
        name: 通道名称
    Returns:
    """
    return _channel.get(name, None)


def get_channels() -> dict[str, Channel]:
    """
    获取通道实例
    Returns:
    """
    return _channel
