# -*- coding: utf-8 -*-
"""
一些常用的工具类，部分来源于 nonebot 并遵循其许可进行修改
"""
import inspect
from pathlib import Path
from typing import Any, Callable


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
