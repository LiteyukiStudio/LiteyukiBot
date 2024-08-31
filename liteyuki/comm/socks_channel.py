# -*- coding: utf-8 -*-
"""
基于socket的通道
"""


class SocksChannel:
    """
    通道类，可以在进程间和进程内通信，双向但同时只能有一个发送者和一个接收者
    有两种接收工作方式，但是只能选择一种，主动接收和被动接收，主动接收使用 `receive` 方法，被动接收使用 `on_receive` 装饰器
    """

    def __init__(self, name: str):
        """
        初始化通道
        Args:
            name: 通道ID
        """

        self._name = name
        self._conn_send = None
        self._conn_recv = None
        self._closed = False

    def send(self, data):
        """
        发送数据
        Args:
            data: 数据
        """

        pass

    def receive(self):
        """
        接收数据
        Returns:
            data: 数据
        """

        pass

    def close(self):
        """
        关闭通道
        """

        pass
