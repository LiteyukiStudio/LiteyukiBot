"""Protocol-neutral action authorization and dispatch."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any, cast

from .events import ActionEnvelope, ActionResult, EventEnvelope

type ActionBackend = Callable[
    [EventEnvelope | None, ActionEnvelope],
    Awaitable[ActionResult],
]
type ActionPolicy = Callable[[EventEnvelope | None, ActionEnvelope], Awaitable[ActionResult | None]]


def _is_async_callable(value: object) -> bool:
    """Return whether a callback is an async function or async callable object."""

    if inspect.iscoroutinefunction(value):
        return True
    return callable(value) and inspect.iscoroutinefunction(cast(Any, value).__call__)


class ActionService:
    """Authorize protocol-neutral actions before dispatching them to a backend."""

    def __init__(self, backend: ActionBackend, policy: ActionPolicy) -> None:
        """Initialize the action service.

        Args:
            backend: Protocol-neutral action dispatch callback.
            policy: Authorization policy evaluated before dispatch.

        Returns:
            None.
        """
        if not _is_async_callable(backend):
            raise TypeError("action backend must be an async callable")
        if not _is_async_callable(policy):
            raise TypeError("action policy must be an async callable")
        self._backend = backend
        self._policy = policy

    async def execute(self, action: ActionEnvelope, *, event: EventEnvelope | None = None) -> ActionResult:
        """Authorize and dispatch one action request.

        Args:
            action: Action request being processed.
            event: Optional source event used by authorization and routing.

        Returns:
            The action result produced by the policy or backend.
        """
        guarded = await self._policy(event, action)
        if guarded is not None:
            if guarded.action_id != action.action_id:
                return ActionResult(
                    action_id=action.action_id,
                    success=False,
                    error_code="ACTION_RESULT_MISMATCH",
                    error_message="action policy returned a result for another action",
                )
            return guarded
        result = await self._backend(event, action)
        if result.action_id != action.action_id:
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error_code="ACTION_RESULT_MISMATCH",
                error_message="action backend returned a result for another action",
            )
        return result


__all__ = ["ActionBackend", "ActionPolicy", "ActionService"]
