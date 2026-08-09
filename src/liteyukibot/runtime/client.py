"""Reusable versioned client for supervised child runtimes."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Mapping, Sequence
from typing import Any

from ..exceptions import RuntimeProtocolError
from .protocol import (
    PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    ActionRequest,
    ActionResponse,
    ConfigMessage,
    Heartbeat,
    Hello,
    JsonValue,
    ProtocolVersion,
    Ready,
    Welcome,
    WireMessage,
    json_mapping,
    read_message,
    write_message,
)


class RuntimeClient:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        runtime_id: str,
        kind: str,
        token: str,
        protocol_version: ProtocolVersion = PROTOCOL_VERSION,
    ) -> None:
        if not host or not runtime_id or not kind or not token:
            raise ValueError("runtime connection identity must not be empty")
        if not 1 <= port <= 65535:
            raise ValueError("runtime port must be between 1 and 65535")
        if protocol_version not in SUPPORTED_PROTOCOL_VERSIONS:
            raise ValueError(f"unsupported runtime protocol version: {protocol_version}")
        self.host = host
        self.port = port
        self.runtime_id = runtime_id
        self.kind = kind
        self.token = token
        self.protocol_version = protocol_version
        self.negotiated_protocol: ProtocolVersion | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._send_lock = asyncio.Lock()
        self._receive_lock = asyncio.Lock()
        self._heartbeat_interval: float | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._capabilities: frozenset[str] = frozenset()
        self._pending_actions: dict[str, asyncio.Future[ActionResponse]] = {}
        self._closed = False

    @classmethod
    def from_environment(
        cls,
        kind: str,
        environment: Mapping[str, str] | None = None,
        *,
        protocol_version: ProtocolVersion = PROTOCOL_VERSION,
    ) -> RuntimeClient:
        values = os.environ if environment is None else environment
        return cls(
            host=values["LITEYUKI_RUNTIME_HOST"],
            port=int(values["LITEYUKI_RUNTIME_PORT"]),
            runtime_id=values["LITEYUKI_RUNTIME_ID"],
            kind=kind,
            token=values["LITEYUKI_RUNTIME_TOKEN"],
            protocol_version=protocol_version,
        )

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._closed

    async def connect(self) -> Mapping[str, JsonValue]:
        if self._reader is not None or self._writer is not None or self._closed:
            raise RuntimeError("runtime client connection is single-use")
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        try:
            await self.send(
                Hello(
                    runtime_id=self.runtime_id,
                    kind=self.kind,
                    token=self.token,
                    protocol=self.protocol_version,
                )
            )
            welcome = await self.receive()
            if not isinstance(welcome, Welcome):
                raise RuntimeProtocolError("expected welcome during runtime handshake")
            if welcome.protocol != self.protocol_version:
                raise RuntimeProtocolError(
                    "supervisor confirmed a different runtime protocol version"
                )
            config = await self.receive()
            if not isinstance(config, ConfigMessage):
                raise RuntimeProtocolError("expected config during runtime handshake")
            if welcome.heartbeat_interval <= 0:
                raise RuntimeProtocolError("runtime heartbeat interval must be positive")
            self._heartbeat_interval = welcome.heartbeat_interval
            self.negotiated_protocol = welcome.protocol
            return config.options
        except BaseException:
            await self.close()
            raise

    async def ready(self, capabilities: Sequence[str] = ()) -> None:
        if self._heartbeat_task is not None:
            raise RuntimeError("runtime client is already ready")
        normalized = tuple(capabilities)
        await self.send(Ready(capabilities=normalized))
        self._capabilities = frozenset(normalized)
        assert self._heartbeat_interval is not None
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat(self._heartbeat_interval),
            name=f"runtime-heartbeat:{self.runtime_id}",
        )

    async def receive(self) -> WireMessage:
        if self._reader is None or self._closed:
            raise ConnectionError("runtime client is not connected")
        if self._receive_lock.locked():
            raise RuntimeError("runtime client already has an active receiver")
        async with self._receive_lock:
            while True:
                try:
                    message = await read_message(self._reader)
                except (EOFError, ConnectionError, RuntimeProtocolError) as error:
                    self._fail_pending_actions(error)
                    raise
                if isinstance(message, ActionResponse):
                    future = self._pending_actions.pop(message.correlation_id, None)
                    if future is not None and not future.done():
                        future.set_result(message)
                        continue
                return message

    async def execute_action(
        self,
        correlation_id: str,
        payload: Mapping[str, Any],
        timeout_seconds: float = 30.0,
    ) -> ActionResponse:
        if timeout_seconds <= 0:
            raise ValueError("runtime action timeout must be positive")
        if self.negotiated_protocol != 3:
            raise RuntimeError("child-originated actions require runtime protocol v3")
        if self._heartbeat_task is None:
            raise RuntimeError("runtime client is not ready")
        if "runtime.actions.send" not in self._capabilities:
            raise RuntimeError("runtime client did not declare runtime.actions.send")
        if correlation_id in self._pending_actions:
            raise ValueError(f"duplicate action correlation id: {correlation_id}")

        request = ActionRequest(
            correlation_id=correlation_id,
            payload=json_mapping(payload),
        )
        future: asyncio.Future[ActionResponse] = asyncio.get_running_loop().create_future()
        self._pending_actions[correlation_id] = future
        try:
            await self.send(request)
            async with asyncio.timeout(timeout_seconds):
                return await future
        finally:
            self._pending_actions.pop(correlation_id, None)

    async def send(self, message: WireMessage) -> None:
        writer = self._writer
        if writer is None or self._closed:
            raise ConnectionError("runtime client is not connected")
        async with self._send_lock:
            if self._writer is not writer or self._closed:
                raise ConnectionError("runtime client is not connected")
            await write_message(writer, message)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._fail_pending_actions(ConnectionError("runtime client closed"))
        heartbeat, self._heartbeat_task = self._heartbeat_task, None
        self._capabilities = frozenset()
        if heartbeat is not None:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
        async with self._send_lock:
            writer, self._writer = self._writer, None
            self._reader = None
            self.negotiated_protocol = None
            if writer is not None:
                writer.close()
                await writer.wait_closed()

    def _fail_pending_actions(self, error: BaseException) -> None:
        for future in self._pending_actions.values():
            if not future.done():
                future.set_exception(error)
        self._pending_actions.clear()

    async def _heartbeat(self, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            await self.send(Heartbeat(monotonic=time.monotonic()))


__all__ = ["RuntimeClient"]
