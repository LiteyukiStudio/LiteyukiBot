# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/7/23 下午8:24
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : lifespan.py
@Software: PyCharm
"""
from typing import Any, Awaitable, Callable, TypeAlias

from liteyuki.utils import is_coroutine_callable

SYNC_LIFESPAN_FUNC: TypeAlias = Callable[[], Any]
ASYNC_LIFESPAN_FUNC: TypeAlias = Callable[[], Awaitable[Any]]
LIFESPAN_FUNC: TypeAlias = SYNC_LIFESPAN_FUNC | ASYNC_LIFESPAN_FUNC


class Lifespan:
    def __init__(self) -> None:
        """
        轻雪生命周期管理，启动、停止、重启
        """

        self.life_flag: int = 0  # 0: 启动前，1: 启动后，2: 停止前，3: 停止后

        self._before_start_funcs: list[LIFESPAN_FUNC] = []
        self._after_start_funcs: list[LIFESPAN_FUNC] = []

        self._before_shutdown_funcs: list[LIFESPAN_FUNC] = []
        self._after_shutdown_funcs: list[LIFESPAN_FUNC] = []

        self._before_restart_funcs: list[LIFESPAN_FUNC] = []
        self._after_restart_funcs: list[LIFESPAN_FUNC] = []

        self._after_nonebot_init_funcs: list[LIFESPAN_FUNC] = []

    @staticmethod
    async def _run_funcs(funcs: list[LIFESPAN_FUNC]) -> None:
        """
        运行函数
        Args:
            funcs:
        Returns:
        """
        for func in funcs:
            if is_coroutine_callable(func):
                await func()
            else:
                func()

    def on_before_start(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC:
        """
        注册启动时的函数
        Args:
            func:
        Returns:
            LIFESPAN_FUNC:
        """
        self._before_start_funcs.append(func)
        return func

    def on_after_start(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC:
        """
        注册启动时的函数
        Args:
            func:
        Returns:
            LIFESPAN_FUNC:
        """
        self._after_start_funcs.append(func)
        return func

    def on_before_shutdown(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC:
        """
        注册停止前的函数
        Args:
            func:
        Returns:
            LIFESPAN_FUNC:
        """
        self._before_shutdown_funcs.append(func)
        return func

    def on_after_shutdown(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC:
        """
        注册停止后的函数
        Args:
            func:

        Returns:
            LIFESPAN_FUNC:

        """
        self._after_shutdown_funcs.append(func)
        return func

    def on_before_restart(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC:
        """
        注册重启时的函数
        Args:
            func:
        Returns:
            LIFESPAN_FUNC:
        """
        self._before_restart_funcs.append(func)
        return func

    def on_after_restart(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC:
        """
        注册重启后的函数
        Args:
            func:
        Returns:
            LIFESPAN_FUNC:
        """
        self._after_restart_funcs.append(func)
        return func

    def on_after_nonebot_init(self, func):
        """
        注册 NoneBot 初始化后的函数
        Args:
            func:

        Returns:

        """
        self._after_nonebot_init_funcs.append(func)
        return func

    async def before_start(self) -> None:
        """
        启动前
        Returns:
        """
        await self._run_funcs(self._before_start_funcs)

    async def after_start(self) -> None:
        """
        启动后
        Returns:
        """
        await self._run_funcs(self._after_start_funcs)

    async def before_shutdown(self) -> None:
        """
        停止前
        Returns:
        """
        await self._run_funcs(self._before_shutdown_funcs)

    async def after_shutdown(self) -> None:
        """
        停止后
        Returns:
        """
        await self._run_funcs(self._after_shutdown_funcs)

    async def before_restart(self) -> None:
        """
        重启前
        Returns:
        """
        await self._run_funcs(self._before_restart_funcs)

    async def after_restart(self) -> None:
        """
        重启后
        Returns:

        """
        await self._run_funcs(self._after_restart_funcs)

    async def after_nonebot_init(self) -> None:
        """
        NoneBot 初始化后
        Returns:
        """
        await self._run_funcs(self._after_nonebot_init_funcs)
