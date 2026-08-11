"""LiteyukiBot v6-compatible matcher handlers."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from liteyuki.log import logger

from .event import MessageEvent
from .rule import Rule

type EventHandler = Callable[[MessageEvent], Any | Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class MatcherRunResult:
    matched: bool
    handlers_called: int = 0
    failures: tuple[str, ...] = ()


class Matcher:
    def __init__(self, rule: Rule, priority: int, block: bool) -> None:
        if priority < 0:
            raise ValueError("matcher priority must be non-negative")
        self.rule = rule
        self.priority = priority
        self.block = block
        self.handlers: list[EventHandler] = []

    def __str__(self) -> str:
        return f"Matcher(rule={self.rule}, priority={self.priority}, block={self.block})"

    def handle(self) -> Callable[[EventHandler], EventHandler]:
        def decorator(handler: EventHandler) -> EventHandler:
            self.handlers.append(handler)
            return handler

        return decorator

    async def run(self, event: MessageEvent) -> MatcherRunResult:
        if not await self.rule(event):
            return MatcherRunResult(matched=False)

        failures: list[str] = []
        handlers = tuple(self.handlers)
        for handler in handlers:
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    await result
            except Exception as error:
                name = getattr(handler, "__qualname__", repr(handler))
                failures.append(f"{name}: {type(error).__name__}: {error}")
                logger.exception("v6 matcher handler {} failed: {}", name, error)
        return MatcherRunResult(
            matched=True,
            handlers_called=len(handlers),
            failures=tuple(failures),
        )


__all__ = ["EventHandler", "Matcher", "MatcherRunResult"]
