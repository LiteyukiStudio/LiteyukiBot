"""OpenAI-compatible Agent and bounded sandbox bridge hosts."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import urlparse
from uuid import uuid4

import zmq.asyncio
from jsonschema import Draft202012Validator, ValidationError
from liteyukibot_permissions.service import create_permission_service

from liteyukibot import AuthorizationContext
from liteyukibot.broker import (
    MESSAGE_SEND_KIND,
    BridgeAccess,
    BridgeClient,
    BridgeControlInvoke,
    BridgeManifest,
    BrokerBridgeRunner,
    BrokerDelivery,
    BrokerToolDeclaration,
    ControlOutcome,
    MessageSendPayload,
    ToolInvoke,
    ToolOutcome,
    ToolResult,
    message_send_resource_key,
)
from liteyukibot.broker.protocol import AuthorizationContextWire
from liteyukibot.config import AppSettings
from liteyukibot.events import EventEnvelope, Message, Segment
from liteyukibot.events.models import JsonValue
from liteyukibot.lyip import LyipLane

from .catalog import (
    ACTIVE_TOOL_LIMIT,
    CATALOG_SEARCH_ID,
    AgentCatalog,
    SandboxToolDefinition,
    catalog_search_schema,
    discover_sandbox_tool_definitions,
    openai_tool_schema,
)
from .engine import AgentEngine, ModelReply, OpenAIChatEngine, ToolCall
from .rag import OpenAIEmbeddingProvider, RagContext, RagIndex, RagSettings
from .sandbox import SandboxPolicy, builtin_sandbox_tools, execute_in_fresh_worker
from .store import ConversationStore

AGENT_HISTORY_CLEAR = "agent.history.clear"
_ALLOWED_AGENT_OPTIONS = frozenset(
    {
        "api_key",
        "base_url",
        "model",
        "history_limit",
        "max_tool_rounds",
        "model_timeout_seconds",
        "event_timeout_seconds",
        "max_concurrent_events",
        "history_path",
        "rag_paths",
        "rag_index_path",
        "rag_chunk_size",
        "rag_chunk_overlap",
        "rag_top_k",
        "rag_context_chars",
        "rag_embedding_model",
        "rag_embedding_api_key",
        "rag_embedding_base_url",
        "rag_timeout_seconds",
        "rag_citations",
    }
)
_ALLOWED_SANDBOX_OPTIONS = frozenset(
    {
        "file_roots",
        "command_allowlist",
        "allowed_hosts",
        "allowed_ports",
        "allow_private_network",
        "wall_timeout_seconds",
        "max_output_bytes",
        "max_file_bytes",
        "work_directory",
    }
)
_HISTORY_SUMMARY_LIMIT = 512
_MODEL_TOOL_RESULT_LIMIT = 8_192


class PermissionPolicy(Protocol):
    def allows(self, context: AuthorizationContext, capability: str) -> bool: ...


class AgentBridgeHost:
    """Own provider state and bounded history behind one Agent bridge."""

    def __init__(
        self,
        runner: BrokerBridgeRunner,
        engine: AgentEngine,
        store: ConversationStore,
        catalog: AgentCatalog,
        permissions: PermissionPolicy | None,
        *,
        max_concurrent_events: int,
        history_limit: int,
        model_timeout_seconds: float,
        event_timeout_seconds: float,
        max_tool_rounds: int,
        rag: RagIndex | None = None,
    ) -> None:
        self.runner = runner
        self.engine = engine
        self.store = store
        self.catalog = catalog
        self.permissions = permissions
        self.history_limit = history_limit
        self.model_timeout_seconds = model_timeout_seconds
        self.event_timeout_seconds = event_timeout_seconds
        self.max_tool_rounds = max_tool_rounds
        self.rag = rag
        self._capacity = asyncio.Semaphore(max_concurrent_events)

    async def handle_delivery(self, delivery: BrokerDelivery) -> None:
        async with self._capacity:
            try:
                event = _event_from_delivery(delivery)
                message = event.message
                if message is None or not message.plain_text.strip():
                    return
                async with asyncio.timeout(self.event_timeout_seconds):
                    await self._process_event(delivery, event)
            except TimeoutError as error:
                raise RuntimeError("agent event timed out") from error
            except Exception as error:
                raise RuntimeError("agent event failed") from error

    async def clear_history(self, request: BridgeControlInvoke) -> ControlOutcome:
        authorization = _authorization_context(request)
        if not _allows(self.permissions, authorization, AGENT_HISTORY_CLEAR):
            return ControlOutcome(success=False, error_code="CONTROL_PERMISSION_DENIED")
        payload = request.payload
        if set(payload) != {"conversation_id"}:
            return ControlOutcome(success=False, error_code="CONTROL_INVALID_PAYLOAD")
        conversation_id = payload.get("conversation_id")
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            return ControlOutcome(success=False, error_code="CONTROL_INVALID_PAYLOAD")
        cleared = self.store.clear(authorization.runtime_id, authorization.bot_id, conversation_id)
        return ControlOutcome(success=True, result={"cleared": cleared})

    async def _process_event(self, delivery: BrokerDelivery, event: EventEnvelope) -> None:
        key = (event.runtime_id, event.bot_id, event.conversation.ordering_key)
        user_text = event.message.plain_text if event.message is not None else ""
        self.store.append(*key, "user", user_text, retain=self.history_limit)
        messages: list[Mapping[str, object]] = [
            cast(Mapping[str, object], item) for item in self.store.messages(*key, limit=self.history_limit)
        ]
        rag_context = await self._retrieve_rag(user_text)
        if rag_context.text:
            messages.insert(0, {"role": "system", "content": "Relevant local documents:\n" + rag_context.text})
        active = {tool.id: tool for tool in self.catalog.initial()}
        messages_tools = _tool_schemas(active.values())
        authorization = AuthorizationContext(
            event_id=event.id,
            runtime_id=event.runtime_id,
            bot_id=event.bot_id,
            actor_id=None if event.actor is None else event.actor.id,
        )
        reply = await self._complete(messages, messages_tools)
        for _round in range(self.max_tool_rounds):
            if not reply.tool_calls:
                break
            messages.append(_assistant_tool_message(reply))
            for call in reply.tool_calls:
                content, history_summary, selected = await self._execute_tool(
                    delivery,
                    event,
                    authorization,
                    call,
                    active,
                )
                messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
                self.store.append(*key, "tool", history_summary, retain=self.history_limit)
                if selected is not None:
                    active.update(selected)
                    if len(active) > ACTIVE_TOOL_LIMIT - 1:
                        active = dict(tuple(active.items())[: ACTIVE_TOOL_LIMIT - 1])
            reply = await self._complete(messages, _tool_schemas(active.values()))
        if reply.tool_calls:
            raise RuntimeError("agent exceeded maximum tool-call rounds")
        final_text = _append_citations(reply.text.strip(), rag_context)
        if not final_text:
            return
        self.store.append(*key, "assistant", final_text, retain=self.history_limit)
        payload = MessageSendPayload(
            bot_id=event.bot_id,
            message=Message(segments=(Segment(type="text", data={"text": final_text}),)),
            conversation=event.conversation,
            reply_token=event.reply_token,
        )
        action = await delivery.request_action(
            correlation_id=f"agent:{event.id}:{uuid4()}",
            kind=MESSAGE_SEND_KIND,
            resource_key=message_send_resource_key(event.runtime_id, event.bot_id),
            payload=payload.model_dump(mode="json", exclude_none=True),
        )
        if not action.success:
            raise RuntimeError("agent final message action failed")

    async def _retrieve_rag(self, query: str) -> RagContext:
        if self.rag is None:
            return RagContext("")
        try:
            return await self.rag.retrieve(query)
        except (RuntimeError, TimeoutError, ValueError):
            return RagContext("")

    async def _execute_tool(
        self,
        delivery: BrokerDelivery,
        event: EventEnvelope,
        authorization: AuthorizationContext,
        call: ToolCall,
        active: Mapping[str, Any],
    ) -> tuple[JsonObject, JsonObject, Mapping[str, Any] | None]:
        if call.tool_id == CATALOG_SEARCH_ID:
            query = call.arguments.get("query")
            if not isinstance(query, str) or not query.strip():
                return (
                    {"error_code": "TOOL_INVALID_ARGUMENTS"},
                    {"tool_id": call.tool_id, "error_code": "TOOL_INVALID_ARGUMENTS"},
                    None,
                )
            search_result = self.catalog.search(query)
            selected = {tool.id: tool for tool in search_result.tools}
            content: JsonObject = {
                "tools": [
                    {
                        "id": tool.id,
                        "title": tool.title,
                        "description": tool.description,
                        "input_schema": dict(tool.input_schema),
                        "required_capabilities": list(tool.required_capabilities),
                    }
                    for tool in search_result.tools
                ]
            }
            return content, {"tool_id": call.tool_id, "result": _truncate_json(content)}, selected

        descriptor = active.get(call.tool_id)
        if descriptor is None:
            return (
                {"error_code": "TOOL_NOT_ACTIVATED"},
                {"tool_id": call.tool_id, "error_code": "TOOL_NOT_ACTIVATED"},
                None,
            )
        if any(
            not _allows(self.permissions, authorization, capability)
            for capability in descriptor.required_capabilities
        ):
            return (
                {"error_code": "TOOL_PERMISSION_DENIED"},
                {"tool_id": call.tool_id, "error_code": "TOOL_PERMISSION_DENIED"},
                None,
            )
        try:
            tool_result = await delivery.request_tool(
                correlation_id=f"agent-tool:{event.id}:{call.id}",
                tool_id=call.tool_id,
                arguments=cast(Mapping[str, JsonValue], call.arguments),
                authorization=AuthorizationContextWire(
                    event_id=authorization.event_id,
                    runtime_id=authorization.runtime_id,
                    bot_id=authorization.bot_id,
                    actor_id=authorization.actor_id,
                ),
            )
        except Exception:
            return (
                {"error_code": "TOOL_UNAVAILABLE"},
                {"tool_id": call.tool_id, "error_code": "TOOL_UNAVAILABLE"},
                None,
            )
        return _tool_result_content(call.tool_id, tool_result)

    async def _complete(
        self,
        messages: Sequence[Mapping[str, object]],
        tools: Sequence[Mapping[str, object]],
    ) -> ModelReply:
        try:
            return await asyncio.wait_for(
                self.engine.complete(messages, tools=tools),
                timeout=self.model_timeout_seconds,
            )
        except TimeoutError as error:
            raise RuntimeError("agent model request timed out") from error


JsonObject = dict[str, object]


async def launch(settings: AppSettings, bridge_id: str, token: str) -> None:
    bridge = settings.broker.bridges.get(bridge_id)
    if bridge is None:
        raise RuntimeError(f"broker bridge {bridge_id!r} is not configured")
    if bridge.kind != "agent":
        raise RuntimeError(f"broker bridge {bridge_id!r} is not an agent bridge")
    _validate_agent_bridge(
        bridge.access,
        bridge.subscriptions,
        bridge.action_resources,
        bridge.tools,
        bridge.controls,
        bridge.options,
    )
    options = bridge.options
    engine = OpenAIChatEngine(
        api_key=_required_string(options, "api_key"),
        base_url=_optional_string(options, "base_url"),
        model=_required_string(options, "model"),
    )
    history_path = _history_path(settings, bridge_id, options)
    store = ConversationStore(history_path)
    permissions = _permission_policy(settings)
    catalog = AgentCatalog(tuple(definition.descriptor for definition in _sandbox_definitions(settings)))
    rag = _build_rag(settings, bridge_id, options)
    if rag is not None:
        try:
            await rag.sync()
        except Exception:
            rag.close()
            store.close()
            raise
    manifest = BridgeManifest(
        bridge_id=bridge_id,
        access=BridgeAccess.LIMITED,
        subscriptions=bridge.subscriptions,
        controls=(AGENT_HISTORY_CLEAR,),
    )
    client = BridgeClient(
        context=zmq.asyncio.Context.instance(),
        endpoints=_broker_endpoints(settings.broker.endpoint),
        generation=settings.broker.generation,
        identity=f"agent:{bridge_id}:{uuid4()}".encode("ascii"),
        manifest=manifest,
        instance_token=token,
    )
    host: AgentBridgeHost | None = None

    async def handle_delivery(delivery: BrokerDelivery) -> None:
        if host is None:
            raise RuntimeError("Agent bridge received an event before host initialization")
        await host.handle_delivery(delivery)

    async def handle_control(request: BridgeControlInvoke) -> ControlOutcome:
        if host is None:
            raise RuntimeError("Agent bridge received a control before host initialization")
        return await host.clear_history(request)

    runner = BrokerBridgeRunner(
        client,
        event_handler=handle_delivery,
        control_handlers={AGENT_HISTORY_CLEAR: handle_control},
    )
    host = AgentBridgeHost(
        runner,
        engine,
        store,
        catalog,
        permissions,
        max_concurrent_events=_positive_int_option(options, "max_concurrent_events", 16),
        history_limit=_positive_int_option(options, "history_limit", 40),
        model_timeout_seconds=_positive_float_option(options, "model_timeout_seconds", 60.0),
        event_timeout_seconds=_positive_float_option(options, "event_timeout_seconds", 120.0),
        max_tool_rounds=_positive_int_option(options, "max_tool_rounds", 4),
        rag=rag,
    )
    try:
        await runner.start()
        await runner.serve_forever()
    finally:
        try:
            await runner.stop()
        finally:
            runner.close()
            store.close()
            if rag is not None:
                rag.close()


async def launch_sandbox(settings: AppSettings, bridge_id: str, token: str) -> None:
    bridge = settings.broker.bridges.get(bridge_id)
    if bridge is None:
        raise RuntimeError(f"broker bridge {bridge_id!r} is not configured")
    if bridge.kind != "agent-sandbox":
        raise RuntimeError(f"broker bridge {bridge_id!r} is not an agent-sandbox bridge")
    _validate_sandbox_bridge(
        bridge.access,
        bridge.subscriptions,
        bridge.action_resources,
        bridge.tools,
        bridge.controls,
        bridge.options,
    )
    definitions = _sandbox_definitions(settings, bridge_id=bridge_id)
    if not definitions:
        raise RuntimeError("Agent sandbox bridge must declare at least one configured Tool")
    policy = SandboxPolicy.from_options(
        bridge.options,
        default_root=settings.core.data_dir / "bridges" / bridge_id / "sandbox",
    )
    permissions = _permission_policy(settings)
    definition_by_id = {definition.descriptor.id: definition for definition in definitions}

    async def handle_tool(request: ToolInvoke) -> ToolOutcome:
        definition = definition_by_id.get(request.tool_id)
        if definition is None:
            return ToolOutcome(success=False, error_code="TOOL_NOT_FOUND")
        authorization = AuthorizationContext(
            event_id=request.authorization.event_id,
            runtime_id=request.authorization.runtime_id,
            bot_id=request.authorization.bot_id,
            actor_id=request.authorization.actor_id,
        )
        if any(
            not _allows(permissions, authorization, capability)
            for capability in definition.descriptor.required_capabilities
        ):
            return ToolOutcome(success=False, error_code="TOOL_PERMISSION_DENIED")
        declaration = _broker_tool_declaration(definition)
        try:
            Draft202012Validator(dict(declaration.input_schema)).validate(dict(request.arguments))
        except (TypeError, ValueError, ValidationError):
            return ToolOutcome(success=False, error_code="TOOL_SCHEMA_INVALID")
        result = await execute_in_fresh_worker(definition, request.arguments, policy)
        if result.success:
            try:
                Draft202012Validator(dict(declaration.output_schema)).validate(result.result)
            except (TypeError, ValueError, ValidationError):
                return ToolOutcome(success=False, error_code="TOOL_SCHEMA_INVALID")
        return ToolOutcome(
            success=result.success,
            result=result.result,
            error_code=result.error_code,
            error_details=result.error_details,
        )

    client = BridgeClient(
        context=zmq.asyncio.Context.instance(),
        endpoints=_broker_endpoints(settings.broker.endpoint),
        generation=settings.broker.generation,
        identity=f"agent-sandbox:{bridge_id}:{uuid4()}".encode("ascii"),
        manifest=BridgeManifest(
            bridge_id=bridge_id,
            access=BridgeAccess.LIMITED,
            tools=tuple(_broker_tool_declaration(definition) for definition in definitions),
        ),
        instance_token=token,
    )
    runner = BrokerBridgeRunner(
        client,
        tool_handlers={definition.descriptor.id: handle_tool for definition in definitions},
    )
    try:
        await runner.start()
        await runner.serve_forever()
    finally:
        try:
            await runner.stop()
        finally:
            runner.close()


def _event_from_delivery(delivery: BrokerDelivery) -> EventEnvelope:
    event = EventEnvelope.model_validate(delivery.message.event.payload)
    if event.id != delivery.message.event.source_event_id:
        raise ValueError("Agent event ID does not match its broker source event")
    if event.runtime_id != delivery.message.event.source_bridge_id:
        raise ValueError("Agent event runtime_id does not match its broker source bridge")
    return event.model_copy(update={"id": delivery.message.event.kernel_event_id})


def _authorization_context(request: BridgeControlInvoke) -> AuthorizationContext:
    return AuthorizationContext(
        event_id=request.authorization.event_id,
        runtime_id=request.authorization.runtime_id,
        bot_id=request.authorization.bot_id,
        actor_id=request.authorization.actor_id,
    )


def _permission_policy(settings: AppSettings) -> PermissionPolicy | None:
    raw = settings.plugins.config.get("liteyukibot.permissions", {})
    if not isinstance(raw, Mapping):
        raise RuntimeError("permission configuration must be an object")
    return cast(PermissionPolicy, create_permission_service(cast(Mapping[str, Any], raw)))


def _allows(policy: PermissionPolicy | None, context: AuthorizationContext, capability: str) -> bool:
    return policy is not None and policy.allows(context, capability)


def _tool_schemas(tools: Iterable[Any]) -> tuple[Mapping[str, object], ...]:
    schemas: list[Mapping[str, object]] = [catalog_search_schema()]
    schemas.extend(openai_tool_schema(tool) for tool in tools)
    return tuple(schemas[:ACTIVE_TOOL_LIMIT])


def _assistant_tool_message(reply: ModelReply) -> Mapping[str, object]:
    return {
        "role": "assistant",
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.tool_id,
                    "arguments": json.dumps(dict(call.arguments), separators=(",", ":")),
                },
            }
            for call in reply.tool_calls
        ],
    }


def _tool_result_content(tool_id: str, result: ToolResult) -> tuple[JsonObject, JsonObject, None]:
    if result.success:
        content: JsonObject = {"ok": True, "result": result.result}
        return content, {"tool_id": tool_id, "ok": True, "summary": _truncate_json(result.result)}, None
    content = {"ok": False, "error_code": result.error_code or "TOOL_FAILED"}
    return content, {"tool_id": tool_id, "ok": False, "error_code": result.error_code or "TOOL_FAILED"}, None


def _append_citations(text: str, context: RagContext) -> str:
    if not text or not context.citations:
        return text
    return f"{text}\n\nSources: {', '.join(context.citations)}"


def _truncate_json(value: object, limit: int = _HISTORY_SUMMARY_LIMIT) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return encoded if len(encoded) <= limit else encoded[:limit] + "..."


def _validate_agent_bridge(
    access: str,
    subscriptions: Sequence[str],
    action_resources: Sequence[Any],
    tools: Sequence[Any],
    controls: Sequence[str],
    options: Mapping[str, Any],
) -> None:
    if access != BridgeAccess.LIMITED.value:
        raise RuntimeError("Agent bridge must use limited access")
    if not subscriptions:
        raise RuntimeError("Agent bridge must declare at least one subscription")
    if action_resources:
        raise RuntimeError("Agent bridge must not own platform actions")
    if tools:
        raise RuntimeError("Agent bridge must not own Tools; configure them on agent-sandbox bridges")
    if tuple(controls) != (AGENT_HISTORY_CLEAR,):
        raise RuntimeError("Agent bridge controls must declare agent.history.clear exactly once")
    unsupported = sorted(set(options).difference(_ALLOWED_AGENT_OPTIONS))
    if unsupported:
        raise RuntimeError("migration_required: unsupported Agent bridge options: " + ", ".join(unsupported))


def _validate_sandbox_bridge(
    access: str,
    subscriptions: Sequence[str],
    action_resources: Sequence[Any],
    tools: Sequence[Any],
    controls: Sequence[str],
    options: Mapping[str, Any],
) -> None:
    if access != BridgeAccess.LIMITED.value:
        raise RuntimeError("Agent sandbox bridge must use limited access")
    if subscriptions or action_resources or controls:
        raise RuntimeError("Agent sandbox bridge must not subscribe, own actions, or own controls")
    if not tools:
        raise RuntimeError("Agent sandbox bridge must declare at least one Tool")
    unsupported = sorted(set(options).difference(_ALLOWED_SANDBOX_OPTIONS))
    if unsupported:
        raise RuntimeError("migration_required: unsupported Agent sandbox options: " + ", ".join(unsupported))


def _sandbox_definitions(settings: AppSettings, *, bridge_id: str | None = None) -> tuple[SandboxToolDefinition, ...]:
    if bridge_id is None:
        sandboxes = tuple(
            (configured_id, bridge)
            for configured_id, bridge in settings.broker.bridges.items()
            if bridge.kind == "agent-sandbox" and bridge.tools
        )
    else:
        sandbox = settings.broker.bridges.get(bridge_id)
        if sandbox is None or sandbox.kind != "agent-sandbox":
            return ()
        sandboxes = ((bridge_id, sandbox),)
    if not sandboxes:
        return ()
    definitions = (*builtin_sandbox_tools(), *discover_sandbox_tool_definitions())
    by_id: dict[str, SandboxToolDefinition] = {}
    for definition in definitions:
        if definition.descriptor.id in by_id:
            raise RuntimeError(f"duplicate sandbox Tool definition: {definition.descriptor.id}")
        by_id[definition.descriptor.id] = definition
    selected: list[SandboxToolDefinition] = []
    selected_ids: set[str] = set()
    for configured_bridge_id, sandbox in sandboxes:
        for configured in sandbox.tools:
            selected_definition = by_id.get(configured.id)
            if selected_definition is None:
                raise RuntimeError(
                    f"configured sandbox Tool {configured.id!r} in {configured_bridge_id!r} is not installed"
                )
            declaration = _broker_tool_declaration(selected_definition)
            if (
                declaration.description != configured.description
                or dict(declaration.input_schema) != dict(configured.input_schema)
                or dict(declaration.output_schema) != dict(configured.output_schema)
                or declaration.capabilities != configured.capabilities
            ):
                raise RuntimeError(
                    f"configured sandbox Tool {configured.id!r} in {configured_bridge_id!r} "
                    "does not match its installed declaration"
                )
            if configured.id in selected_ids:
                raise RuntimeError(f"duplicate selected sandbox Tool definition: {configured.id}")
            selected_ids.add(configured.id)
            selected.append(selected_definition)
    return tuple(selected)


def _broker_tool_declaration(definition: SandboxToolDefinition) -> BrokerToolDeclaration:
    return BrokerToolDeclaration(
        id=definition.descriptor.id,
        description=definition.descriptor.description,
        input_schema=definition.descriptor.input_schema,
        output_schema={"type": "object"},
        capabilities=definition.descriptor.required_capabilities,
    )


def _history_path(settings: AppSettings, bridge_id: str, options: Mapping[str, Any]) -> Path:
    value = options.get("history_path")
    if value is None:
        return settings.core.data_dir / "bridges" / bridge_id / "history.sqlite3"
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Agent history_path must be a non-empty string")
    return Path(value)


def _build_rag(settings: AppSettings, bridge_id: str, options: Mapping[str, Any]) -> RagIndex | None:
    rag_settings = RagSettings.from_options(
        options,
        default_directory=settings.core.data_dir / "bridges" / bridge_id,
    )
    if rag_settings is None:
        return None
    provider = OpenAIEmbeddingProvider(
        api_key=rag_settings.embedding_api_key,
        base_url=rag_settings.embedding_base_url,
        model=rag_settings.embedding_model,
    )
    return RagIndex(rag_settings, provider)


def _required_string(options: Mapping[str, Any], key: str) -> str:
    value = options.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Agent option {key!r} must be a non-empty string")
    return value


def _optional_string(options: Mapping[str, Any], key: str) -> str | None:
    value = options.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Agent option {key!r} must be a non-empty string when set")
    return value


def _positive_int_option(options: Mapping[str, Any], key: str, default: int) -> int:
    value = options.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"Agent option {key!r} must be a positive integer")
    return value


def _positive_float_option(options: Mapping[str, Any], key: str, default: float) -> float:
    value = options.get(key, default)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"Agent option {key!r} must be a positive number")
    return float(value)


def _broker_endpoints(endpoint: str) -> dict[LyipLane, str]:
    parsed = urlparse(endpoint)
    if parsed.scheme != "tcp" or parsed.hostname is None or parsed.port is None:
        raise ValueError("broker endpoint must be a valid tcp URL")
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    return {
        LyipLane.CONTROL: f"tcp://{host}:{parsed.port}",
        LyipLane.BUSINESS: f"tcp://{host}:{parsed.port + 1}",
    }


__all__ = ["AgentBridgeHost", "AGENT_HISTORY_CLEAR", "launch", "launch_sandbox"]
