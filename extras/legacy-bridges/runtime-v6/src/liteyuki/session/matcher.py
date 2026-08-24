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
    """Represent the validated matcher run result contract."""
    matched: bool
    handlers_called: int = 0
    failures: tuple[str, ...] = ()


class Matcher:
    """Represent the matcher contract."""
    def __init__(self, rule: Rule, priority: int, block: bool) -> None:
        """Initialize the matcher.

        Args:
            rule: The rule value used by the operation.
            priority: The priority value used by the operation.
            block: The block value used by the operation.

        Returns:
            None.
        """
        if priority < 0:
            raise ValueError("matcher priority must be non-negative")
        self.rule = rule
        self.priority = priority
        self.block = block
        self.handlers: list[EventHandler] = []

    def __str__(self) -> str:
        """Implement the str operation for the matcher.

        Returns:
            The `str` result produced by the operation.
        """
        return f"Matcher(rule={self.rule}, priority={self.priority}, block={self.block})"

    def handle(self) -> Callable[[EventHandler], EventHandler]:
        """Handle one request through the matcher.

        Returns:
            The `Callable[[EventHandler], EventHandler]` result produced by the operation.
        """
        def decorator(handler: EventHandler) -> EventHandler:
            """Implement the decorator operation for the handle.

            Args:
                handler: Callable that handles the dispatched value.

            Returns:
                The `EventHandler` result produced by the operation.

            Notes:
                Internal implementation detail for `Matcher.handle.decorator`. It delegates to `append` while
                keeping intermediate state local to the owning operation.
            """
            self.handlers.append(handler)
            return handler

        return decorator

    async def run(self, event: MessageEvent) -> MatcherRunResult:
        """Run the matcher until its lifecycle completes.

        Args:
            event: Event associated with the operation.

        Returns:
            The `MatcherRunResult` result produced by the operation.
        """
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
