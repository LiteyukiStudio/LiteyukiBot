"""NoneBot bridge host for the standalone Liteyuki broker."""

from __future__ import annotations

import asyncio
import importlib
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from typing import Any, cast
from urllib.parse import urlparse
from uuid import uuid4

import zmq.asyncio

from liteyukibot.broker import (
    MESSAGE_SEND_KIND,
    ActionOutcome,
    ActionRequest,
    ActionResourceDeclaration,
    BoundedIngressPublisher,
    BridgeAccess,
    BridgeClient,
    BridgeManifest,
    BrokerBridgeRunner,
    EventIngress,
    MessageSendPayload,
    RuntimeApiDeclaration,
    RuntimeApiInvoke,
    RuntimeApiOutcome,
    parse_message_send_request,
    portable_runtime_api_catalog,
)
from liteyukibot.config import AppSettings
from liteyukibot.events import ConversationRef, EventEnvelope, JsonValue, Message, Segment
from liteyukibot.logging import get_logger
from liteyukibot.lyip import LyipLane
from liteyukibot.runtime_api import BotSnapshot, EventSnapshot, SendResult

from .contracts import AdapterContractError, adapter_id, json_value, normalize_event, send_proactive, to_native_message

logger = get_logger(component="nonebot")
MESSAGE_CREATED_TOPIC = "message.created"


class NoneBotHost:
    """Own one initialized NoneBot process and its broker-facing callbacks."""

    def __init__(
        self,
        nonebot: Any,
        runner: BrokerBridgeRunner | None,
        bridge_id: str,
        options: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialize the none bot host.

        Args:
            nonebot: The nonebot value used by the operation.
            runner: The runner value used by the operation.
            bridge_id: Stable identifier for the bridge.
            options: Validated optional settings for the operation.

        Returns:
            None.
        """
        self.nonebot = nonebot
        self.runner = runner
        self.bridge_id = bridge_id
        self.options = dict(options or {})
        self.events: OrderedDict[str, tuple[Any, Any]] = OrderedDict()
        self._events_by_source_id: OrderedDict[str, tuple[Any, Any, EventEnvelope]] = OrderedDict()
        self._serve_task: asyncio.Task[None] | None = None
        self._ingress_publisher: BoundedIngressPublisher[EventIngress] | None = None

    def install(self) -> None:
        """Install the fixed B5 ingress and message.send action owner.

        Returns:
            None.
        """

        if self.runner is None:
            raise RuntimeError("NoneBot host requires a broker bridge runner before installation")
        runner = self.runner
        config = _mapping_option(self.options, "config")
        configured_adapters = _string_list_option(self.options, "adapters")
        configured_plugins = _string_list_option(self.options, "plugins")
        configured_directories = _string_list_option(self.options, "plugin_dirs")
        self.nonebot.init(**config)
        driver = self.nonebot.get_driver()
        for spec in configured_adapters:
            driver.register_adapter(_load_symbol(spec))
        for plugin_name in configured_plugins:
            if self.nonebot.load_plugin(plugin_name) is None:
                raise RuntimeError(f"failed to load NoneBot plugin: {plugin_name}")
        for directory in configured_directories:
            loaded = self.nonebot.load_plugins(directory)
            if not loaded:
                raise RuntimeError(f"NoneBot plugin directory loaded no plugins: {directory}")

        async def forward(bot: Any, event: Any) -> None:
            """Implement the forward operation for the install.

            Args:
                bot: The bot value used by the operation.
                event: Event associated with the operation.

            Returns:
                None.

            Notes:
                Internal implementation detail for `NoneBotHost.install.forward`. It delegates to
                `normalize_event`, `move_to_end`, `popitem`, `submit` while keeping intermediate state local to
                the owning operation.
            """
            envelope = normalize_event(bot, event, runtime_id=self.bridge_id)
            if envelope.reply_token is not None:
                self.events[envelope.reply_token] = (bot, event)
                self.events.move_to_end(envelope.reply_token)
                while len(self.events) > 2048:
                    self.events.popitem(last=False)
            self._events_by_source_id[envelope.id] = (bot, event, envelope)
            self._events_by_source_id.move_to_end(envelope.id)
            while len(self._events_by_source_id) > 2048:
                self._events_by_source_id.popitem(last=False)
            publisher = self._ingress_publisher
            if publisher is not None:
                publisher.submit(self.event_ingress(envelope))

        adapters = importlib.import_module("nonebot.adapters")
        forward.__annotations__ = {
            "bot": adapters.Bot,
            "event": adapters.Event,
            "return": None,
        }
        importlib.import_module("nonebot.message").event_preprocessor(forward)

        async def send_ingress(ingress: EventIngress) -> None:
            """Send ingress.

            Args:
                ingress: The ingress value used by the operation.

            Returns:
                None.

            Notes:
                Internal implementation detail for `NoneBotHost.install.send_ingress`. It delegates to
                `send_event_ingress` while keeping intermediate state local to the owning operation.
            """
            await runner.client.send_event_ingress(ingress)

        self._ingress_publisher = BoundedIngressPublisher(
            send_ingress,
            on_error=self._report_ingress_error,
            task_name=f"liteyuki-nonebot-ingress:{self.bridge_id}",
        )

        async def on_startup() -> None:
            """Implement the on startup operation for the install.

            Returns:
                None.

            Notes:
                Internal implementation detail for `NoneBotHost.install.on_startup`. It delegates to `start`,
                `create_task`, `serve_forever` while keeping intermediate state local to the owning operation.
            """
            await runner.start()
            assert self._ingress_publisher is not None
            await self._ingress_publisher.start()
            self._serve_task = asyncio.create_task(runner.serve_forever(), name="liteyuki-nonebot-broker")

        async def on_shutdown() -> None:
            """Implement the on shutdown operation for the install.

            Returns:
                None.

            Notes:
                Internal implementation detail for `NoneBotHost.install.on_shutdown`. It delegates to `cancel`,
                `gather`, `close`, `stop` while keeping intermediate state local to the owning operation.
            """
            if self._serve_task is not None:
                self._serve_task.cancel()
                await asyncio.gather(self._serve_task, return_exceptions=True)
                self._serve_task = None
            try:
                if self._ingress_publisher is not None:
                    await self._ingress_publisher.close()
            finally:
                await runner.stop()
                runner.close()

        driver.on_startup(on_startup)
        driver.on_shutdown(on_shutdown)

    def _report_ingress_error(self, error: Exception) -> None:
        """Implement the report ingress error operation for the none bot host.

        Args:
            error: The error value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `NoneBotHost._report_ingress_error`. It delegates to
            `warning`, `bind` while keeping intermediate state local to the owning operation.
        """
        logger.bind(runtime=self.bridge_id, component="ingress").warning(
            "NoneBot broker ingress delivery failed: {}",
            type(error).__name__,
        )

    @staticmethod
    def event_ingress(envelope: EventEnvelope) -> EventIngress:
        """Create the sole B5 NoneBot ingress shape from one normalized message.

        Args:
            envelope: The envelope value used by the operation.

        Returns:
            The `EventIngress` result produced by the operation.
        """

        return EventIngress(
            source_event_id=envelope.id,
            topic=MESSAGE_CREATED_TOPIC,
            ordering_key=envelope.conversation.ordering_key,
            payload=envelope.model_dump(mode="json"),
        )

    async def execute_message_send(self, request: ActionRequest) -> ActionOutcome:
        """Execute the sole B5 portable action in the selected native adapter.

        Args:
            request: Validated request object to process.

        Returns:
            The `ActionOutcome` result produced by the operation.
        """

        try:
            payload = parse_message_send_request(request, owner_bridge_id=self.bridge_id)
            result = await self._send_message(payload)
        except (AdapterContractError, KeyError, ValueError) as error:
            return ActionOutcome(success=False, payload={"error": "message_send_failed", "message": str(error)})
        return ActionOutcome(success=True, payload=json_value(result))

    async def execute_runtime_api(self, request: RuntimeApiInvoke) -> RuntimeApiOutcome:
        """Execute runtime api.

        Args:
            request: Validated request object to process.

        Returns:
            The `RuntimeApiOutcome` result produced by the operation.
        """
        target = self._events_by_source_id.get(request.source_event_id)
        if target is None:
            return RuntimeApiOutcome(success=False, error_code="RUNTIME_EVENT_UNAVAILABLE")
        bot, event, envelope = target
        if request.api_id == "event.snapshot":
            if request.arguments:
                return RuntimeApiOutcome(success=False, error_code="RUNTIME_API_INVALID_ARGUMENTS")
            return RuntimeApiOutcome(success=True, result=_event_snapshot(envelope))
        if request.api_id == "event.send":
            if request.authorization.bot_id != str(bot.self_id):
                return RuntimeApiOutcome(success=False, error_code="RUNTIME_API_AUTHORIZATION_MISMATCH")
            try:
                if set(request.arguments) != {"message"}:
                    raise ValueError("event.send accepts only message")
                message = _runtime_message(request.arguments["message"])
                native = to_native_message(adapter_id(str(bot.adapter.get_name())), message)
            except (AdapterContractError, TypeError, ValueError):
                return RuntimeApiOutcome(success=False, error_code="RUNTIME_API_INVALID_ARGUMENTS")
            try:
                result = await bot.send(event, native)
            except Exception:
                return RuntimeApiOutcome(success=False, error_code="RUNTIME_API_SEND_FAILED")
            return RuntimeApiOutcome(success=True, result=_send_result(result))
        if request.api_id == "bot.snapshot":
            if request.arguments:
                return RuntimeApiOutcome(success=False, error_code="RUNTIME_API_INVALID_ARGUMENTS")
            if request.authorization.bot_id != str(bot.self_id):
                return RuntimeApiOutcome(success=False, error_code="RUNTIME_API_AUTHORIZATION_MISMATCH")
            return RuntimeApiOutcome(success=True, result=_bot_snapshot(bot))
        if request.api_id == "bot.send":
            try:
                if set(request.arguments) != {"bot_id", "message", "conversation"}:
                    raise ValueError("bot.send requires bot_id, message, and conversation")
                bot_id = request.arguments["bot_id"]
                if bot_id != request.authorization.bot_id:
                    raise ValueError("bot.send bot ID does not match the active event")
                payload = MessageSendPayload(
                    bot_id=bot_id,
                    message=_runtime_message(request.arguments["message"]),
                    conversation=_runtime_conversation(request.arguments["conversation"]),
                )
                result = await self._send_message(payload)
            except (AdapterContractError, KeyError, TypeError, ValueError):
                return RuntimeApiOutcome(success=False, error_code="RUNTIME_API_INVALID_ARGUMENTS")
            except Exception:
                return RuntimeApiOutcome(success=False, error_code="RUNTIME_API_SEND_FAILED")
            return RuntimeApiOutcome(success=True, result=_send_result(result))
        return RuntimeApiOutcome(success=False, error_code="RUNTIME_API_NOT_REGISTERED")

    async def _send_message(self, payload: MessageSendPayload) -> Any:
        """Send message.

        Args:
            payload: JSON-safe payload carried by the operation.

        Returns:
            The `Any` result produced by the operation.

        Notes:
            Internal implementation detail for `NoneBotHost._send_message`. It delegates to `get_bot`,
            `adapter_id`, `get_name`, `to_native_message` while keeping intermediate state local to the
            owning operation.
        """
        bot = self.nonebot.get_bot(payload.bot_id)
        selected_adapter = adapter_id(str(bot.adapter.get_name()))
        message = to_native_message(selected_adapter, payload.message)
        if payload.reply_token is not None:
            target = self.events.get(payload.reply_token)
            if target is None:
                raise AdapterContractError("reply token is unknown or expired")
            target_bot, event = target
            if str(target_bot.self_id) != payload.bot_id:
                raise AdapterContractError("reply token belongs to a different bot")
            target_adapter = adapter_id(str(target_bot.adapter.get_name()))
            if target_adapter != selected_adapter:
                raise AdapterContractError("reply token belongs to a different adapter")
            return await target_bot.send(event, message)
        return await send_proactive(bot, selected_adapter, _portable_send_action(payload), message)


async def launch(settings: AppSettings, bridge_id: str, token: str) -> None:
    """Launch a configured NoneBot bridge without nesting the CLI event loop.

    Args:
        settings: Validated application settings.
        bridge_id: Stable identifier for the bridge.
        token: Authentication token presented at the boundary.

    Returns:
        None.
    """

    await asyncio.to_thread(_run_nonebot, settings, bridge_id, token)


def _run_nonebot(settings: AppSettings, bridge_id: str, token: str) -> None:
    """Run nonebot.

    Args:
        settings: Validated application settings.
        bridge_id: Stable identifier for the bridge.
        token: Authentication token presented at the boundary.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_run_nonebot`. It delegates to `get`, `import_module`,
        `_runtime_api_declarations`, `instance` while keeping intermediate state local to the owning
        operation.
    """
    bridge = settings.broker.bridges.get(bridge_id)
    if bridge is None:
        raise RuntimeError(f"broker bridge {bridge_id!r} is not configured")
    if bridge.kind != "nonebot":
        raise RuntimeError(f"broker bridge {bridge_id!r} is not a NoneBot bridge")
    try:
        nonebot = importlib.import_module("nonebot")
    except ModuleNotFoundError as error:
        raise RuntimeError("NoneBot bridge is not installed; install liteyukibot-v7-runtime-nonebot") from error

    manifest = BridgeManifest(
        bridge_id=bridge_id,
        access=BridgeAccess(bridge.access),
        subscriptions=bridge.subscriptions,
        action_resources=tuple(
            ActionResourceDeclaration(
                kind=item.kind,
                resource=item.resource,
                resource_prefix=item.resource_prefix,
            )
            for item in bridge.action_resources
        ),
        runtime_apis=_runtime_api_declarations(),
    )
    client = BridgeClient(
        context=zmq.asyncio.Context.instance(),
        endpoints=_broker_endpoints(settings.broker.endpoint),
        generation=settings.broker.generation,
        identity=f"nonebot:{bridge_id}:{uuid4()}".encode("ascii"),
        manifest=manifest,
        instance_token=token,
    )
    host: NoneBotHost | None = None

    async def execute_action(request: ActionRequest) -> ActionOutcome:
        """Execute action.

        Args:
            request: Validated request object to process.

        Returns:
            The `ActionOutcome` result produced by the operation.

        Notes:
            Internal implementation detail for `_run_nonebot.execute_action`. It delegates to
            `execute_message_send` while keeping intermediate state local to the owning operation.
        """
        if host is None:
            raise RuntimeError("NoneBot action handler was invoked before host initialization")
        return await host.execute_message_send(request)

    async def execute_runtime_api(request: RuntimeApiInvoke) -> RuntimeApiOutcome:
        """Execute runtime api.

        Args:
            request: Validated request object to process.

        Returns:
            The `RuntimeApiOutcome` result produced by the operation.

        Notes:
            Internal implementation detail for `_run_nonebot.execute_runtime_api`. It delegates to
            `execute_runtime_api` while keeping intermediate state local to the owning operation.
        """
        if host is None:
            raise RuntimeError("NoneBot runtime API handler was invoked before host initialization")
        return await host.execute_runtime_api(request)

    runner = BrokerBridgeRunner(
        client,
        action_handlers={MESSAGE_SEND_KIND: execute_action},
        runtime_api_handlers={
            "event.snapshot": execute_runtime_api,
            "event.send": execute_runtime_api,
            "bot.snapshot": execute_runtime_api,
            "bot.send": execute_runtime_api,
        },
    )
    host = NoneBotHost(nonebot, runner, bridge_id, bridge.options)
    host.install()
    logger.info("starting NoneBot broker bridge {}", bridge_id)
    nonebot.run()


def _broker_endpoints(endpoint: str) -> dict[LyipLane, str]:
    """Implement the broker endpoints operation for the component.

    Args:
        endpoint: Transport endpoint used for the connection.

    Returns:
        The `dict[LyipLane, str]` result produced by the operation.

    Notes:
        Internal implementation detail for `_broker_endpoints`. It delegates to `urlparse` while keeping
        intermediate state local to the owning operation.
    """
    parsed = urlparse(endpoint)
    if parsed.scheme != "tcp" or parsed.hostname is None or parsed.port is None:
        raise ValueError("broker endpoint must be a valid tcp URL")
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    return {
        LyipLane.CONTROL: f"tcp://{host}:{parsed.port}",
        LyipLane.BUSINESS: f"tcp://{host}:{parsed.port + 1}",
    }


def _portable_send_action(payload: MessageSendPayload) -> Any:
    """Adapt the retained native conversion helper without reviving ActionEnvelope.

    Args:
        payload: JSON-safe payload carried by the operation.

    Returns:
        The `Any` result produced by the operation.

    Notes:
        Internal implementation detail for `_portable_send_action`. It performs the local state
        transition directly and is not a stable extension boundary.
    """

    from liteyukibot.events import SendMessage

    return SendMessage(
        message=payload.message,
        conversation=payload.conversation,
        reply_token=payload.reply_token,
    )


def _event_snapshot(envelope: EventEnvelope) -> dict[str, JsonValue]:
    """Implement the event snapshot operation for the component.

    Args:
        envelope: The envelope value used by the operation.

    Returns:
        The `dict[str, JsonValue]` result produced by the operation.

    Notes:
        Internal implementation detail for `_event_snapshot`. It delegates to `cast`, `model_dump` while
        keeping intermediate state local to the owning operation.
    """
    return cast(
        dict[str, JsonValue],
        EventSnapshot(
            source_event_id=envelope.id,
            runtime_id=envelope.runtime_id,
            adapter=envelope.adapter,
            bot_id=envelope.bot_id,
            event_type=envelope.type,
            conversation=envelope.conversation,
            actor=envelope.actor,
            message=envelope.message,
        ).model_dump(mode="json"),
    )


def _bot_snapshot(bot: Any) -> dict[str, JsonValue]:
    """Implement the bot snapshot operation for the component.

    Args:
        bot: The bot value used by the operation.

    Returns:
        The `dict[str, JsonValue]` result produced by the operation.

    Notes:
        Internal implementation detail for `_bot_snapshot`. It delegates to `cast`, `model_dump`,
        `adapter_id`, `get_name` while keeping intermediate state local to the owning operation.
    """
    return cast(
        dict[str, JsonValue],
        BotSnapshot(
            bot_id=str(bot.self_id),
            adapter=adapter_id(str(bot.adapter.get_name())),
            capabilities=("message.send",),
        ).model_dump(mode="json"),
    )


def _send_result(value: object) -> dict[str, JsonValue]:
    """Send result.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `dict[str, JsonValue]` result produced by the operation.

    Notes:
        Internal implementation detail for `_send_result`. It delegates to `cast`, `model_dump`,
        `json_value` while keeping intermediate state local to the owning operation.
    """
    return cast(
        dict[str, JsonValue],
        SendResult(sent=True, result=json_value(value)).model_dump(mode="json"),
    )


def _runtime_message(value: object) -> Message:
    """Implement the runtime message operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `Message` result produced by the operation.

    Notes:
        Internal implementation detail for `_runtime_message`. It delegates to `strip`, `model_validate`
        while keeping intermediate state local to the owning operation.
    """
    if isinstance(value, str):
        if not value.strip():
            raise ValueError("runtime message text must not be blank")
        return Message(segments=(Segment(type="text", data={"text": value}),))
    if not isinstance(value, Mapping):
        raise TypeError("runtime message must be text or a portable Message object")
    return Message.model_validate(value)


def _runtime_conversation(value: object) -> ConversationRef:
    """Implement the runtime conversation operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `ConversationRef` result produced by the operation.

    Notes:
        Internal implementation detail for `_runtime_conversation`. It delegates to `model_validate`
        while keeping intermediate state local to the owning operation.
    """
    if not isinstance(value, Mapping):
        raise TypeError("runtime conversation must be a portable ConversationRef object")
    return ConversationRef.model_validate(value)


def _runtime_api_declarations() -> tuple[RuntimeApiDeclaration, ...]:
    """Implement the runtime api declarations operation for the component.

    Returns:
        The `tuple[RuntimeApiDeclaration, ...]` result produced by the operation.

    Notes:
        Internal implementation detail for `_runtime_api_declarations`. It delegates to
        `portable_runtime_api_catalog` while keeping intermediate state local to the owning operation.
    """
    return portable_runtime_api_catalog("nonebot")


def _mapping_option(options: Mapping[str, Any], key: str) -> dict[str, Any]:
    """Implement the mapping option operation for the component.

    Args:
        options: Validated optional settings for the operation.
        key: Stable FIFO ordering key for the queued work.

    Returns:
        The `dict[str, Any]` result produced by the operation.

    Notes:
        Internal implementation detail for `_mapping_option`. It delegates to `get` while keeping
        intermediate state local to the owning operation.
    """
    value = options.get(key, {})
    if not isinstance(value, Mapping):
        raise ValueError(f"NoneBot bridge option {key!r} must be an object")
    return dict(value)


def _string_list_option(options: Mapping[str, Any], key: str) -> tuple[str, ...]:
    """Implement the string list option operation for the component.

    Args:
        options: Validated optional settings for the operation.
        key: Stable FIFO ordering key for the queued work.

    Returns:
        The `tuple[str, ...]` result produced by the operation.

    Notes:
        Internal implementation detail for `_string_list_option`. It delegates to `get`, `any`, `strip`
        while keeping intermediate state local to the owning operation.
    """
    value = options.get(key, ())
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"NoneBot bridge option {key!r} must be an array of strings")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"NoneBot bridge option {key!r} must contain non-empty strings")
    return tuple(item.strip() for item in value)


def _load_symbol(spec: str) -> Any:
    """Load symbol.

    Args:
        spec: The spec value used by the operation.

    Returns:
        The `Any` result produced by the operation.

    Notes:
        Internal implementation detail for `_load_symbol`. It delegates to `partition`, `getattr`,
        `import_module` while keeping intermediate state local to the owning operation.
    """
    module_name, separator, attribute = spec.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError(f"NoneBot adapter must use module:attribute syntax: {spec}")
    return getattr(importlib.import_module(module_name), attribute)


__all__ = ["MESSAGE_CREATED_TOPIC", "NoneBotHost", "launch"]
