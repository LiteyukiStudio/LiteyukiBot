"""Reusable versioned client for supervised child runtimes."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Mapping, Sequence

from ..exceptions import RuntimeProtocolError
from .protocol import (
    PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    ConfigMessage,
    Heartbeat,
    Hello,
    JsonValue,
    ProtocolVersion,
    Ready,
    Welcome,
    WireMessage,
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
        self._heartbeat_interval: float | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
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
        await self.send(Ready(capabilities=tuple(capabilities)))
        assert self._heartbeat_interval is not None
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat(self._heartbeat_interval),
            name=f"runtime-heartbeat:{self.runtime_id}",
        )

    async def receive(self) -> WireMessage:
        if self._reader is None or self._closed:
            raise ConnectionError("runtime client is not connected")
        return await read_message(self._reader)

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
        heartbeat, self._heartbeat_task = self._heartbeat_task, None
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

    async def _heartbeat(self, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            await self.send(Heartbeat(monotonic=time.monotonic()))


__all__ = ["RuntimeClient"]
