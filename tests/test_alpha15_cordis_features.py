from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from liteyukibot_cordis import CordisManager, CordisSession, Scope
from liteyukibot_kernel import KERNEL_STATUS_SERVICE
from liteyukibot_kernel.events import (
    ActionEnvelope,
    ActionResult,
    ActorRef,
    ConversationRef,
    EventBus,
    EventEnvelope,
    HandlerFailure,
    HandlerResult,
    Message,
    Segment,
    SendMessage,
)
from liteyukibot_kernel.services import ServiceRegistry
from liteyukibot_kernel.status import KernelStatusSnapshot

from liteyukibot.features.catalog import activate_builtin_features, feature_order
from liteyukibot.features.commands import ArgumentSpec, CommandSchema, OptionSpec, integer_value, parse_command
from liteyukibot.features.commands_models import CommandInvocation, CommandSpec
from liteyukibot.features.commands_service import create_command_service
from liteyukibot.features.common import SERVICE_REGISTRY, NullTranslator
from liteyukibot.features.permissions import PERMISSION_SERVICE, create_permission_service
from liteyukibot.features.profile import PROFILE_DATABASE, PROFILE_SERVICE
from liteyukibot.features.resources import RESOURCE_SERVICE


class _Actions:
    def __init__(self) -> None:
        self.calls: list[ActionEnvelope] = []

    async def execute(self, action: ActionEnvelope, *, event: EventEnvelope | None = None) -> ActionResult:
        assert event is not None
        self.calls.append(action)
        return ActionResult(action_id=action.action_id, success=True)


def _event(text: str = "/help") -> EventEnvelope:
    return EventEnvelope(
        runtime_id="runtime",
        adapter="test",
        bot_id="bot",
        type="message",
        conversation=ConversationRef(id="conversation", type="private"),
        message=Message(segments=(Segment(type="text", data={"text": text}),)),
    )


def test_permissions_resolve_only_configured_principal_grants() -> None:
    service = create_permission_service(
        {
            "roles": {"operator": ["liteyukibot.status.read"]},
            "grants": [
                {
                    "runtime_id": "runtime",
                    "bot_id": "bot",
                    "actor_id": "user",
                    "roles": ["operator"],
                }
            ],
        }
    )
    event = _event().model_copy(update={"actor": ActorRef(id="user")})

    assert service.allows(event, "public")
    assert service.allows(event, "liteyukibot.status.read")
    assert not service.allows(event.model_copy(update={"actor": ActorRef(id="other")}), "liteyukibot.status.read")


def test_command_parser_handles_typed_arguments_and_options() -> None:
    schema = CommandSchema(
        arguments=(ArgumentSpec("count", converter=integer_value),),
        options=(OptionSpec("limit", aliases=("n",), converter=integer_value, default=10),),
    )

    parsed = parse_command("3 --limit 5", schema)
    assert parsed.arguments == {"count": 3}
    assert parsed.options == {"limit": 5}


@pytest.mark.asyncio
async def test_command_service_preserves_handler_outcomes() -> None:
    service = create_command_service({}, create_permission_service({}), _Logger())
    failure = HandlerFailure(handler="command.handler", kind="error", message="partial")
    action_result = ActionResult(action_id="action", success=False, error_code="rejected")

    async def handler(_invocation: CommandInvocation) -> HandlerResult:
        return HandlerResult(action_results=(action_result,), failures=(failure,))

    service.register(CommandSpec("ping"), handler, owner="test")
    result = await service.dispatch(_event("/ping"))

    assert result is not None
    assert result.action_results == (action_result,)
    assert result.failures == (failure,)


@pytest.mark.asyncio
async def test_minimal_cordis_preserves_ordered_handlers_and_cleanup() -> None:
    actions = _Actions()
    async def execute(event: EventEnvelope, action: ActionEnvelope) -> ActionResult:
        return await actions.execute(action, event=event)

    bus = EventBus(action_executor=execute)
    manager = CordisManager(bus, actions)
    seen: list[str] = []
    closed: list[str] = []

    async def factory(scope: Scope) -> None:
        scope.provide("value", lambda: "provided")

        async def first(session: CordisSession) -> None:
            assert await session.scope.use("value") == "provided"
            seen.append("first")
            source = session.event.envelope
            session.emit(
                ActionEnvelope(
                    runtime_id=source.runtime_id,
                    bot_id=source.bot_id,
                    action=SendMessage(
                        message=Message(segments=(Segment(type="text", data={"text": "ok"}),)),
                        conversation=source.conversation,
                    ),
                )
            )

        async def second(_session: CordisSession) -> None:
            seen.append("second")

        scope.on(second, order=2)
        scope.on(first, order=1)
        scope.own(lambda: closed.append("plugin"))

    await manager.activate("test.feature", factory)
    source = _event()
    result = await manager.dispatch(source)
    assert seen == ["first", "second"]
    assert result.failures == ()
    assert result.actions[0].event_id == source.id
    await manager.aclose()
    assert closed == ["plugin"]
    assert not hasattr(Scope, "parallel")
    assert not hasattr(Scope, "middleware")
    assert not hasattr(Scope, "route")
    assert not hasattr(Scope, "schedule")
    assert not hasattr(Scope, "tool")


@pytest.mark.asyncio
async def test_builtin_features_activate_in_dependency_order(tmp_path: Path) -> None:
    actions = _Actions()
    async def execute(event: EventEnvelope, action: ActionEnvelope) -> ActionResult:
        return await actions.execute(action, event=event)

    bus = EventBus(action_executor=execute)
    manager = CordisManager(bus, actions)
    registry = ServiceRegistry()
    manager.scope.provide(KERNEL_STATUS_SERVICE, lambda: _Status())
    manager.scope.provide(PROFILE_DATABASE, lambda: tmp_path / "profile.sqlite3")
    manager.scope.provide("liteyukibot.i18n", lambda: NullTranslator())

    scopes = await activate_builtin_features(
        manager,
        configs={"liteyukibot.essentials": {"language": "en"}},
        providers={"liteyukibot.logger": _Logger(), SERVICE_REGISTRY: registry},
    )
    assert feature_order() == tuple(scope.plugin_id for scope in scopes)
    assert manager.active_plugin_ids == feature_order()
    assert await scopes[1].use(PERMISSION_SERVICE) is await scopes[1].use(PERMISSION_SERVICE)
    assert await scopes[2].use(RESOURCE_SERVICE) is not None
    assert await scopes[3].use(PROFILE_SERVICE) is not None
    assert registry.provider_for(PERMISSION_SERVICE) == "liteyukibot.permissions"
    await manager.start()
    await bus.publish(_event())
    assert actions.calls
    await manager.aclose()
    assert registry.snapshot() == ()


class _Logger:
    def bind(self, **_values: Any) -> _Logger:
        return self

    def info(self, _message: str, *_args: Any, **_values: Any) -> None:
        return None

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        return None

    def exception(self, message: str, *args: Any, **kwargs: Any) -> None:
        return None

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        return None


class _Status:
    def snapshot(self) -> KernelStatusSnapshot:
        return KernelStatusSnapshot(
            version="test",
            state="ready",
            uptime_seconds=0,
            features={},
            events_outstanding=0,
        )
