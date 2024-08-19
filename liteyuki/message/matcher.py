# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/19 下午10:51
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : matcher.py
@Software: PyCharm
"""
import traceback
from typing import Any, TypeAlias, Callable, Coroutine

from liteyuki import Event
from liteyuki.message.rule import Rule

EventHandler: TypeAlias = Callable[[Event], Coroutine[None, None, Any]]


class Matcher:
    def __init__(self, rule: Rule, priority: int, block: bool):
        """
        匹配器
        Args:
            rule: 规则
            priority: 优先级 >= 0
            block: 是否阻断后续优先级更低的匹配器
        """
        self.rule = rule
        self.priority = priority
        self.block = block
        self.handlers: list[EventHandler] = []

    def __str__(self):
        return f"Matcher(rule={self.rule}, priority={self.priority}, block={self.block})"

    def handle(self, handler: EventHandler) -> EventHandler:
        """
        添加处理函数，装饰器
        Args:
            handler:
        Returns:
            EventHandler
        """
        self.handlers.append(handler)
        return handler

    async def run(self, event: Event) -> None:
        """
        运行处理函数
        Args:
            event:
        Returns:
        """
        if not await self.rule(event):
            return

        for handler in self.handlers:
            try:
                await handler(event)
            except Exception:
                traceback.print_exc()
