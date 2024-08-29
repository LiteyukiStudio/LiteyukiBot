# -*- coding: utf-8 -*-
"""
一些常用的工具类，部分来源于 nonebot 并遵循其许可进行修改
"""
import asyncio
import inspect
import multiprocessing
import threading
from pathlib import Path
from typing import Any, Callable, Coroutine

from liteyuki.log import logger

IS_MAIN_PROCESS = multiprocessing.current_process().name == "MainProcess"


def is_coroutine_callable(call: Callable[..., Any]) -> bool:
    """
    判断是否为协程可调用对象
    Args:
        call: 可调用对象
    Returns:
        bool: 是否为协程可调用对象
    """
    if inspect.isroutine(call):
        return inspect.iscoroutinefunction(call)
    if inspect.isclass(call):
        return False
    func_ = getattr(call, "__call__", None)
    return inspect.iscoroutinefunction(func_)


def run_coroutine(*coro: Coroutine):
    """
    运行协程
    Args:
        coro:

    Returns:

    """

    # 检测是否有现有的事件循环

    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            # 如果事件循环正在运行，创建任务
            for c in coro:
                asyncio.ensure_future(c)
        else:
            # 如果事件循环未运行，运行直到完成
            for c in coro:
                loop.run_until_complete(c)
    except RuntimeError:
        # 如果没有找到事件循环，创建一个新的
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(asyncio.gather(*coro))
        loop.close()
    except Exception as e:
        # 捕获其他异常，防止协程被重复等待
        logger.error(f"Exception occurred: {e}")


def run_coroutine_in_thread(*coro: Coroutine):
    """
    在新线程中运行协程
    Args:
        coro:

    Returns:

    """
    threading.Thread(target=run_coroutine, args=coro, daemon=True).start()


def path_to_module_name(path: Path) -> str:
    """
    转换路径为模块名
    Args:
        path: 路径a/b/c/d -> a.b.c.d
    Returns:
        str: 模块名
    """
    rel_path = path.resolve().relative_to(Path.cwd().resolve())
    if rel_path.stem == "__init__":
        return ".".join(rel_path.parts[:-1])
    else:
        return ".".join(rel_path.parts[:-1] + (rel_path.stem,))


def async_wrapper(func: Callable[..., Any]) -> Callable[..., Coroutine]:
    """
    异步包装器
    Args:
        func: Sync Callable
    Returns:
        Coroutine: Asynchronous Callable
    """

    async def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    wrapper.__signature__ = inspect.signature(func)
    return wrapper
