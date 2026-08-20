from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest
from liteyukibot_functions import (
    Alpha7FunctionHostProvider,
    FunctionRuntime,
    PreflightResult,
    parse,
    preflight,
)

from liteyukibot import AuthorizationContext
from liteyukibot.events import ActorRef, ConversationRef, EventEnvelope
from liteyukibot.functions import FunctionHostBindings, FunctionPackSource


def test_alpha7_parser_builds_immutable_ast_and_tuple_bindings() -> None:
    result = parse(
        "\n".join(
            (
                "@version 1.0",
                "/// greeting",
                "fn greet(name) {",
                "    let (first, _) = (name, null)",
                '    return {"message": "hello {first}"}',
                "}",
            )
        ),
        source_id="pack:functions/main.lyf",
    )

    assert result.ok
    assert result.program is not None
    function = result.program.functions[0]
    assert function.documentation == "greeting"
    assert function.parameters == ("name",)
    with pytest.raises(FrozenInstanceError):
        cast(Any, function).name = "changed"


@pytest.mark.asyncio
async def test_alpha7_preflight_and_runtime_execute_json_subset() -> None:
    source = "\n".join(
        (
            "@version 1.0",
            "fn greet(name) {",
            "    let (first, _) = (name, null)",
            '    return {"message": "hello {first}"}',
            "}",
        )
    )
    checked = preflight(parse(source, source_id="pack:functions/main.lyf"))

    assert checked.ok
    assert isinstance(checked, PreflightResult)
    assert await FunctionRuntime(checked).invoke("greet", {"name": "Liteyuki"}) == {"message": "hello Liteyuki"}


def test_alpha7_preflight_reports_parse_only_and_migration_nodes() -> None:
    source = "\n".join(
        (
            "@version 1.0",
            "sync fn old() { while true { pass } }",
            "var legacy=1",
        )
    )
    checked = preflight(parse(source, source_id="pack:functions/old.lyf"))
    codes = {diagnostic.code for diagnostic in checked.diagnostics}

    assert "LYF_UNSUPPORTED_SYNTAX" in codes
    assert "migration_required" in codes
    with pytest.raises(ValueError, match="preflighted"):
        FunctionRuntime(checked)


@pytest.mark.asyncio
async def test_public_host_provider_preflights_contributions_and_invokes_tools() -> None:
    source = "\n".join(
        (
            "@version 1.0",
            '@agent(tool, name="say", description="Say hello", '
            'input={"type": "object", "properties": '
            '{"name": {"type": "string"}}, "required": ["name"]}, '
            'output={"type": "object"})',
            'fn say(name) { return {"message": "hello {name}"} }',
            '@events("chat.message")',
            "async fn on_message(event) { return event }",
        )
    )
    provider = Alpha7FunctionHostProvider()
    preflighted = provider.preflight((FunctionPackSource("example", "pack", {"functions/main.lyf": source.encode()}),))

    registered_tools: dict[str, Any] = {}
    registered_events: list[Any] = []
    bindings = FunctionHostBindings(
        extension_id="example",
        config={},
        events=cast(Any, None),
        services=cast(Any, None),
        tasks=cast(Any, None),
        logger=cast(Any, None),
        register_tool=lambda declaration, callback: registered_tools.setdefault(declaration.id, callback),
        register_event=lambda contribution, callback: registered_events.append((contribution, callback)),
    )
    host = provider.create_host(preflighted, bindings)

    assert preflighted.function_ids == ("say", "on_message")
    assert set(registered_tools) == {"example.lyf.say"}
    assert len(registered_events) == 1
    assert await host.invoke("say", {"name": "world"}) == {"message": "hello world"}
    assert await registered_tools["example.lyf.say"](
        AuthorizationContext("event-1", "runtime-1", "bot-1"), {"name": "tool"}
    ) == {"message": "hello tool"}

    await host.aclose()
    with pytest.raises(RuntimeError):
        await host.invoke("say", {"name": "closed"})


@pytest.mark.asyncio
async def test_public_host_event_handlers_preserve_zero_and_one_parameter_signatures() -> None:
    source = "\n".join(
        (
            "@version 1.0",
            '@events("chat.message")',
            "fn on_empty() {}",
            '@events("chat.message")',
            "fn on_event(event) { return event }",
        )
    )
    provider = Alpha7FunctionHostProvider()
    preflighted = provider.preflight((FunctionPackSource("example", "pack", {"main.lyf": source.encode()}),))
    callbacks: list[Any] = []
    bindings = FunctionHostBindings(
        extension_id="example",
        config={},
        events=cast(Any, None),
        services=cast(Any, None),
        tasks=cast(Any, None),
        logger=cast(Any, None),
        register_tool=lambda _declaration, _callback: None,
        register_event=lambda contribution, callback: callbacks.append((contribution, callback)),
    )
    host = provider.create_host(preflighted, bindings)
    event = EventEnvelope(
        id="event-1",
        runtime_id="runtime-1",
        adapter="test",
        bot_id="bot-1",
        type="chat.message",
        conversation=ConversationRef(id="conversation-1", type="group"),
        actor=ActorRef(id="actor-1"),
    )

    assert [item.parameters for item in preflighted.events] == [(), ("event",)]
    await callbacks[0][1](event)
    await callbacks[1][1](event)
    await host.aclose()
