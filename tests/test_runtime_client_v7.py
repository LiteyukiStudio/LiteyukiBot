from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import pytest

from liteyukibot.exceptions import RuntimeProtocolError
from liteyukibot.runtime import RuntimeClient
from liteyukibot.runtime.protocol import (
    PROTOCOL_VERSION,
    ConfigMessage,
    ErrorMessage,
    Heartbeat,
    Hello,
    ProtocolVersion,
    Ready,
    Welcome,
    read_message,
    write_message,
)

type ServerHandler = Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]]


async def _server(handler: ServerHandler) -> tuple[asyncio.Server, int, asyncio.Future[None]]:
    done: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    async def wrapped(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await handler(reader, writer)
        except BaseException as error:
            if not done.done():
                done.set_exception(error)
        else:
            if not done.done():
                done.set_result(None)

    server = await asyncio.start_server(wrapped, "127.0.0.1", 0)
    port = int(server.sockets[0].getsockname()[1])
    return server, port, done


def _client(port: int, protocol_version: ProtocolVersion = PROTOCOL_VERSION) -> RuntimeClient:
    return RuntimeClient(
        host="127.0.0.1",
        port=port,
        runtime_id="fixture",
        kind="test",
        token="secret",
        protocol_version=protocol_version,
    )


def test_runtime_client_rejects_unsupported_protocol_before_connecting() -> None:
    with pytest.raises(ValueError, match="unsupported runtime protocol version"):
        RuntimeClient(
            host="127.0.0.1",
            port=1,
            runtime_id="fixture",
            kind="test",
            token="secret",
            protocol_version=4,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_runtime_client_handshake_ready_heartbeat_and_close() -> None:
    observed: list[object] = []
    heartbeat_seen = asyncio.Event()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        observed.append(await read_message(reader))
        await write_message(writer, Welcome(heartbeat_interval=0.01))
        await write_message(writer, ConfigMessage(options={"enabled": True}))
        observed.append(await read_message(reader))
        observed.append(await read_message(reader))
        heartbeat_seen.set()
        assert await reader.read() == b""
        writer.close()
        await writer.wait_closed()

    server, port, server_done = await _server(handle)
    client = _client(port)
    try:
        assert await client.connect() == {"enabled": True}
        assert client.connected is True
        await client.ready(("events",))
        await asyncio.wait_for(heartbeat_seen.wait(), timeout=1)
        await client.close()
        await client.close()
        await server_done
    finally:
        await client.close()
        server.close()
        await server.wait_closed()

    assert isinstance(observed[0], Hello)
    assert observed[0].protocol == 3
    assert observed[1] == Ready(capabilities=("events",))
    assert isinstance(observed[2], Heartbeat)
    assert client.connected is False


@pytest.mark.asyncio
async def test_runtime_client_serializes_concurrent_writes() -> None:
    responses: list[object] = []

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        assert isinstance(await read_message(reader), Hello)
        await write_message(writer, Welcome())
        await write_message(writer, ConfigMessage())
        responses.extend([await read_message(reader), await read_message(reader)])
        writer.close()
        await writer.wait_closed()

    server, port, server_done = await _server(handle)
    client = _client(port)
    try:
        await client.connect()
        await asyncio.gather(
            client.send(ErrorMessage(code="first", message="one")),
            client.send(ErrorMessage(code="second", message="two")),
        )
        await server_done
    finally:
        await client.close()
        server.close()
        await server.wait_closed()

    assert {message.code for message in responses if isinstance(message, ErrorMessage)} == {
        "first",
        "second",
    }


@pytest.mark.asyncio
async def test_runtime_client_rejects_invalid_handshake_and_closes() -> None:
    peer_closed = asyncio.Event()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        assert isinstance(await read_message(reader), Hello)
        await write_message(writer, ConfigMessage())
        assert await reader.read() == b""
        peer_closed.set()
        writer.close()
        await writer.wait_closed()

    server, port, server_done = await _server(handle)
    client = _client(port)
    try:
        with pytest.raises(RuntimeProtocolError, match="expected welcome"):
            await client.connect()
        await asyncio.wait_for(peer_closed.wait(), timeout=1)
        await server_done
    finally:
        await client.close()
        server.close()
        await server.wait_closed()

    assert client.connected is False


@pytest.mark.asyncio
async def test_runtime_client_reports_eof_after_handshake() -> None:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        assert isinstance(await read_message(reader), Hello)
        await write_message(writer, Welcome())
        await write_message(writer, ConfigMessage())
        writer.close()
        await writer.wait_closed()

    server, port, server_done = await _server(handle)
    client = _client(port)
    try:
        await client.connect()
        with pytest.raises(EOFError, match="connection closed"):
            await client.receive()
        await server_done
    finally:
        await client.close()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol_version", [1, 2])
async def test_runtime_client_can_negotiate_older_protocol(
    protocol_version: ProtocolVersion,
) -> None:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        hello = await read_message(reader)
        assert isinstance(hello, Hello)
        assert hello.protocol == protocol_version
        await write_message(writer, Welcome(protocol=protocol_version))
        await write_message(writer, ConfigMessage())
        assert await reader.read() == b""
        writer.close()
        await writer.wait_closed()

    server, port, server_done = await _server(handle)
    client = _client(port, protocol_version=protocol_version)
    try:
        assert await client.connect() == {}
        assert client.negotiated_protocol == protocol_version
    finally:
        await client.close()
        await server_done
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_runtime_client_rejects_protocol_version_mismatch() -> None:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        hello = await read_message(reader)
        assert isinstance(hello, Hello)
        assert hello.protocol == 3
        await write_message(writer, Welcome(protocol=1))
        assert await reader.read() == b""
        writer.close()
        await writer.wait_closed()

    server, port, server_done = await _server(handle)
    client = _client(port)
    try:
        with pytest.raises(RuntimeProtocolError, match="different runtime protocol"):
            await client.connect()
        await server_done
    finally:
        await client.close()
        server.close()
        await server.wait_closed()
