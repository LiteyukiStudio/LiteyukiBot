# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/19 下午10:55
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : rule.py
@Software: PyCharm
"""

from typing import Optional, TypeAlias, Callable, Coroutine

from liteyuki.message.event import Event

RuleHandler: TypeAlias = Callable[[Event], Coroutine[None, None, bool]]
"""规则函数签名"""


class Rule:
    def __init__(self, handler: Optional[RuleHandler] = None):
        self.handler = handler

    def __or__(self, other: "Rule") -> "Rule":
        return Rule(lambda event: self.handler(event) or other.handler(event))

    def __and__(self, other: "Rule") -> "Rule":
        return Rule(lambda event: self.handler(event) and other.handler(event))

    async def __call__(self, event: Event) -> bool:
        if self.handler is None:
            return True
        return await self.handler(event)
