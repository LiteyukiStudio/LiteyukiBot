"""Composable LiteyukiBot v6-compatible matcher rules."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Sequence

from liteyuki.bot import get_config

from .event import MessageEvent

type RuleHandlerFunc = Callable[[MessageEvent], bool | Awaitable[bool]]


class Rule:
    def __init__(self, handler: RuleHandlerFunc) -> None:
        if not callable(handler):
            raise TypeError("rule handler must be callable")
        self.handler = handler

    def __or__(self, other: Rule) -> Rule:
        async def combined_handler(event: MessageEvent) -> bool:
            return await self(event) or await other(event)

        return Rule(combined_handler)

    def __and__(self, other: Rule) -> Rule:
        async def combined_handler(event: MessageEvent) -> bool:
            return await self(event) and await other(event)

        return Rule(combined_handler)

    def __invert__(self) -> Rule:
        async def inverted_handler(event: MessageEvent) -> bool:
            return not await self(event)

        return Rule(inverted_handler)

    async def __call__(self, event: MessageEvent) -> bool:
        result = self.handler(event)
        if inspect.isawaitable(result):
            result = await result
        return bool(result)


@Rule
async def empty_rule(_event: MessageEvent) -> bool:
    return True


@Rule
async def is_su_rule(event: MessageEvent) -> bool:
    configured: object = get_config("liteyuki.superusers", ())
    superusers: tuple[str, ...]
    if isinstance(configured, (str, int)):
        superusers = (str(configured),)
    elif isinstance(configured, Sequence):
        superusers = tuple(str(value) for value in configured)
    else:
        superusers = ()
    return str(event.user_id) in superusers


__all__ = ["Rule", "RuleHandlerFunc", "empty_rule", "is_su_rule"]
