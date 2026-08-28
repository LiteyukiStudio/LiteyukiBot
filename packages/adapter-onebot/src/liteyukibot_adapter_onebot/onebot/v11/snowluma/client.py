"""SnowLuma's outbound OneBot v11 WebSocket account client."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, cast
from uuid import uuid4

import websockets.asyncio.client as websocket_client
from liteyukibot_kernel import ConversationRef, EventEnvelope, SendMessage, json_value
from liteyukibot_kernel.events import JsonValue

from ..core import ONEBOT_V11_ADAPTER, OneBotV11Error, normalize_event, to_onebot_message
from .settings import SnowLumaAccountSettings

CONNECT_TIMEOUT_SECONDS = 30.0
ACTION_TIMEOUT_SECONDS = 30.0
RECONNECT_DELAY_SECONDS = 5.0
_EVENT_QUEUE_CAPACITY = 1024
_MAX_REPLY_ROUTES = 4096
_MAX_MESSAGE_BYTES = 1024 * 1024

EventHandler = Callable[[EventEnvelope], Awaitable[object] | object]


class SnowLumaConnectionError(OneBotV11Error):
    """The SnowLuma account is not currently connected."""


class SnowLumaClient:
    """Maintain one reconnecting SnowLuma WebSocket and its pending calls."""

    def __init__(
        self,
        settings: SnowLumaAccountSettings,
        *,
        runtime_id: str = "onebot",
        on_event: EventHandler | None = None,
        logger: Any | None = None,
    ) -> None:
        self.settings = settings
        self.runtime_id = runtime_id
        self.on_event = on_event
        self.logger = logger
        self._connection: Any | None = None
        self._task: asyncio.Task[None] | None = None
        self._connected = asyncio.Event()
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._reply_routes: dict[str, ConversationRef] = {}
        self._events: asyncio.Queue[EventEnvelope] = asyncio.Queue(maxsize=_EVENT_QUEUE_CAPACITY)
        self._event_dispatch_task: asyncio.Task[None] | None = None
        self._closed = True

    @property
    def self_id(self) -> str:
        return self.settings.self_id

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def reply_routes(self) -> Mapping[str, ConversationRef]:
        return self._reply_routes

    async def start(self) -> None:
        """Start the account's background connection and reconnect loop."""

        if self._task is not None and not self._task.done():
            return
        self._closed = False
        self._connected.clear()
        self._events = asyncio.Queue(maxsize=_EVENT_QUEUE_CAPACITY)
        self._event_dispatch_task = asyncio.create_task(
            self._dispatch_events(), name=f"onebot-snowluma-events-{self.self_id}"
        )
        self._task = asyncio.create_task(self._run(), name=f"onebot-snowluma-{self.self_id}")
        await asyncio.sleep(0)

    async def close(self) -> None:
        """Stop the account and fail all in-flight calls."""

        if self._closed and self._task is None:
            self._clear_connection_state(SnowLumaConnectionError("SnowLuma account is closed"))
            return
        self._closed = True
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        event_task, self._event_dispatch_task = self._event_dispatch_task, None
        if event_task is not None:
            event_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await event_task
        connection, self._connection = self._connection, None
        if connection is not None:
            with contextlib.suppress(Exception):
                await connection.close()
        self._clear_connection_state(SnowLumaConnectionError("SnowLuma account is closed"))

    async def send_message(self, action: SendMessage) -> JsonValue:
        """Send one source-bound kernel message through this account."""

        conversation = action.conversation
        if conversation is None:
            if not action.reply_token:
                raise OneBotV11Error("message.send requires a conversation or reply_token")
            try:
                conversation = self._reply_routes[action.reply_token]
            except KeyError as error:
                raise OneBotV11Error("reply_token is unknown or expired") from error

        target = _positive_integer_id(conversation.id)
        message = to_onebot_message(action.message)
        if conversation.type == "private":
            response = await self.call_api("send_private_msg", {"user_id": target, "message": message})
        elif conversation.type == "group":
            response = await self.call_api("send_group_msg", {"group_id": target, "message": message})
        else:
            raise OneBotV11Error(f"OneBot v11 does not support {conversation.type!r} conversations")
        return response

    async def call_api(self, api: str, params: Mapping[str, Any]) -> JsonValue:
        """Call one OneBot v11 API and return its JSON ``data`` field."""

        if self._connection is None:
            raise SnowLumaConnectionError("SnowLuma WebSocket is not connected")
        if (
            not api
            or not api[0].isascii()
            or not api[0].isalpha()
            or any(not (character.isascii() and (character.isalnum() or character == "_")) for character in api)
        ):
            raise OneBotV11Error("OneBot API names must contain only ASCII letters, digits, and underscores")
        correlation_id = str(uuid4())
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[correlation_id] = future
        request = {"action": api, "params": json_value(params), "echo": correlation_id}
        try:
            async with asyncio.timeout(ACTION_TIMEOUT_SECONDS):
                await self._connection.send(json.dumps(request, ensure_ascii=False, separators=(",", ":")))
                response = await asyncio.shield(future)
        except TimeoutError as error:
            raise OneBotV11Error(f"OneBot API {api!r} timed out") from error
        except asyncio.CancelledError:
            raise
        except SnowLumaConnectionError:
            raise
        except OneBotV11Error:
            raise
        except Exception as error:
            raise SnowLumaConnectionError(f"OneBot API {api!r} connection failed") from error
        finally:
            self._pending.pop(correlation_id, None)
        if response.get("status") != "ok" or response.get("retcode") != 0:
            detail = response.get("wording") or response.get("message") or response.get("retcode")
            raise OneBotV11Error(f"OneBot API {api!r} failed: {detail!r}")
        return cast(JsonValue, json_value(response.get("data")))

    async def _run(self) -> None:
        headers = {
            "User-Agent": "OneBot/11",
            "X-Self-ID": self.settings.self_id,
            "X-Client-Role": "Universal",
        }
        if self.settings.access_token:
            headers["Authorization"] = f"Bearer {self.settings.access_token}"
        while not self._closed:
            disconnect_error: BaseException | None = None
            try:
                async with websocket_client.connect(
                    self.settings.ws_url,
                    additional_headers=headers,
                    max_size=_MAX_MESSAGE_BYTES,
                    open_timeout=CONNECT_TIMEOUT_SECONDS,
                ) as connection:
                    self._connection = connection
                    self._connected.set()
                    await self._consume(connection)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                disconnect_error = SnowLumaConnectionError(f"SnowLuma WebSocket disconnected: {error}")
                self._log("warning", "account {} transport failed: {}", self.self_id, error)
            finally:
                self._connected.clear()
                self._connection = None
                self._clear_connection_state(disconnect_error or SnowLumaConnectionError("SnowLuma WebSocket closed"))
            if not self._closed:
                await asyncio.sleep(RECONNECT_DELAY_SECONDS)

    async def _consume(self, connection: Any) -> None:
        async for raw in connection:
            if isinstance(raw, bytes):
                try:
                    raw = raw.decode("utf-8")
                except UnicodeDecodeError:
                    continue
            if not isinstance(raw, str):
                continue
            try:
                value = json.loads(raw)
            except TypeError, ValueError:
                continue
            if not isinstance(value, Mapping):
                continue
            payload = dict(value)
            echo = payload.get("echo")
            if isinstance(echo, str) and (future := self._pending.get(echo)) is not None:
                if not future.done():
                    future.set_result(payload)
                continue
            try:
                event = normalize_event(
                    payload,
                    self_id=self.settings.self_id,
                    runtime_id=self.runtime_id,
                    adapter=ONEBOT_V11_ADAPTER,
                )
            except OneBotV11Error as error:
                self._log("warning", "account {} discarded an invalid event: {}", self.self_id, error)
                continue
            if event is None or self.on_event is None:
                continue
            if event.reply_token is not None:
                self._remember_reply_route(event.reply_token, event.conversation)
            await self._events.put(event)

    def _remember_reply_route(self, token: str, conversation: ConversationRef) -> None:
        self._reply_routes[token] = conversation
        if len(self._reply_routes) > _MAX_REPLY_ROUTES:
            self._reply_routes.pop(next(iter(self._reply_routes)))

    async def _dispatch_events(self) -> None:
        while not self._closed:
            event = await self._events.get()
            try:
                if self.on_event is not None:
                    result = self.on_event(event)
                    if inspect.isawaitable(result):
                        await result
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self._log("error", "account {} event delivery failed: {}", self.self_id, error)
            finally:
                self._events.task_done()

    def _clear_connection_state(self, error: BaseException) -> None:
        self._reply_routes.clear()
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)
        self._pending.clear()

    def _log(self, level: str, template: str, *args: object) -> None:
        logger = self.logger
        if logger is None:
            return
        try:
            method = getattr(logger, level, None)
            if callable(method):
                method(template, *args)
        except Exception:
            return


def _positive_integer_id(value: str) -> int:
    if not value.isdecimal() or (parsed := int(value)) <= 0:
        raise OneBotV11Error("OneBot v11 conversation IDs must be positive integers")
    return parsed


__all__ = [
    "SnowLumaClient",
    "SnowLumaConnectionError",
]
