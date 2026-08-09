"""NoneBot2 host runtime and protocol-neutral event bridge."""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import threading
from collections import OrderedDict
from collections.abc import Callable, Coroutine, Mapping, Sequence
from concurrent.futures import Future
from typing import Any
from uuid import uuid4

from yukilog import configure_child_runtime, get_logger

from ..events import (
    ActionEnvelope,
    ActorRef,
    CallApi,
    ConversationRef,
    EventEnvelope,
    Message,
    Segment,
    SendMessage,
)
from .client import RuntimeClient
from .protocol import (
    ActionRequest,
    ActionResponse,
    EventMessage,
    Shutdown,
    WireMessage,
    json_mapping,
)

logger = get_logger(component="nonebot", runtime=os.environ.get("LITEYUKI_RUNTIME_ID"))
type ActionHandler = Callable[
    [Mapping[str, Any]],
    Coroutine[Any, Any, tuple[bool, Any, str | None]],
]


class SupervisorBridge:
    def __init__(self) -> None:
        self.options: Mapping[str, Any] = {}
        self._configured = threading.Event()
        self._thread = threading.Thread(target=self._thread_main, name="liteyuki-nonebot-ipc", daemon=True)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client: RuntimeClient | None = None
        self._action_handler: ActionHandler | None = None
        self._shutdown: Callable[[], None] | None = None
        self._main_loop: asyncio.AbstractEventLoop | None = None

    def start(self) -> Mapping[str, Any]:
        self._thread.start()
        if not self._configured.wait(timeout=10):
            raise TimeoutError("NoneBot runtime did not receive supervisor configuration")
        return self.options

    def set_handlers(
        self,
        action_handler: ActionHandler,
        shutdown: Callable[[], None],
        main_loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._action_handler = action_handler
        self._shutdown = shutdown
        self._main_loop = main_loop

    def ready(self) -> None:
        if self._client is None:
            raise RuntimeError("NoneBot supervisor bridge is not connected")
        self._submit(
            self._client.ready(("nonebot.plugins", "nonebot.events", "nonebot.actions"))
        ).result(10)

    def emit_event(self, event: EventEnvelope) -> None:
        future = self._submit(
            self._send(EventMessage(correlation_id=event.id, payload=event.model_dump(mode="json")))
        )
        future.add_done_callback(self._report_send_failure)

    def close(self) -> None:
        self._thread.join(timeout=10)

    def _submit(self, awaitable: Coroutine[Any, Any, None]) -> Future[None]:
        if self._loop is None:
            raise RuntimeError("NoneBot supervisor bridge is not connected")
        return asyncio.run_coroutine_threadsafe(awaitable, self._loop)

    @staticmethod
    def _report_send_failure(future: Future[None]) -> None:
        error = future.exception()
        if error is not None:
            logger.error("failed to forward NoneBot event: {}", error)

    def _thread_main(self) -> None:
        asyncio.run(self._run())

    async def _run(self) -> None:
        self._loop = asyncio.get_running_loop()
        client = RuntimeClient.from_environment("nonebot")
        self._client = client
        self.options = await client.connect()
        self._configured.set()
        try:
            while True:
                message = await client.receive()
                if isinstance(message, Shutdown):
                    if self._shutdown is not None:
                        self._shutdown()
                    return
                if isinstance(message, ActionRequest):
                    await self._handle_action(message)
        finally:
            await client.close()

    async def _handle_action(self, request: ActionRequest) -> None:
        if self._action_handler is None or self._main_loop is None:
            response = ActionResponse(
                correlation_id=request.correlation_id,
                ok=False,
                error="NoneBot driver is not ready",
            )
        else:
            future: Future[tuple[bool, Any, str | None]] = asyncio.run_coroutine_threadsafe(
                self._action_handler(request.payload),
                self._main_loop,
            )
            try:
                ok, data, error = await asyncio.wrap_future(future)
                response = ActionResponse(
                    correlation_id=request.correlation_id,
                    ok=ok,
                    data=_json_value(data),
                    error=error,
                )
            except Exception as error:
                response = ActionResponse(
                    correlation_id=request.correlation_id,
                    ok=False,
                    error=f"{type(error).__name__}: {error}",
                )
        await self._send(response)

    async def _send(self, message: WireMessage) -> None:
        if self._client is None:
            raise ConnectionError("NoneBot supervisor bridge is not connected")
        await self._client.send(message)


class NoneBotHost:
    def __init__(self, nonebot: Any, bridge: SupervisorBridge) -> None:
        self.nonebot = nonebot
        self.bridge = bridge
        self.events: OrderedDict[str, tuple[Any, Any]] = OrderedDict()

    def install(self, options: Mapping[str, Any]) -> None:
        config = _mapping_option(options, "config")
        self.nonebot.init(**config)
        driver = self.nonebot.get_driver()
        for spec in _string_list_option(options, "adapters"):
            driver.register_adapter(_load_symbol(spec))
        for plugin_name in _string_list_option(options, "plugins"):
            if self.nonebot.load_plugin(plugin_name) is None:
                raise RuntimeError(f"failed to load NoneBot plugin: {plugin_name}")
        for directory in _string_list_option(options, "plugin_dirs"):
            loaded = self.nonebot.load_plugins(directory)
            if not loaded:
                raise RuntimeError(f"NoneBot plugin directory loaded no plugins: {directory}")

        async def forward(bot: Any, event: Any) -> None:
            envelope = self._normalize_event(bot, event)
            self.events[envelope.reply_token or envelope.id] = (bot, event)
            self.events.move_to_end(envelope.reply_token or envelope.id)
            while len(self.events) > 2048:
                self.events.popitem(last=False)
            self.bridge.emit_event(envelope)

        adapters = importlib.import_module("nonebot.adapters")
        forward.__annotations__ = {
            "bot": adapters.Bot,
            "event": adapters.Event,
            "return": None,
        }
        nonebot_message = importlib.import_module("nonebot.message")
        nonebot_message.event_preprocessor(forward)

        async def on_startup() -> None:
            main_loop = asyncio.get_running_loop()

            def shutdown() -> None:
                main_loop.call_soon_threadsafe(driver.exit)

            self.bridge.set_handlers(
                self.execute_action,
                shutdown,
                main_loop,
            )
            self.bridge.ready()

        driver.on_startup(on_startup)

    async def execute_action(self, payload: Mapping[str, Any]) -> tuple[bool, Any, str | None]:
        envelope = ActionEnvelope.model_validate(payload)
        bot = self.nonebot.get_bot(envelope.bot_id)
        action = envelope.action
        if isinstance(action, CallApi):
            result = await bot.call_api(action.api, **action.params)
            return True, result, None
        if isinstance(action, SendMessage):
            if not action.reply_token:
                return False, None, "generic proactive NoneBot sends require CallApi"
            target = self.events.get(action.reply_token)
            if target is None:
                return False, None, "reply token is unknown or expired"
            target_bot, event = target
            result = await target_bot.send(event, action.message.plain_text)
            return True, result, None
        return False, None, f"unsupported NoneBot action: {type(action).__name__}"

    @staticmethod
    def _normalize_event(bot: Any, event: Any) -> EventEnvelope:
        reply_token = str(uuid4())
        try:
            plain_text = event.get_plaintext()
        except (AttributeError, NotImplementedError):
            plain_text = ""
        try:
            actor_id = str(event.get_user_id())
        except (AttributeError, NotImplementedError, ValueError):
            actor_id = None
        try:
            conversation_id = str(event.get_session_id())
        except (AttributeError, NotImplementedError):
            conversation_id = reply_token
        try:
            event_name = str(event.get_event_name())
        except (AttributeError, NotImplementedError):
            event_name = type(event).__name__
        adapter_name = str(bot.adapter.get_name())
        raw = _event_raw(event)
        return EventEnvelope(
            runtime_id=os.environ.get("LITEYUKI_RUNTIME_ID", "nonebot"),
            adapter=adapter_name,
            bot_id=str(bot.self_id),
            type=event_name,
            conversation=ConversationRef(id=conversation_id),
            actor=ActorRef(id=actor_id) if actor_id else None,
            message=Message(segments=(Segment(type="text", data={"text": plain_text}),)) if plain_text else None,
            reply_token=reply_token,
            raw=raw,
        )


def run() -> None:
    try:
        nonebot = importlib.import_module("nonebot")
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "NoneBot runtime is not installed; run `uv add 'liteyukibot-v7[nonebot]'`"
        ) from error
    configure_child_runtime()
    bridge = SupervisorBridge()
    options = bridge.start()
    host = NoneBotHost(nonebot, bridge)
    host.install(options)
    try:
        nonebot.run()
    finally:
        bridge.close()


def _mapping_option(options: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = options.get(key, {})
    if not isinstance(value, Mapping):
        raise ValueError(f"NoneBot runtime option {key!r} must be an object")
    return dict(value)


def _string_list_option(options: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = options.get(key, [])
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"NoneBot runtime option {key!r} must be an array of strings")
    if any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"NoneBot runtime option {key!r} must contain non-empty strings")
    return tuple(str(item) for item in value)


def _load_symbol(spec: str) -> Any:
    module_name, separator, attribute = spec.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError(f"adapter must use module:attribute syntax: {spec}")
    return getattr(importlib.import_module(module_name), attribute)


def _event_raw(event: Any) -> dict[str, Any]:
    try:
        value = event.model_dump(mode="json")
        return json_mapping(value) if isinstance(value, Mapping) else {}
    except (AttributeError, TypeError, ValueError):
        return {}


def _json_value(value: Any) -> Any:
    encoded = json.dumps(value, ensure_ascii=False, default=str, allow_nan=False)
    return json.loads(encoded)


__all__ = ["NoneBotHost", "SupervisorBridge", "run"]
