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
import threading
from multiprocessing import Queue
from queue import Empty, Full
from typing import Any, Awaitable, Callable, List, Optional, TypeAlias

from nonebot import logger

from liteyuki.utils import is_coroutine_callable, run_coroutine

SYNC_ON_RECEIVE_FUNC: TypeAlias = Callable[[Any], Any]
ASYNC_ON_RECEIVE_FUNC: TypeAlias = Callable[[Any], Awaitable[Any]]
ON_RECEIVE_FUNC: TypeAlias = SYNC_ON_RECEIVE_FUNC | ASYNC_ON_RECEIVE_FUNC

SYNC_FILTER_FUNC: TypeAlias = Callable[[Any], bool]
ASYNC_FILTER_FUNC: TypeAlias = Callable[[Any], Awaitable[bool]]
FILTER_FUNC: TypeAlias = SYNC_FILTER_FUNC | ASYNC_FILTER_FUNC


class Channel:
    def __init__(self, buffer_size: int = 0):
        self._queue = Queue(buffer_size)
        self._closed = False
        self._on_receive_funcs: List[ON_RECEIVE_FUNC] = []
        self._on_receive_funcs_with_receiver: dict[str, List[ON_RECEIVE_FUNC]] = {}

        self._receiving_thread = threading.Thread(target=self._start_receiver, daemon=True)
        self._receiving_thread.start()

    def send(
            self,
            data: Any,
            receiver: Optional[str] = None,
            block: bool = True,
            timeout: Optional[float] = None
    ):
        """
        发送数据
        Args:
            data: 数据
            receiver: 接收者，如果为None则广播
            block: 是否阻塞
            timeout: 超时时间

        Returns:

        """
        print(f"send {data} -> {receiver}")
        if self._closed:
            raise RuntimeError("Cannot send to a closed channel")
        try:
            self._queue.put((data, receiver), block, timeout)
        except Full:
            logger.warning("Channel buffer is full, send operation is blocked")

    def receive(
            self,
            receiver: str = None,
            block: bool = True,
            timeout: Optional[float] = None
    ) -> Any:
        """
        接收数据
        Args:
            receiver: 接收者，如果为None则接收任意数据
            block: 是否阻塞
            timeout: 超时时间

        Returns:

        """
        if self._closed:
            raise RuntimeError("Cannot receive from a closed channel")
        try:
            while True:
                data, data_receiver = self._queue.get(block, timeout)
                if receiver is None or receiver == data_receiver:
                    return data
        except Empty:
            if not block:
                return None
            raise

    def close(self):
        """
        关闭通道
        Returns:

        """
        self._closed = True
        self._queue.close()
        while not self._queue.empty():
            self._queue.get()

    def on_receive(
            self,
            filter_func: Optional[FILTER_FUNC] = None,
            receiver: Optional[str] = None,
    ) -> Callable[[ON_RECEIVE_FUNC], ON_RECEIVE_FUNC]:
        """
        接收数据并执行函数
        Args:
            filter_func: 过滤函数，为None则不过滤
            receiver: 接收者, 为None则接收任意数据
        Returns:
            装饰器，装饰一个函数在接收到数据后执行
        """

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

            if receiver is None:
                self._on_receive_funcs.append(wrapper)
            else:
                if receiver not in self._on_receive_funcs_with_receiver:
                    self._on_receive_funcs_with_receiver[receiver] = []
                self._on_receive_funcs_with_receiver[receiver].append(wrapper)
            return func

        return decorator

    def _start_receiver(self):
        """
        使用多线程启动接收循环，在通道实例化时自动启动
        Returns:
        """
        while True:
            data, receiver = self._queue.get(block=True, timeout=None)
            self._run_on_receive_funcs(data, receiver)

    def _run_on_receive_funcs(self, data: Any, receiver: Optional[str] = None):
        """
        运行接收函数
        Args:
            data: 数据
        Returns:

        """
        if receiver is None:
            for func in self._on_receive_funcs:
                run_coroutine(func(data))
        else:
            for func in self._on_receive_funcs_with_receiver.get(receiver, []):
                run_coroutine(func(data))

    def __iter__(self):
        return self

    def __next__(self, timeout: Optional[float] = None) -> Any:
        return self.receive(block=True, timeout=timeout)


"""默认通道实例，可直接从模块导入使用"""
chan = Channel()
