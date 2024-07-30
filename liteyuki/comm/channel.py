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
from multiprocessing import Pipe
from typing import Any, Optional, Callable, Awaitable, List, TypeAlias

from liteyuki.utils import is_coroutine_callable, run_coroutine

SYNC_ON_RECEIVE_FUNC: TypeAlias = Callable[[Any], Any]
ASYNC_ON_RECEIVE_FUNC: TypeAlias = Callable[[Any], Awaitable[Any]]
ON_RECEIVE_FUNC: TypeAlias = SYNC_ON_RECEIVE_FUNC | ASYNC_ON_RECEIVE_FUNC

SYNC_FILTER_FUNC: TypeAlias = Callable[[Any], bool]
ASYNC_FILTER_FUNC: TypeAlias = Callable[[Any], Awaitable[bool]]
FILTER_FUNC: TypeAlias = SYNC_FILTER_FUNC | ASYNC_FILTER_FUNC


class Channel:
    """
    通道类，用于进程间通信
    有两种接收工作方式，但是只能选择一种，主动接收和被动接收，主动接收使用 `receive` 方法，被动接收使用 `on_receive` 装饰器
    """

    def __init__(self):
        self.receive_conn, self.send_conn = Pipe()
        self._closed = False
        self._on_receive_funcs: List[ON_RECEIVE_FUNC] = []
        self._on_receive_funcs_with_receiver: dict[str, List[ON_RECEIVE_FUNC]] = {}

    def send(self, data: Any, receiver: Optional[str] = None):
        """
        发送数据
        Args:
            data: 数据
            receiver: 接收者，如果为None则广播
        """
        if self._closed:
            raise RuntimeError("Cannot send to a closed channel")
        self.send_conn.send((data, receiver))

    def receive(self, receiver: str = None) -> Any:
        """
        接收数据
        Args:
            receiver: 接收者，如果为None则接收任意数据
        """
        if self._closed:
            raise RuntimeError("Cannot receive from a closed channel")
        while True:
            # 判断receiver是否为None或者receiver是否等于接收者，是则接收数据，否则不动数据
            data, receiver_ = self.receive_conn.recv()
            if receiver is None or receiver == receiver_:
                self._run_on_receive_funcs(data, receiver_)
                return data
            self.send_conn.send((data, receiver_))

    def peek(self) -> Optional[Any]:
        """
        查看管道中的数据，不移除
        Returns:
        """
        if self._closed:
            raise RuntimeError("Cannot peek from a closed channel")
        if self.receive_conn.poll():
            data, receiver = self.receive_conn.recv()
            self.receive_conn.send((data, receiver))
            return data
        return None

    def close(self):
        """
        关闭通道
        """
        self._closed = True
        self.receive_conn.close()
        self.send_conn.close()

    def on_receive(self, filter_func: Optional[FILTER_FUNC] = None, receiver: Optional[str] = None) -> Callable[[ON_RECEIVE_FUNC], ON_RECEIVE_FUNC]:
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

    def _run_on_receive_funcs(self, data: Any, receiver: Optional[str] = None):
        """
        运行接收函数
        Args:
            data: 数据
        """
        if receiver is None:
            for func in self._on_receive_funcs:
                run_coroutine(func(data))
        else:
            for func in self._on_receive_funcs_with_receiver.get(receiver, []):
                run_coroutine(func(data))

    def __iter__(self):
        return self

    def __next__(self) -> Any:
        return self.receive()


"""默认通道实例，可直接从模块导入使用"""
chan = Channel()
