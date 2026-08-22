"""Bounded OneBot forward and reverse WebSocket transport."""

from __future__ import annotations

import asyncio
import hmac
import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Any
from uuid import uuid4

from websockets.asyncio.client import connect
from websockets.asyncio.server import Server, ServerConnection, serve

JsonHandler = Callable[[Mapping[str, Any]], Awaitable[None]]
FailureHandler = Callable[[BaseException], Awaitable[None]]

_MAX_MESSAGE_BYTES = 1024 * 1024
_CONNECT_TIMEOUT = 10
_REQUEST_TIMEOUT = 15
_RETRY_DELAYS = (1, 2, 4)


class OneBotWebSocketError(ValueError):
    """The configured OneBot WebSocket transport cannot complete an operation."""


class OneBotWebSocketTransport:
    """Own exactly one active OneBot WebSocket and correlated API requests."""

    def __init__(
        self,
        *,
        mode: str,
        url: str | None,
        host: str | None,
        port: int | None,
        path: str,
        access_token: str | None,
        handle_event: JsonHandler,
        on_failure: FailureHandler | None = None,
    ) -> None:
        """Initialize the one bot web socket transport.

        Args:
            mode: The mode value used by the operation.
            url: The url value used by the operation.
            host: The host value used by the operation.
            port: The port value used by the operation.
            path: Filesystem or logical resource path.
            access_token: The access token value used by the operation.
            handle_event: The handle event value used by the operation.
            on_failure: The on failure value used by the operation.

        Returns:
            None.
        """
        if mode not in {"forward_websocket", "reverse_websocket"}:
            raise OneBotWebSocketError("WebSocket mode must be forward_websocket or reverse_websocket")
        self.mode = mode
        self.url = url
        self.host = host
        self.port = port
        self.path = path
        self.access_token = access_token
        self.handle_event = handle_event
        self.on_failure = on_failure
        self._connection: Any | None = None
        self._server: Server | None = None
        self._task: asyncio.Task[None] | None = None
        self._connected = asyncio.Event()
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._closed = False
        self._failure_notified = False

    async def start(self) -> None:
        """Start the one bot web socket transport.

        Returns:
            None.
        """
        self._closed = False
        self._failure_notified = False
        self._connected.clear()
        if self.mode == "forward_websocket":
            if self.url is None:
                raise OneBotWebSocketError("forward_websocket requires config.ws_url")
            self._task = asyncio.create_task(self._forward_loop(), name="onebot-forward-websocket")
            ready = asyncio.create_task(self._connected.wait(), name="onebot-forward-websocket-ready")
            task = self._task
            done, pending = await asyncio.wait(
                {ready, task}, timeout=_CONNECT_TIMEOUT, return_when=asyncio.FIRST_COMPLETED
            )
            if ready in pending:
                ready.cancel()
                await asyncio.gather(ready, return_exceptions=True)
            if ready in done and ready.result():
                return
            failure = task.exception() if task in done and not task.cancelled() else None
            await self.close()
            if isinstance(failure, OneBotWebSocketError):
                raise failure
            raise OneBotWebSocketError("OneBot forward WebSocket did not connect")
        if self.host is None or self.port is None:
            raise OneBotWebSocketError("reverse_websocket requires config.ws_host and config.ws_port")
        self._server = await serve(self._accept, self.host, self.port, max_size=_MAX_MESSAGE_BYTES)

    async def execute(self, api: str, params: Mapping[str, Any]) -> dict[str, Any]:
        """Execute one request through the one bot web socket transport.

        Args:
            api: The api value used by the operation.
            params: The params value used by the operation.

        Returns:
            The `dict[str, Any]` result produced by the operation.
        """
        connection = self._connection
        if connection is None:
            raise OneBotWebSocketError("OneBot WebSocket is not connected")
        correlation_id = str(uuid4())
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[correlation_id] = future
        try:
            await connection.send(json.dumps({"action": api, "params": params, "echo": correlation_id}))
            return await asyncio.wait_for(future, timeout=_REQUEST_TIMEOUT)
        except TimeoutError as error:
            raise OneBotWebSocketError(f"OneBot WebSocket API {api!r} timed out") from error
        finally:
            self._pending.pop(correlation_id, None)

    async def close(self) -> None:
        """Close the one bot web socket transport and release its owned resources.

        Returns:
            None.
        """
        self._closed = True
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        server, self._server = self._server, None
        if server is not None:
            server.close()
            await server.wait_closed()
        connection, self._connection = self._connection, None
        if connection is not None:
            await connection.close()
        self._connected.clear()
        for future in self._pending.values():
            if not future.done():
                future.set_exception(OneBotWebSocketError("OneBot WebSocket closed"))
        self._pending.clear()

    async def _forward_loop(self) -> None:
        """Implement the forward loop operation for the one bot web socket transport.

        Returns:
            None.

        Notes:
            Internal implementation detail for `OneBotWebSocketTransport._forward_loop`. It delegates to
            `connect`, `_run_connection`, `clear`, `on_failure` while keeping intermediate state local to
            the owning operation.
        """
        assert self.url is not None
        headers = {"Authorization": f"Bearer {self.access_token}"} if self.access_token else None
        retry_index = 0
        while not self._closed:
            try:
                async with connect(self.url, additional_headers=headers, max_size=_MAX_MESSAGE_BYTES) as connection:
                    await self._run_connection(connection)
                    if not self._closed:
                        raise OneBotWebSocketError("OneBot forward WebSocket disconnected")
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self._connected.clear()
                if not self._closed:
                    if retry_index >= len(_RETRY_DELAYS):
                        failure = OneBotWebSocketError("OneBot forward WebSocket retries exhausted")
                        if self.on_failure is not None and not self._failure_notified:
                            self._failure_notified = True
                            await self.on_failure(failure)
                        raise failure from error
                    await asyncio.sleep(_RETRY_DELAYS[retry_index])
                    retry_index += 1

    async def _accept(self, connection: ServerConnection) -> None:
        """Accept the one bot web socket transport operation.

        Args:
            connection: The connection value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `OneBotWebSocketTransport._accept`. It delegates to `close`,
            `get`, `compare_digest`, `_run_connection` while keeping intermediate state local to the owning
            operation.
        """
        request = connection.request
        if request is None or (self.path and request.path != self.path):
            await connection.close(code=1008, reason="unexpected path")
            return
        if self.access_token is not None:
            authorization = request.headers.get("Authorization")
            expected = f"Bearer {self.access_token}"
            if authorization is None or not hmac.compare_digest(authorization, expected):
                await connection.close(code=1008, reason="unauthorized")
                return
        await self._run_connection(connection)

    async def _run_connection(self, connection: Any) -> None:
        """Run connection.

        Args:
            connection: The connection value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `OneBotWebSocketTransport._run_connection`. It delegates to
            `close`, `loads`, `get`, `done` while keeping intermediate state local to the owning operation.
        """
        if self._connection is not None:
            await connection.close(code=1013, reason="connection already active")
            return
        self._connection = connection
        self._connected.set()
        try:
            async for raw in connection:
                if not isinstance(raw, str):
                    continue
                value = json.loads(raw)
                if not isinstance(value, Mapping):
                    continue
                payload = dict(value)
                echo = payload.get("echo")
                if isinstance(echo, str) and echo in self._pending:
                    future = self._pending[echo]
                    if not future.done():
                        future.set_result(payload)
                    continue
                await self.handle_event(payload)
        finally:
            if self._connection is connection:
                self._connection = None
                self._connected.clear()


__all__ = ["OneBotWebSocketError", "OneBotWebSocketTransport"]
