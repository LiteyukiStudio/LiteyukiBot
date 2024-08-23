# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/19 下午10:55
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : rule.py
@Software: PyCharm
"""
import inspect
from typing import Optional, TypeAlias, Callable, Coroutine

from liteyuki.message.event import MessageEvent
from liteyuki import get_config

_superusers: list[str] = get_config("liteyuki.superusers", [])

RuleHandlerFunc: TypeAlias = Callable[[MessageEvent], Coroutine[None, None, bool]]
"""规则函数签名"""


class Rule:
    def __init__(self, handler: RuleHandlerFunc):
        self.handler = handler

    def __or__(self, other: "Rule") -> "Rule":
        async def combined_handler(event: MessageEvent) -> bool:
            return await self.handler(event) or await other.handler(event)

        return Rule(combined_handler)

    def __and__(self, other: "Rule") -> "Rule":
        async def combined_handler(event: MessageEvent) -> bool:
            return await self.handler(event) and await other.handler(event)

        return Rule(combined_handler)

    async def __call__(self, event: MessageEvent) -> bool:
        if self.handler is None:
            return True
        return await self.handler(event)


@Rule
async def empty_rule(event: MessageEvent) -> bool:
    return True

@Rule
async def is_su_rule(event: MessageEvent) -> bool:
    return str(event.user_id) in _superusers
