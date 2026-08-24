"""Composable LiteyukiBot v6-compatible matcher rules."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Sequence

from liteyuki.bot import get_config

from .event import MessageEvent

type RuleHandlerFunc = Callable[[MessageEvent], bool | Awaitable[bool]]


class Rule:
    """Represent the rule contract."""
    def __init__(self, handler: RuleHandlerFunc) -> None:
        """Initialize the rule.

        Args:
            handler: Callable that handles the dispatched value.

        Returns:
            None.
        """
        if not callable(handler):
            raise TypeError("rule handler must be callable")
        self.handler = handler

    def __or__(self, other: Rule) -> Rule:
        """Implement the or operation for the rule.

        Args:
            other: The other value used by the operation.

        Returns:
            The `Rule` result produced by the operation.
        """
        async def combined_handler(event: MessageEvent) -> bool:
            """Implement the combined handler operation for the or.

            Args:
                event: Event associated with the operation.

            Returns:
                Whether the requested condition is satisfied.

            Notes:
                Internal implementation detail for `Rule.__or__.combined_handler`. It delegates to `self`,
                `other` while keeping intermediate state local to the owning operation.
            """
            return await self(event) or await other(event)

        return Rule(combined_handler)

    def __and__(self, other: Rule) -> Rule:
        """Implement the and operation for the rule.

        Args:
            other: The other value used by the operation.

        Returns:
            The `Rule` result produced by the operation.
        """
        async def combined_handler(event: MessageEvent) -> bool:
            """Implement the combined handler operation for the and.

            Args:
                event: Event associated with the operation.

            Returns:
                Whether the requested condition is satisfied.

            Notes:
                Internal implementation detail for `Rule.__and__.combined_handler`. It delegates to `self`,
                `other` while keeping intermediate state local to the owning operation.
            """
            return await self(event) and await other(event)

        return Rule(combined_handler)

    def __invert__(self) -> Rule:
        """Implement the invert operation for the rule.

        Returns:
            The `Rule` result produced by the operation.
        """
        async def inverted_handler(event: MessageEvent) -> bool:
            """Implement the inverted handler operation for the invert.

            Args:
                event: Event associated with the operation.

            Returns:
                Whether the requested condition is satisfied.

            Notes:
                Internal implementation detail for `Rule.__invert__.inverted_handler`. It delegates to `self`
                while keeping intermediate state local to the owning operation.
            """
            return not await self(event)

        return Rule(inverted_handler)

    async def __call__(self, event: MessageEvent) -> bool:
        """Invoke the rule as a callable.

        Args:
            event: Event associated with the operation.

        Returns:
            Whether the requested condition is satisfied.
        """
        result = self.handler(event)
        if inspect.isawaitable(result):
            result = await result
        return bool(result)


@Rule
async def empty_rule(_event: MessageEvent) -> bool:
    """Implement the empty rule operation for the component.

    Args:
        _event: The event value used by the operation.

    Returns:
        Whether the requested condition is satisfied.
    """
    return True


@Rule
async def is_su_rule(event: MessageEvent) -> bool:
    """Implement the is su rule operation for the component.

    Args:
        event: Event associated with the operation.

    Returns:
        Whether the requested condition is satisfied.
    """
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
