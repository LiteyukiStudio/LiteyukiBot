"""Minimal supervised LiteyukiBot v7 custom runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, Literal

from pydantic import ValidationError

from liteyukibot.events import ActionEnvelope, EventEnvelope, Message, Segment, SendMessage
from liteyukibot.runtime import (
    ActionRequest,
    ActionResponse,
    EventAccepted,
    EventMessage,
    RuntimeClient,
    Shutdown,
)

MAX_IN_FLIGHT = 32


async def _handle_event(client: RuntimeClient, message: EventMessage) -> None:
    status: Literal["accepted", "overloaded", "invalid"] = "accepted"
    detail: str | None = None
    try:
        event = EventEnvelope.model_validate(message.payload)
    except ValidationError as error:
        status = "invalid"
        detail = str(error)
    else:
        try:
            if event.message is not None:
                reply = ActionEnvelope(
                    event_id=event.id,
                    runtime_id=event.runtime_id,
                    bot_id=event.bot_id,
                    action=SendMessage(
                        message=Message(
                            segments=(
                                Segment(
                                    type="text",
                                    data={"text": "runtime: " + event.message.plain_text},
                                ),
                            )
                        ),
                        conversation=event.conversation,
                        reply_token=event.reply_token,
                    ),
                )
                result = await client.execute_action(
                    reply.action_id,
                    reply.model_dump(mode="json"),
                )
                if not result.ok:
                    status = "invalid"
                    detail = result.error or "core rejected the reply Action"
        except Exception as error:
            status = "invalid"
            detail = f"{type(error).__name__}: {error}"

    await client.send(
        EventAccepted(
            correlation_id=message.correlation_id,
            status=status,
            detail=detail,
        )
    )


async def _handle_action(client: RuntimeClient, message: ActionRequest) -> None:
    await client.send(
        ActionResponse(
            correlation_id=message.correlation_id,
            ok=True,
            data={"echo": message.payload},
        )
    )


async def run() -> None:
    client = RuntimeClient.from_environment("custom")
    tasks: set[asyncio.Task[None]] = set()

    def task_done(task: asyncio.Task[None]) -> None:
        tasks.discard(task)
        if not task.cancelled():
            task.exception()

    def spawn(awaitable: Coroutine[Any, Any, None], *, name: str) -> None:
        task = asyncio.create_task(awaitable, name=name)
        tasks.add(task)
        task.add_done_callback(task_done)

    try:
        await client.connect()
        await client.ready(("runtime.events.receive", "runtime.actions.send"))
        while True:
            message = await client.receive()
            if isinstance(message, Shutdown):
                break
            if isinstance(message, EventMessage):
                if len(tasks) >= MAX_IN_FLIGHT:
                    await client.send(
                        EventAccepted(
                            correlation_id=message.correlation_id,
                            status="overloaded",
                        )
                    )
                else:
                    spawn(
                        _handle_event(client, message),
                        name=f"event:{message.correlation_id}",
                    )
            elif isinstance(message, ActionRequest):
                if len(tasks) >= MAX_IN_FLIGHT:
                    await client.send(
                        ActionResponse(
                            correlation_id=message.correlation_id,
                            ok=False,
                            error="runtime is overloaded",
                        )
                    )
                else:
                    spawn(
                        _handle_action(client, message),
                        name=f"action:{message.correlation_id}",
                    )
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await client.close()


def main() -> None:
    asyncio.run(run())


__all__ = ["main", "run"]
