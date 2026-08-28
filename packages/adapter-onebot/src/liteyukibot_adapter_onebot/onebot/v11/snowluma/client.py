"""SnowLuma's outbound OneBot v11 WebSocket account client."""

from __future__ import annotations

import asyncio
import inspect
import json
import math
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
CLOSE_TIMEOUT_SECONDS = 10.0
RECONNECT_DELAY_SECONDS = 5.0
RECONNECT_MAX_DELAY_SECONDS = 60.0
_EVENT_QUEUE_CAPACITY = 1024
_EVENT_QUEUE_BYTE_UNIT = 4096
_EVENT_QUEUE_BYTE_BUDGET = 16 * 1024 * 1024
_EVENT_QUEUE_BYTE_SLOTS = _EVENT_QUEUE_BYTE_BUDGET // _EVENT_QUEUE_BYTE_UNIT
_MAX_PENDING_CALLS = 1024
_MAX_REPLY_ROUTES = 4096
_MAX_MESSAGE_BYTES = 1024 * 1024

EventHandler = Callable[[EventEnvelope], Awaitable[object]]


def _is_async_callable(value: object) -> bool:
    """Return whether a callback is an async function or async callable object."""

    if inspect.iscoroutinefunction(value):
        return True
    return callable(value) and inspect.iscoroutinefunction(cast(Any, value).__call__)


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
        if on_event is not None and not _is_async_callable(on_event):
            raise TypeError("on_event must be an async callable")
        self.settings = settings
        self.runtime_id = runtime_id
        self.on_event = on_event
        self.logger = logger
        self._connection: Any | None = None
        self._closing_connection: Any | None = None
        self._transport_close_task: asyncio.Task[Any] | None = None
        self._send_lock = asyncio.Lock()
        self._close_lock = asyncio.Lock()
        self._closing = False
        self._send_tasks: set[asyncio.Task[Any]] = set()
        self._task: asyncio.Task[None] | None = None
        self._connected = asyncio.Event()
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._reply_routes: dict[str, ConversationRef] = {}
        self._events: asyncio.Queue[tuple[EventEnvelope, int, int]] = asyncio.Queue(maxsize=_EVENT_QUEUE_CAPACITY)
        self._event_slots = asyncio.BoundedSemaphore(_EVENT_QUEUE_BYTE_SLOTS)
        self._queued_event_bytes = 0
        self._event_dispatch_task: asyncio.Task[None] | None = None
        self._closed = True
        self._state = "stopped"
        self._reconnect_count = 0
        self._last_error: str | None = None
        self._cleanup_error: str | None = None
        self._lingering_tasks: set[asyncio.Task[Any]] = set()

    @property
    def self_id(self) -> str:
        return self.settings.self_id

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def status(self) -> dict[str, object]:
        """Return JSON-safe transport health without exposing credentials."""

        return {
            "state": self._state,
            "connected": self.connected,
            "pending_calls": self.pending_count,
            "queued_events": self._events.qsize(),
            "queued_event_bytes": self._queued_event_bytes,
            "reconnect_count": self._reconnect_count,
            "last_error": self._last_error,
            "cleanup_error": self._cleanup_error,
            "background_tasks": len(self._lingering_tasks | self._send_tasks)
            + sum(task is not None and not task.done() for task in (self._task, self._event_dispatch_task)),
        }

    @property
    def reply_routes(self) -> Mapping[str, ConversationRef]:
        return self._reply_routes

    async def start(self) -> None:
        """Start the account's background connection and reconnect loop."""

        if self._task is not None and not self._task.done():
            return
        if self._closing:
            raise RuntimeError("SnowLuma account is closing")
        if self._lingering_tasks or self._closing_connection is not None or self._cleanup_error is not None:
            raise RuntimeError("SnowLuma account still has cleanup from a previous close")
        self._closed = False
        self._closing = False
        self._state = "connecting"
        self._last_error = None
        self._cleanup_error = None
        self._connected.clear()
        self._events = asyncio.Queue(maxsize=_EVENT_QUEUE_CAPACITY)
        self._event_slots = asyncio.BoundedSemaphore(_EVENT_QUEUE_BYTE_SLOTS)
        self._queued_event_bytes = 0
        self._event_dispatch_task = asyncio.create_task(
            self._dispatch_events(), name=f"onebot-snowluma-events-{self.self_id}"
        )
        self._task = asyncio.create_task(self._run(), name=f"onebot-snowluma-{self.self_id}")
        await asyncio.sleep(0)

    async def close(self, *, timeout_seconds: float = CLOSE_TIMEOUT_SECONDS) -> None:
        """Stop the account and fail all in-flight calls."""

        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        try:
            await asyncio.wait_for(self._close_lock.acquire(), timeout=_remaining_seconds(deadline))
        except TimeoutError as error:
            raise TimeoutError("SnowLuma account close is already in progress") from error
        try:
            await self._close_locked(deadline)
        finally:
            self._close_lock.release()

    async def _close_locked(self, deadline: float) -> None:
        """Close one account while serializing state transitions and honoring one time budget."""

        if (
            self._closed
            and self._task is None
            and self._event_dispatch_task is None
            and self._connection is None
            and self._closing_connection is None
            and not self._send_tasks
            and not self._lingering_tasks
            and self._cleanup_error is None
        ):
            self._drain_events()
            self._state = "stopped"
            self._clear_connection_state(SnowLumaConnectionError("SnowLuma account is closed"))
            return

        self._closing = True
        self._state = "stopping"
        if self._connection is not None or self._closing_connection is not None:
            self._cleanup_error = None
        connection: Any | None = None
        send_gate_timed_out = False
        try:
            try:
                await asyncio.wait_for(self._send_lock.acquire(), timeout=_remaining_seconds(deadline))
            except TimeoutError:
                send_gate_timed_out = True
                self._closed = True
                connection, self._connection = self._connection or self._closing_connection, None
            else:
                try:
                    self._closed = True
                    connection, self._connection = self._connection or self._closing_connection, None
                finally:
                    self._send_lock.release()

            task, self._task = self._task, None
            event_task, self._event_dispatch_task = self._event_dispatch_task, None
            lifecycle_tasks = tuple(
                task for task in (task, event_task) if task is not None and not task.done()
            )
            send_tasks = tuple(self._send_tasks)
            pending_tasks = await self._cancel_tasks((*lifecycle_tasks, *send_tasks), deadline=deadline)
            self._drain_events()
            pending = len(pending_tasks)
            if connection is not None:
                self._closing_connection = connection
                if send_gate_timed_out:
                    self._defer_connection_close(connection)
                else:
                    pending += await self._close_connection(connection, timeout_seconds=_remaining_seconds(deadline))
            if pending:
                self._log("error", "account {} close left {} task(s) running", self.self_id, pending)
            self._clear_connection_state(SnowLumaConnectionError("SnowLuma account is closed"))
            if self._cleanup_error is not None:
                self._state = "failed"
            else:
                self._state = "cleanup_pending" if pending or self._closing_connection is not None else "stopped"
        except asyncio.CancelledError:
            self._state = "cleanup_pending"
            raise
        except BaseException as error:
            self._record_cleanup_error(error)
            raise
        finally:
            self._closing = False
            self._maybe_mark_stopped()

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

        if (
            not api
            or not api[0].isascii()
            or not api[0].isalpha()
                or any(not (character.isascii() and (character.isalnum() or character == "_")) for character in api)
        ):
            raise OneBotV11Error("OneBot API names must contain only ASCII letters, digits, and underscores")
        correlation_id = str(uuid4())
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        request = {"action": api, "params": json_value(params), "echo": correlation_id}
        current = asyncio.current_task()
        if current is not None:
            self._send_tasks.add(current)
        try:
            async with asyncio.timeout(ACTION_TIMEOUT_SECONDS):
                async with self._send_lock:
                    if self._closed or self._closing:
                        raise SnowLumaConnectionError("SnowLuma account is closed")
                    connection = self._connection
                    if connection is None:
                        raise SnowLumaConnectionError("SnowLuma WebSocket is not connected")
                    if len(self._pending) >= _MAX_PENDING_CALLS:
                        raise OneBotV11Error("too many pending OneBot API calls")
                    self._pending[correlation_id] = future
                    wire = json.dumps(request, ensure_ascii=False, separators=(",", ":"))
                    if len(wire.encode("utf-8")) > _MAX_MESSAGE_BYTES:
                        raise OneBotV11Error("OneBot API payload exceeds the maximum message size")
                    await connection.send(wire)
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
            if current is not None:
                self._send_tasks.discard(current)
        if response.get("status") != "ok" or response.get("retcode") != 0:
            retcode = response.get("retcode")
            safe_retcode = (
                retcode if isinstance(retcode, int) and not isinstance(retcode, bool) else type(retcode).__name__
            )
            raise OneBotV11Error(f"OneBot API {api!r} failed with retcode {safe_retcode!r}")
        return cast(JsonValue, json_value(response.get("data")))

    async def _run(self) -> None:
        headers = {
            "User-Agent": "OneBot/11",
            "X-Self-ID": self.settings.self_id,
            "X-Client-Role": "Universal",
        }
        if self.settings.access_token:
            headers["Authorization"] = f"Bearer {self.settings.access_token}"
        reconnect_delay = RECONNECT_DELAY_SECONDS
        while not self._closed:
            disconnect_error: BaseException | None = None
            try:
                async with websocket_client.connect(
                    self.settings.ws_url,
                    additional_headers=headers,
                    max_size=_MAX_MESSAGE_BYTES,
                    open_timeout=CONNECT_TIMEOUT_SECONDS,
                ) as connection:
                    async with self._send_lock:
                        if self._closed or self._closing:
                            return
                        self._connection = connection
                    self._connected.set()
                    self._state = "connected"
                    reconnect_delay = RECONNECT_DELAY_SECONDS
                    await self._consume(connection)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                disconnect_error = SnowLumaConnectionError("SnowLuma WebSocket disconnected")
                self._last_error = type(error).__name__
                self._log("warning", "account {} transport failed: {}", self.self_id, type(error).__name__)
            finally:
                self._connected.clear()
                self._connection = None
                final_error = disconnect_error or SnowLumaConnectionError("SnowLuma WebSocket closed")
                if not self._closed and disconnect_error is None:
                    self._last_error = type(final_error).__name__
                self._clear_connection_state(final_error)
                if not self._closed:
                    self._reconnect_count += 1
                    self._state = "backoff"
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, RECONNECT_MAX_DELAY_SECONDS)

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
                self._log(
                    "warning",
                    "account {} discarded an invalid event: {}",
                    self.self_id,
                    type(error).__name__,
                )
                continue
            if event is None or self.on_event is None:
                continue
            if event.reply_token is not None:
                self._remember_reply_route(event.reply_token, event.conversation)
            reserved = await self._reserve_event(event)
            if reserved is None:
                self._log("warning", "account {} dropped an event over the queue byte budget", self.self_id)
                continue
            event_size, event_slots = reserved
            try:
                await self._events.put((event, event_size, event_slots))
            except BaseException:
                self._release_event(event_size, event_slots)
                raise

    async def _reserve_event(self, event: EventEnvelope) -> tuple[int, int] | None:
        """Reserve weighted queue capacity before retaining one normalized event."""

        event_size = len(event.model_dump_json().encode("utf-8"))
        event_slots = max(1, (event_size + _EVENT_QUEUE_BYTE_UNIT - 1) // _EVENT_QUEUE_BYTE_UNIT)
        if event_slots > _EVENT_QUEUE_BYTE_SLOTS:
            return None
        acquired = 0
        try:
            while acquired < event_slots:
                if self._closed:
                    self._release_event_slots(acquired)
                    return None
                await self._event_slots.acquire()
                acquired += 1
            if self._closed:
                self._release_event_slots(acquired)
                return None
        except BaseException:
            self._release_event_slots(acquired)
            raise
        self._queued_event_bytes += event_size
        return event_size, event_slots

    def _release_event(self, event_size: int, event_slots: int) -> None:
        self._queued_event_bytes = max(0, self._queued_event_bytes - event_size)
        self._release_event_slots(event_slots)

    def _release_event_slots(self, event_slots: int) -> None:
        for _ in range(event_slots):
            self._event_slots.release()

    def _drain_events(self) -> None:
        """Drop queued events during close and return their weighted capacity."""

        while True:
            try:
                _event, event_size, event_slots = self._events.get_nowait()
            except asyncio.QueueEmpty:
                return
            self._release_event(event_size, event_slots)
            self._events.task_done()

    def _remember_reply_route(self, token: str, conversation: ConversationRef) -> None:
        self._reply_routes[token] = conversation
        if len(self._reply_routes) > _MAX_REPLY_ROUTES:
            self._reply_routes.pop(next(iter(self._reply_routes)))

    async def _dispatch_events(self) -> None:
        while not self._closed:
            event, event_size, event_slots = await self._events.get()
            self._release_event(event_size, event_slots)
            try:
                if self.on_event is not None:
                    await self.on_event(event)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self._log("error", "account {} event delivery failed: {}", self.self_id, type(error).__name__)
            finally:
                self._events.task_done()

    def _clear_connection_state(self, error: BaseException) -> None:
        self._reply_routes.clear()
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)
        self._pending.clear()

    async def _close_connection(self, connection: Any, *, timeout_seconds: float) -> int:
        """Close a WebSocket gracefully before cancelling an uncooperative close task."""

        existing = self._transport_close_task
        if existing is not None:
            if not existing.done():
                return 1
            self._forget_close_task(existing, self._closing_connection)
            if self._cleanup_error is not None:
                raise SnowLumaConnectionError("SnowLuma WebSocket close failed")
            if self._closing_connection is None:
                return 0
        try:
            close_task = asyncio.create_task(connection.close(), name=f"onebot-snowluma-close-{self.self_id}")
        except Exception as error:
            self._record_cleanup_error(error)
            raise SnowLumaConnectionError("SnowLuma WebSocket close failed") from error
        self._transport_close_task = close_task
        try:
            done, pending = await asyncio.wait((close_task,), timeout=timeout_seconds)
        except BaseException:
            if not close_task.done():
                self._track_close_task(close_task, connection)
            else:
                self._forget_close_task(close_task, connection)
            raise
        if done:
            try:
                close_task.result()
            except BaseException as error:
                self._forget_close_task(close_task, connection)
                raise SnowLumaConnectionError("SnowLuma WebSocket close failed") from error
            self._forget_close_task(close_task, connection)
            return 0
        close_task.cancel()
        self._track_close_task(close_task, connection)
        return len(pending)

    def _defer_connection_close(self, connection: Any) -> None:
        """Close a connection only after a timed-out send gate is released."""

        task = asyncio.create_task(
            self._close_after_send_gate(connection),
            name=f"onebot-snowluma-deferred-close-{self.self_id}",
        )
        self._lingering_tasks.add(task)
        task.add_done_callback(self._forget_task)

    async def _close_after_send_gate(self, connection: Any) -> None:
        """Avoid racing a transport close with an uncooperative in-flight send."""

        await self._send_lock.acquire()
        self._send_lock.release()
        await self._close_connection(connection, timeout_seconds=CLOSE_TIMEOUT_SECONDS)

    async def _cancel_tasks(
        self,
        tasks: tuple[asyncio.Task[Any], ...],
        *,
        deadline: float,
    ) -> tuple[asyncio.Task[Any], ...]:
        """Cancel tasks and retain any that ignore cancellation for later observation."""

        for task in tasks:
            task.cancel()
        if not tasks:
            return ()
        done, pending = await asyncio.wait(tasks, timeout=_remaining_seconds(deadline))
        for task in done:
            self._forget_task(task)
        for task in pending:
            self._lingering_tasks.add(task)
            task.add_done_callback(self._forget_task)
        return tuple(pending)

    def _forget_task(self, task: asyncio.Task[Any]) -> None:
        """Remove a completed lifecycle task and consume its exception."""

        self._lingering_tasks.discard(task)
        if not task.cancelled():
            try:
                error = task.exception()
            except BaseException:
                error = None
            if error is not None:
                self._record_cleanup_error(error)
        self._maybe_mark_stopped()

    def _track_close_task(self, task: asyncio.Task[Any], connection: Any) -> None:
        self._transport_close_task = task
        self._lingering_tasks.add(task)
        task.add_done_callback(lambda completed: self._forget_close_task(completed, connection))

    def _forget_close_task(self, task: asyncio.Task[Any], connection: Any | None) -> None:
        """Observe a deferred transport close and preserve failures for service cleanup."""

        self._lingering_tasks.discard(task)
        if self._transport_close_task is task:
            self._transport_close_task = None
        if task.cancelled():
            self._maybe_mark_stopped()
            return
        try:
            error = task.exception()
        except BaseException:
            error = None
        if error is not None:
            self._record_cleanup_error(error)
        elif self._closing_connection is connection:
            self._closing_connection = None
        self._maybe_mark_stopped()

    def _record_cleanup_error(self, error: BaseException) -> None:
        if self._cleanup_error is None:
            self._cleanup_error = type(error).__name__
            self._last_error = self._cleanup_error
        self._state = "failed"

    def _maybe_mark_stopped(self) -> None:
        if (
            self._closed
            and not self._closing
            and self._connection is None
            and self._closing_connection is None
            and not self._send_tasks
            and not self._lingering_tasks
            and self._cleanup_error is None
        ):
            self._state = "stopped"

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


def _remaining_seconds(deadline: float) -> float:
    """Return the non-negative remainder of a monotonic shutdown deadline."""

    return max(0.0, deadline - asyncio.get_running_loop().time())


def _positive_integer_id(value: str) -> int:
    if not value.isdecimal() or (parsed := int(value)) <= 0:
        raise OneBotV11Error("OneBot v11 conversation IDs must be positive integers")
    return parsed


__all__ = [
    "SnowLumaClient",
    "SnowLumaConnectionError",
]
