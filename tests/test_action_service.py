from __future__ import annotations

from typing import NoReturn

import pytest

from liteyukibot.action_service import ActionService
from liteyukibot.events import ActionEnvelope, ActionResult, CallApi, ConversationRef, EventEnvelope


def _action() -> ActionEnvelope:
    return ActionEnvelope(
        action_id="action-1",
        runtime_id="adapter",
        bot_id="bot-1",
        action=CallApi(api="get_status"),
    )


def _event() -> EventEnvelope:
    return EventEnvelope(
        id="event-1",
        runtime_id="adapter",
        adapter="onebot-v11",
        bot_id="bot-1",
        type="notice.ready",
        conversation=ConversationRef(id="system", type="private"),
    )


@pytest.mark.asyncio
async def test_action_service_dispatches_to_async_backend() -> None:
    action = _action()
    event = _event()
    observed: list[tuple[EventEnvelope | None, ActionEnvelope]] = []

    async def backend(source: EventEnvelope | None, request: ActionEnvelope) -> ActionResult:
        observed.append((source, request))
        return ActionResult(action_id=request.action_id, success=True)

    service = ActionService(backend, lambda _event, _action: None)

    result = await service.execute(action, event=event)

    assert result.success is True
    assert observed == [(event, action)]


@pytest.mark.asyncio
async def test_action_service_accepts_sync_backend() -> None:
    action = _action()
    observed: list[EventEnvelope | None] = []

    def backend(event: EventEnvelope | None, request: ActionEnvelope) -> ActionResult:
        observed.append(event)
        return ActionResult(action_id=request.action_id, success=True)

    service = ActionService(
        backend,
        lambda _event, _action: None,
    )

    result = await service.execute(action)

    assert result.success is True
    assert observed == [None]


@pytest.mark.asyncio
async def test_action_service_policy_short_circuits_backend() -> None:
    action = _action()
    denied = ActionResult(
        action_id=action.action_id,
        success=False,
        error_code="ACTION_PERMISSION_DENIED",
    )

    def backend(_event: EventEnvelope | None, _action: ActionEnvelope) -> NoReturn:
        raise AssertionError("denied action reached backend")

    service = ActionService(backend, lambda _event, _action: denied)

    result = await service.execute(action)

    assert result is denied


@pytest.mark.asyncio
async def test_action_service_rejects_mismatched_policy_result() -> None:
    action = _action()

    def backend(_event: EventEnvelope | None, _action: ActionEnvelope) -> NoReturn:
        raise AssertionError("mismatched policy result reached backend")

    service = ActionService(
        backend,
        lambda _event, _action: ActionResult(
            action_id="other-action",
            success=False,
            error_code="ACTION_PERMISSION_DENIED",
        ),
    )

    result = await service.execute(action)

    assert result.action_id == action.action_id
    assert result.success is False
    assert result.error_code == "ACTION_RESULT_MISMATCH"


@pytest.mark.asyncio
async def test_action_service_rejects_mismatched_backend_result() -> None:
    action = _action()

    async def backend(_event: EventEnvelope | None, _action: ActionEnvelope) -> ActionResult:
        return ActionResult(action_id="other-action", success=True)

    service = ActionService(backend, lambda _event, _action: None)

    result = await service.execute(action)

    assert result.action_id == action.action_id
    assert result.success is False
    assert result.error_code == "ACTION_RESULT_MISMATCH"
