"""NoneBot bridge host for the standalone Liteyuki broker."""

from __future__ import annotations

import asyncio
import importlib
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import zmq.asyncio

from liteyukibot.broker import (
    MESSAGE_SEND_KIND,
    ActionOutcome,
    ActionRequest,
    ActionResourceDeclaration,
    BridgeAccess,
    BridgeClient,
    BridgeManifest,
    BrokerBridgeRunner,
    EventIngress,
    MessageSendPayload,
    parse_message_send_request,
)
from liteyukibot.config import AppSettings
from liteyukibot.events import EventEnvelope
from liteyukibot.logging import get_logger
from liteyukibot.lyip import LyipLane

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
        self.nonebot = nonebot
        self.runner = runner
        self.bridge_id = bridge_id
        self.options = dict(options or {})
        self.events: OrderedDict[str, tuple[Any, Any]] = OrderedDict()
        self._serve_task: asyncio.Task[None] | None = None

    def install(self) -> None:
        """Install the fixed B5 ingress and message.send action owner."""

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
            envelope = normalize_event(bot, event)
            if envelope.reply_token is not None:
                self.events[envelope.reply_token] = (bot, event)
                self.events.move_to_end(envelope.reply_token)
                while len(self.events) > 2048:
                    self.events.popitem(last=False)
            await runner.client.send_event_ingress(self.event_ingress(envelope))

        adapters = importlib.import_module("nonebot.adapters")
        forward.__annotations__ = {
            "bot": adapters.Bot,
            "event": adapters.Event,
            "return": None,
        }
        importlib.import_module("nonebot.message").event_preprocessor(forward)

        async def on_startup() -> None:
            await runner.start()
            self._serve_task = asyncio.create_task(runner.serve_forever(), name="liteyuki-nonebot-broker")

        async def on_shutdown() -> None:
            if self._serve_task is not None:
                self._serve_task.cancel()
                await asyncio.gather(self._serve_task, return_exceptions=True)
                self._serve_task = None
            await runner.stop()
            runner.close()

        driver.on_startup(on_startup)
        driver.on_shutdown(on_shutdown)

    @staticmethod
    def event_ingress(envelope: EventEnvelope) -> EventIngress:
        """Create the sole B5 NoneBot ingress shape from one normalized message."""

        return EventIngress(
            source_event_id=envelope.id,
            topic=MESSAGE_CREATED_TOPIC,
            ordering_key=envelope.conversation.ordering_key,
            payload=envelope.model_dump(mode="json"),
        )

    async def execute_message_send(self, request: ActionRequest) -> ActionOutcome:
        """Execute the sole B5 portable action in the selected native adapter."""

        try:
            payload = parse_message_send_request(request, owner_bridge_id=self.bridge_id)
            result = await self._send_message(payload)
        except (AdapterContractError, KeyError, ValueError) as error:
            return ActionOutcome(success=False, payload={"error": "message_send_failed", "message": str(error)})
        return ActionOutcome(success=True, payload=json_value(result))

    async def _send_message(self, payload: MessageSendPayload) -> Any:
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
    """Launch a configured NoneBot bridge without nesting the CLI event loop."""

    await asyncio.to_thread(_run_nonebot, settings, bridge_id, token)


def _run_nonebot(settings: AppSettings, bridge_id: str, token: str) -> None:
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
            ActionResourceDeclaration(kind=item.kind, resource_prefix=item.resource_prefix)
            for item in bridge.action_resources
        ),
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
        if host is None:
            raise RuntimeError("NoneBot action handler was invoked before host initialization")
        return await host.execute_message_send(request)

    runner = BrokerBridgeRunner(client, action_handlers={MESSAGE_SEND_KIND: execute_action})
    host = NoneBotHost(nonebot, runner, bridge_id, bridge.options)
    host.install()
    logger.info("starting NoneBot broker bridge {}", bridge_id)
    nonebot.run()


def _broker_endpoints(endpoint: str) -> dict[LyipLane, str]:
    parsed = urlparse(endpoint)
    if parsed.scheme != "tcp" or parsed.hostname is None or parsed.port is None:
        raise ValueError("broker endpoint must be a valid tcp URL")
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    return {
        LyipLane.CONTROL: f"tcp://{host}:{parsed.port}",
        LyipLane.BUSINESS: f"tcp://{host}:{parsed.port + 1}",
    }


def _portable_send_action(payload: MessageSendPayload) -> Any:
    """Adapt the retained native conversion helper without reviving ActionEnvelope."""

    from liteyukibot.events import SendMessage

    return SendMessage(
        message=payload.message,
        conversation=payload.conversation,
        reply_token=payload.reply_token,
    )


def _mapping_option(options: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = options.get(key, {})
    if not isinstance(value, Mapping):
        raise ValueError(f"NoneBot bridge option {key!r} must be an object")
    return dict(value)


def _string_list_option(options: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = options.get(key, ())
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"NoneBot bridge option {key!r} must be an array of strings")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"NoneBot bridge option {key!r} must contain non-empty strings")
    return tuple(item.strip() for item in value)


def _load_symbol(spec: str) -> Any:
    module_name, separator, attribute = spec.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError(f"NoneBot adapter must use module:attribute syntax: {spec}")
    return getattr(importlib.import_module(module_name), attribute)


__all__ = ["MESSAGE_CREATED_TOPIC", "NoneBotHost", "launch"]
