# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/7/23 下午8:24
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : lifespan.py
@Software: PyCharm
"""
import asyncio
from typing import Any, Awaitable, Callable, TypeAlias

from liteyuki.log import logger
from liteyuki.utils import is_coroutine_callable, async_wrapper

SYNC_LIFESPAN_FUNC: TypeAlias = Callable[[], Any]
ASYNC_LIFESPAN_FUNC: TypeAlias = Callable[[], Awaitable[Any]]
LIFESPAN_FUNC: TypeAlias = SYNC_LIFESPAN_FUNC | ASYNC_LIFESPAN_FUNC

SYNC_PROCESS_LIFESPAN_FUNC: TypeAlias = Callable[[str], Any]
ASYNC_PROCESS_LIFESPAN_FUNC: TypeAlias = Callable[[str], Awaitable[Any]]
PROCESS_LIFESPAN_FUNC: TypeAlias = SYNC_PROCESS_LIFESPAN_FUNC | ASYNC_PROCESS_LIFESPAN_FUNC


class Lifespan:
    def __init__(self) -> None:
        """
        轻雪生命周期管理，启动、停止、重启
        """
        self.life_flag: int = 0

        self._before_start_funcs: list[LIFESPAN_FUNC] = []
        self._after_start_funcs: list[LIFESPAN_FUNC] = []

        self._before_process_shutdown_funcs: list[LIFESPAN_FUNC] = []
        self._after_shutdown_funcs: list[LIFESPAN_FUNC] = []

        self._before_process_restart_funcs: list[LIFESPAN_FUNC] = []
        self._after_restart_funcs: list[LIFESPAN_FUNC] = []

    @staticmethod
    async def run_funcs(funcs: list[ASYNC_LIFESPAN_FUNC | PROCESS_LIFESPAN_FUNC], *args, **kwargs) -> None:
        """
        并发运行异步函数
        Args:
            funcs:
        Returns:
        """
        loop = asyncio.get_running_loop()
        tasks = [func(*args, **kwargs) if is_coroutine_callable(func) else async_wrapper(func)(*args, **kwargs) for func in funcs]
        await asyncio.gather(*tasks)

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

    def on_before_process_shutdown(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC:
        """
        注册停止前的函数
        Args:
            func:
        Returns:
            LIFESPAN_FUNC:
        """
        self._before_process_shutdown_funcs.append(func)
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

    def on_before_process_restart(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC:
        """
        注册重启时的函数
        Args:
            func:
        Returns:
            LIFESPAN_FUNC:
        """
        self._before_process_restart_funcs.append(func)
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

    async def before_start(self) -> None:
        """
        启动前
        Returns:
        """
        logger.debug("Running before_start functions")
        await self.run_funcs(self._before_start_funcs)

    async def after_start(self) -> None:
        """
        启动后
        Returns:
        """
        logger.debug("Running after_start functions")
        await self.run_funcs(self._after_start_funcs)

    async def before_process_shutdown(self) -> None:
        """
        停止前
        Returns:
        """
        logger.debug("Running before_shutdown functions")
        await self.run_funcs(self._before_process_shutdown_funcs)

    async def after_shutdown(self) -> None:
        """
        停止后
        Returns:
        """
        logger.debug("Running after_shutdown functions")
        await self.run_funcs(self._after_shutdown_funcs)

    async def before_process_restart(self) -> None:
        """
        重启前
        Returns:
        """
        logger.debug("Running before_restart functions")
        await self.run_funcs(self._before_process_restart_funcs)

    async def after_restart(self) -> None:
        """
        重启后
        Returns:

        """
        logger.debug("Running after_restart functions")
        await self.run_funcs(self._after_restart_funcs)
