# -*- coding: utf-8 -*-
"""
本模块用于实现RPC(基于IPC)通信
"""

from typing import TypeAlias, Callable, Any

from liteyuki.comm.channel import Channel

ON_CALLING_FUNC: TypeAlias = Callable[[tuple, dict], Any]


class RPC:
    """
    RPC类
    """

    def __init__(self, on_calling: ON_CALLING_FUNC) -> None:
        self.on_calling = on_calling

    def call(self, args: tuple, kwargs: dict) -> Any:
        """
        调用
        """
        # 获取self.calling函数名
        return self.on_calling(args, kwargs)
