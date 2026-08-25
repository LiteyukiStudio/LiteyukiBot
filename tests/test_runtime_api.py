from __future__ import annotations

from collections.abc import Mapping
from importlib import metadata

import pytest

from liteyukibot import (
    AuthorizationContext,
    RuntimeBinding,
    RuntimeCallContext,
    RuntimeNamespaceProxy,
    RuntimeRequirement,
    RuntimeUnavailable,
    create_runtime_proxy,
    runtime,
    runtime_bindings,
    runtime_handler,
)
from liteyukibot.events import ConversationRef, EventEnvelope, JsonValue
from liteyukibot.plugins import ExtensionManifest


def _event() -> EventEnvelope:
    return EventEnvelope(
        runtime_id="astrbot",
        adapter="qq",
        bot_id="bot-1",
        type="message.created",
        conversation=ConversationRef(id="chat-1", type="group"),
    )


@pytest.mark.asyncio
async def test_runtime_decorator_injects_one_json_safe_proxy() -> None:
    event = _event()
    calls: list[tuple[str, Mapping[str, JsonValue]]] = []

    class Backend:
        async def invoke(
            self,
            binding: RuntimeBinding,
            operation: str,
            arguments: Mapping[str, JsonValue],
            _context: RuntimeCallContext,
        ) -> dict[str, JsonValue]:
            calls.append((f"{binding.runtime}.{binding.api}.{operation}", arguments))
            return {"ok": True}

    binding = RuntimeBinding("astrbot", "event", "^1.0", False, "astrbot")

    @runtime("astrbot", api="event", version="^1.0", as_="astrbot")
    async def handler(received: EventEnvelope, *, astrbot: RuntimeNamespaceProxy) -> object:
        assert received is event
        assert astrbot.available
        return await astrbot.call("snapshot")

    result = await runtime_handler(
        handler,
        context_factory=lambda _args, _kwargs: RuntimeCallContext(
            "example.plugin",
            event,
            AuthorizationContext(event.id, event.runtime_id, event.bot_id),
        ),
        resolver=lambda received_binding, context: RuntimeNamespaceProxy(
            received_binding,
            Backend(),
            context,
        ),
    )(event)

    assert result == {"ok": True}
    assert runtime_bindings(handler) == (binding,)
    assert calls == [("astrbot.event.snapshot", {})]


@pytest.mark.asyncio
async def test_optional_runtime_proxy_fails_closed_when_unavailable() -> None:
    binding = RuntimeBinding("astrbot", "event", "^1.0", True, "astrbot")
    context = RuntimeCallContext("example.plugin", _event(), AuthorizationContext("event", "astrbot", "bot-1"))
    proxy = RuntimeNamespaceProxy(binding, None, context)

    assert not proxy.available
    with pytest.raises(RuntimeUnavailable, match="astrbot.event"):
        await proxy.call("snapshot")


def test_runtime_requirements_are_explicit_manifest_capabilities() -> None:
    requirement = RuntimeRequirement(
        runtime="astrbot",
        api="event",
        version="^1.0",
        operations=("snapshot", "send"),
    )
    manifest = ExtensionManifest(
        id="example.runtime",
        name="Runtime Example",
        version="1.0.0",
        runtime_requirements=(requirement,),
    )

    assert manifest.runtime_capabilities == frozenset(
        {
            "runtime.astrbot.event.snapshot",
            "runtime.astrbot.event.send",
        }
    )
    with pytest.raises(ValueError, match="must not contain duplicates"):
        ExtensionManifest(
            id="example.runtime",
            name="Runtime Example",
            version="1.0.0",
            runtime_requirements=(requirement, requirement),
        )


def test_duplicate_runtime_proxy_providers_report_their_entry_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Entry:
        def __init__(self, value: str) -> None:
            self.name = "astrbot.event"
            self.value = value

    monkeypatch.setattr(
        metadata,
        "entry_points",
        lambda *, group: (Entry("provider_one:factory"), Entry("provider_two:factory")),
    )

    binding = RuntimeBinding("astrbot", "event", "^1.0", True, "astrbot")
    with pytest.raises(RuntimeError, match="provider_one:factory, provider_two:factory"):
        create_runtime_proxy(binding, None, None)
