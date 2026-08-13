"""NoneBot2 host runtime and protocol-neutral event bridge."""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import signal
import threading
from collections import OrderedDict
from collections.abc import Callable, Coroutine, Mapping, Sequence
from concurrent.futures import Future
from pathlib import Path, PurePath
from typing import Any

from liteyukibot.events import ActionEnvelope, CallApi, EditMessage, EventEnvelope, SendMessage
from liteyukibot.logging import configure_runtime_child_logging, get_logger
from liteyukibot.runtime import RuntimeClient
from liteyukibot.runtime.protocol import (
    ActionRequest,
    ActionResponse,
    EventMessage,
    Shutdown,
    WireMessage,
)

from .contracts import (
    AdapterContractError,
    adapter_id,
    json_value,
    normalize_event,
    send_proactive,
    to_native_message,
)

logger = get_logger(component="nonebot", runtime=os.environ.get("LITEYUKI_RUNTIME_ID"))
type ActionHandler = Callable[
    [Mapping[str, Any]],
    Coroutine[Any, Any, tuple[bool, Any, str | None]],
]


def _stop_driver(driver: Any) -> None:
    exit_driver = getattr(driver, "exit", None)
    if callable(exit_driver):
        exit_driver()
        return
    signal.raise_signal(signal.SIGINT)


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
                    data=json_value(data),
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
        managed = _managed_plugin_options()
        configured_plugins = _string_list_option(options, "plugins")
        configured_directories = _string_list_option(options, "plugin_dirs")
        if managed is not None and (configured_plugins or configured_directories):
            raise RuntimeError("managed NoneBot generation cannot combine plugins or plugin_dirs runtime options")
        plugins, directories = managed if managed is not None else (configured_plugins, configured_directories)
        self.nonebot.init(**config)
        driver = self.nonebot.get_driver()
        for spec in _string_list_option(options, "adapters"):
            driver.register_adapter(_load_symbol(spec))
        for plugin_name in plugins:
            if self.nonebot.load_plugin(plugin_name) is None:
                raise RuntimeError(f"failed to load NoneBot plugin: {plugin_name}")
        for directory in directories:
            loaded = self.nonebot.load_plugins(directory)
            if not loaded:
                raise RuntimeError(f"NoneBot plugin directory loaded no plugins: {directory}")

        async def forward(bot: Any, event: Any) -> None:
            envelope = self._normalize_event(bot, event)
            if envelope.reply_token is not None:
                self.events[envelope.reply_token] = (bot, event)
                self.events.move_to_end(envelope.reply_token)
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
                main_loop.call_soon_threadsafe(_stop_driver, driver)

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
        selected_adapter = adapter_id(str(bot.adapter.get_name()))
        if isinstance(action, CallApi):
            params = json_value(action.params)
            if not isinstance(params, dict):
                return False, None, "CallApi params must serialize to an object"
            result = await bot.call_api(action.api, **params)
            return True, json_value(result), None
        if isinstance(action, SendMessage):
            try:
                message = to_native_message(selected_adapter, action.message)
                if action.reply_token:
                    target = self.events.get(action.reply_token)
                    if target is None:
                        return False, None, "reply token is unknown or expired"
                    target_bot, event = target
                    if str(target_bot.self_id) != envelope.bot_id:
                        return False, None, "reply token belongs to a different bot"
                    target_adapter = adapter_id(str(target_bot.adapter.get_name()))
                    if target_adapter != selected_adapter:
                        return False, None, "reply token belongs to a different adapter"
                    result = await target_bot.send(event, message)
                else:
                    result = await send_proactive(bot, selected_adapter, action, message)
            except AdapterContractError as error:
                return False, None, str(error)
            return True, json_value(result), None
        if isinstance(action, EditMessage):
            if selected_adapter != "satori":
                return False, None, f"adapter {selected_adapter!r} does not support edit_message"
            try:
                message = to_native_message(selected_adapter, action.message)
                edit_params: dict[str, Any] = {"message_id": action.message_id, "content": message}
                if action.conversation is not None:
                    edit_params["channel_id"] = action.conversation.id
                result = await bot.call_api("message_update", **edit_params)
            except AdapterContractError as error:
                return False, None, str(error)
            return True, json_value(result), None
        return False, None, f"unsupported NoneBot action: {type(action).__name__}"

    @staticmethod
    def _normalize_event(bot: Any, event: Any) -> EventEnvelope:
        return normalize_event(bot, event)


def run() -> None:
    try:
        nonebot = importlib.import_module("nonebot")
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "NoneBot runtime is not installed; install `liteyukibot-v7-runtime-nonebot`"
        ) from error
    configure_runtime_child_logging()
    logger.info("starting NoneBot runtime host")
    bridge = SupervisorBridge()
    options = bridge.start()
    host = NoneBotHost(nonebot, bridge)
    host.install(options)
    logger.info("NoneBot runtime host is ready")
    try:
        nonebot.run()
    finally:
        bridge.close()
        logger.info("NoneBot runtime host stopped")


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


def _managed_plugin_options() -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    raw_generation = os.environ.get("LITEYUKI_RUNTIME_GENERATION_DIR")
    if raw_generation is None:
        return None
    generation = Path(raw_generation).resolve(strict=True)
    plan_path = generation / "load-plan.json"
    try:
        document = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError("managed NoneBot generation has an invalid load plan") from error
    if not isinstance(document, Mapping):
        raise RuntimeError("managed NoneBot generation load plan must be an object")
    plugins = _string_list_option(document, "plugins")
    raw_directories = _string_list_option(document, "directories")
    payload = (generation / "payload").resolve()
    directories: list[str] = []
    for raw_directory in raw_directories:
        relative = PurePath(raw_directory)
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise RuntimeError("managed NoneBot generation directory must be a safe payload-relative path")
        directory = (payload / relative).resolve()
        try:
            directory.relative_to(payload)
        except ValueError as error:
            raise RuntimeError("managed NoneBot generation directory escapes its payload") from error
        if not directory.is_dir():
            raise RuntimeError(f"managed NoneBot generation plugin directory is absent: {raw_directory}")
        directories.append(str(directory))
    return plugins, tuple(directories)


def _load_symbol(spec: str) -> Any:
    module_name, separator, attribute = spec.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError(f"adapter must use module:attribute syntax: {spec}")
    return getattr(importlib.import_module(module_name), attribute)


__all__ = ["NoneBotHost", "SupervisorBridge", "run"]
