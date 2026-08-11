"""Agent-only child host that returns all output through source runtimes."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from uuid import uuid4

from liteyukibot.events import ActionEnvelope, EventEnvelope, Message, Segment, SendMessage
from liteyukibot.logging import configure_runtime_child_logging, get_logger
from liteyukibot.runtime import RuntimeClient
from liteyukibot.runtime.protocol import (
    ActionRequest,
    ActionResponse,
    EventAccepted,
    EventCompleted,
    EventMessage,
    EventTrace,
    Shutdown,
)

from .engine import AgentEngine, ModelReply, OpenAIChatEngine
from .store import ConversationStore


class NativeAgentHost:
    def __init__(
        self,
        client: RuntimeClient,
        engine: AgentEngine,
        store: ConversationStore,
        *,
        history_limit: int,
        message_chunk_size: int,
        max_concurrent_events: int,
    ) -> None:
        self.client = client
        self.engine = engine
        self.store = store
        self.history_limit = history_limit
        self.message_chunk_size = message_chunk_size
        self.max_concurrent_events = max_concurrent_events
        self.logger = get_logger(component="agent", runtime=os.environ.get("LITEYUKI_RUNTIME_ID", "agent"))
        self._tasks: set[asyncio.Task[None]] = set()

    async def serve(self) -> None:
        while True:
            message = await self.client.receive()
            if isinstance(message, Shutdown):
                return
            if isinstance(message, ActionRequest):
                await self.client.send(
                    ActionResponse(
                        correlation_id=message.correlation_id,
                        ok=False,
                        error="native agent does not own a platform action adapter",
                    )
                )
            elif isinstance(message, EventMessage):
                await self._accept_event(message)

    async def close(self) -> None:
        tasks = tuple(self._tasks)
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.store.close()

    async def _accept_event(self, message: EventMessage) -> None:
        try:
            event = EventEnvelope.model_validate(message.payload)
        except ValueError:
            await self.client.send(
                EventAccepted(
                    correlation_id=message.correlation_id,
                    status="invalid",
                    detail="invalid EventEnvelope",
                )
            )
            return
        if event.message is None or not event.message.plain_text.strip():
            await self.client.send(EventAccepted(correlation_id=message.correlation_id, status="accepted"))
            await self.client.send(
                EventCompleted(correlation_id=message.correlation_id, status="completed")
            )
            return
        if len(self._tasks) >= self.max_concurrent_events:
            await self.client.send(
                EventAccepted(
                    correlation_id=message.correlation_id,
                    status="overloaded",
                    detail="native agent event capacity is exhausted",
                )
            )
            return
        await self.client.send(EventAccepted(correlation_id=message.correlation_id, status="accepted"))
        task = asyncio.create_task(
            self._process_event(message.correlation_id, event, message.trace),
            name=f"agent-event:{message.correlation_id}",
        )
        self._tasks.add(task)
        task.add_done_callback(self._event_finished)

    def _event_finished(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            self.logger.error("native agent event task failed: {}", error)

    async def _process_event(
        self,
        delivery_correlation_id: str,
        event: EventEnvelope,
        trace: EventTrace | None,
    ) -> None:
        try:
            key = (event.runtime_id, event.bot_id, event.conversation.ordering_key)
            self.store.append(*key, "user", event.message.plain_text if event.message is not None else "")
            messages: list[Mapping[str, object]] = [
                item for item in self.store.messages(*key, limit=self.history_limit)
            ]
            reply = await self.engine.complete(messages)
            for _index in range(4):
                if not reply.tool_calls:
                    break
                messages.append(_assistant_tool_message(reply))
                for call in reply.tool_calls:
                    result = await self.client.execute_agent_tool(
                        f"tool-{uuid4()}",
                        delivery_correlation_id,
                        call.tool_id,
                        call.arguments,
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": result.data if result.ok else {"error": result.error or "tool failed"},
                        }
                    )
                reply = await self.engine.complete(messages)
            if reply.tool_calls:
                raise RuntimeError("agent exceeded maximum tool-call rounds")
            if reply.text:
                self.store.append(*key, "assistant", reply.text)
                for chunk in _chunks(reply.text, self.message_chunk_size):
                    action = ActionEnvelope(
                        event_id=event.id,
                        runtime_id=event.runtime_id,
                        bot_id=event.bot_id,
                        action=SendMessage(
                            message=Message(segments=(Segment(type="text", data={"text": chunk}),)),
                            conversation=event.conversation,
                            reply_token=event.reply_token,
                        ),
                    )
                    response = await self.client.execute_action(
                        action.action_id,
                        action.model_dump(mode="json"),
                    )
                    if not response.ok:
                        raise RuntimeError(response.error or "source runtime rejected agent output")
        except Exception as error:
            self.logger.bind(
                correlation_id=delivery_correlation_id,
                trace_id=trace.trace_id if trace is not None else None,
            ).error("native agent event failed: {}", error)
            await self.client.send(
                EventCompleted(
                    correlation_id=delivery_correlation_id,
                    status="failed",
                    detail=f"{type(error).__name__}: {error}",
                )
            )
            raise
        await self.client.send(EventCompleted(correlation_id=delivery_correlation_id, status="completed"))


async def run() -> None:
    configure_runtime_child_logging()
    logger = get_logger(component="agent", runtime=os.environ.get("LITEYUKI_RUNTIME_ID", "agent"))
    client = RuntimeClient.from_environment("agent")
    host: NativeAgentHost | None = None
    try:
        logger.info("starting native agent runtime")
        options = await client.connect()
        state_directory = Path(os.environ["LITEYUKI_RUNTIME_STATE_DIR"])
        api_key = _environment_secret(options, "api_key_env", "LITEYUKI_AGENT_API_KEY")
        engine = OpenAIChatEngine(
            api_key=api_key,
            base_url=_optional_string(options, "base_url"),
            model=_required_string(options, "model"),
            tools=_tool_schemas(options),
        )
        host = NativeAgentHost(
            client,
            engine,
            ConversationStore(state_directory / "history.sqlite3"),
            history_limit=_positive_int(options, "history_limit", 40),
            message_chunk_size=_positive_int(options, "message_chunk_size", 1500),
            max_concurrent_events=_positive_int(options, "max_concurrent_events", 16),
        )
        await client.ready(
            ("runtime.events.receive", "runtime.events.complete", "runtime.actions.send", "agent.tools.execute")
        )
        logger.info("native agent runtime is ready")
        await host.serve()
    except Exception as error:
        logger.error("native agent runtime failed: {}", error)
        raise
    finally:
        if host is not None:
            await host.close()
        await client.close()
        logger.info("native agent runtime stopped")


def _assistant_tool_message(reply: ModelReply) -> Mapping[str, object]:
    return {
        "role": "assistant",
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.tool_id, "arguments": str(dict(call.arguments))},
            }
            for call in reply.tool_calls
        ],
    }


def _chunks(value: str, size: int) -> Sequence[str]:
    return tuple(value[index : index + size] for index in range(0, len(value), size))


def _required_string(options: Mapping[str, object], key: str) -> str:
    value = options.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"native agent option {key!r} must be a non-empty string")
    return value


def _optional_string(options: Mapping[str, object], key: str) -> str | None:
    value = options.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"native agent option {key!r} must be a non-empty string when set")
    return value


def _positive_int(options: Mapping[str, object], key: str, default: int) -> int:
    value = options.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"native agent option {key!r} must be a positive integer")
    return value


def _environment_secret(options: Mapping[str, object], key: str, default: str) -> str:
    environment_name = _optional_string(options, key) or default
    value = os.environ.get(environment_name)
    if not value:
        raise ValueError(f"native agent environment variable {environment_name!r} is not set")
    return value


def _tool_schemas(options: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    catalog = options.get("agent_tool_catalog", {})
    if not isinstance(catalog, Mapping):
        raise ValueError("native agent option 'agent_tool_catalog' must be an object")
    tools = catalog.get("tools", ())
    if not isinstance(tools, Sequence) or isinstance(tools, (str, bytes)):
        raise ValueError("native agent tool catalog must contain a tools array")
    schemas: list[Mapping[str, object]] = []
    for entry in tools:
        if not isinstance(entry, Mapping):
            raise ValueError("native agent tool catalog entries must be objects")
        tool_id = entry.get("id")
        description = entry.get("description")
        input_schema = entry.get("input_schema")
        if not isinstance(tool_id, str) or not isinstance(description, str) or not isinstance(input_schema, Mapping):
            raise ValueError("native agent tool catalog entry is invalid")
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": tool_id,
                    "description": description,
                    "parameters": dict(input_schema),
                },
            }
        )
    return tuple(schemas)
