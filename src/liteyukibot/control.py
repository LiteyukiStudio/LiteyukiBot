"""Authenticated loopback control channel for local CLI operations."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
from collections.abc import Awaitable, Callable, Mapping
from ipaddress import ip_address
from pathlib import Path
from typing import Any

MAX_CONTROL_MESSAGE = 64 * 1024

type StatusProvider = Callable[[], Mapping[str, Any]]
type RuntimeRestarter = Callable[[str], Awaitable[None]]
type ControlHandler = Callable[[Mapping[str, Any]], Awaitable[Any]]


class ControlError(RuntimeError):
    """Raised when the control contract cannot be satisfied."""
    pass


class ControlServer:
    """Expose authenticated, bounded daemon commands on a loopback socket."""
    def __init__(
        self,
        descriptor_path: Path,
        *,
        status_provider: StatusProvider,
        runtime_restarter: RuntimeRestarter | None = None,
        handlers: Mapping[str, ControlHandler] | None = None,
    ) -> None:
        """Initialize the control server.

        Args:
            descriptor_path: Filesystem path for the descriptor.
            status_provider: The status provider value used by the operation.
            runtime_restarter: The runtime restarter value used by the operation.
            handlers: The handlers value used by the operation.

        Returns:
            None.
        """
        self.descriptor_path = descriptor_path
        self.status_provider = status_provider
        self.runtime_restarter = runtime_restarter
        self.handlers = dict(handlers or {})
        self.token = secrets.token_urlsafe(32)
        self.server: asyncio.Server | None = None

    async def start(self) -> None:
        """Start the control server.

        Returns:
            None.

        Security:
            The descriptor contains a bearer token, so it is written through a
            temporary file with owner-only permissions before atomic replacement.
            The endpoint remains necessary for local CLI and daemon management;
            loopback alone is not considered authentication. See
            `docs/security/trusted-boundaries.md#local-control-and-diagnostics`.
        """
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        temporary = self.descriptor_path.with_suffix(".tmp")
        try:
            socket = self.server.sockets[0]
            port = int(socket.getsockname()[1])
            descriptor = {
                "protocol": 1,
                "pid": os.getpid(),
                "host": "127.0.0.1",
                "port": port,
                "token": self.token,
            }
            self.descriptor_path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(descriptor, separators=(",", ":")), encoding="utf-8")
            temporary.chmod(0o600)
            temporary.replace(self.descriptor_path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            self.server.close()
            await self.server.wait_closed()
            self.server = None
            raise

    async def stop(self) -> None:
        """Stop the control server and release its owned resources.

        Returns:
            None.
        """
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        try:
            current = json.loads(self.descriptor_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(current, dict) and secrets.compare_digest(str(current.get("token", "")), self.token):
            self.descriptor_path.unlink(missing_ok=True)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Handle the control server operation.

        Args:
            reader: The reader value used by the operation.
            writer: The writer value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `ControlServer._handle`. It delegates to `_read_request`,
            `_dispatch`, `write`, `encode` while keeping intermediate state local to the owning operation.
        """
        try:
            request = await self._read_request(reader)
            response = {"ok": True, "result": await self._dispatch(request)}
        except Exception as error:
            response = {"ok": False, "error": f"{type(error).__name__}: {error}"}
        writer.write(json.dumps(response, separators=(",", ":"), default=str).encode("utf-8") + b"\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def _read_request(self, reader: asyncio.StreamReader) -> dict[str, Any]:
        """Read and authenticate one bounded request before command dispatch.

        Args:
            reader: The reader value used by the operation.

        Returns:
            The `dict[str, Any]` result produced by the operation.

        Notes:
            Reads one newline-delimited JSON object, applies the 64 KiB bound,
            then authenticates before command dispatch.

        Security:
            Local processes can connect to loopback and send arbitrary bytes.
            Bounded reads and constant-time token comparison are retained because
            the management capability cannot rely on network location alone. See
            `docs/security/trusted-boundaries.md#local-control-and-diagnostics`.
        """

        line = await reader.readline()
        if not line or len(line) > MAX_CONTROL_MESSAGE:
            raise ControlError("invalid control message size")
        request = json.loads(line)
        if not isinstance(request, dict):
            raise ControlError("control request must be an object")
        token = request.get("token")
        if not isinstance(token, str) or not secrets.compare_digest(token, self.token):
            raise ControlError("control authentication failed")
        return request

    async def _dispatch(self, request: Mapping[str, Any]) -> Any:
        """Dispatch the control server operation.

        Args:
            request: Validated request object to process.

        Returns:
            The `Any` result produced by the operation.

        Notes:
            Internal implementation detail for `ControlServer._dispatch`. It delegates to `get`,
            `status_provider`, `runtime_restarter`, `handler` while keeping intermediate state local to the
            owning operation.
        """
        command = request.get("command")
        if command == "status":
            return self.status_provider()
        if command == "runtime.restart" and self.runtime_restarter is not None:
            runtime_id = request.get("runtime_id")
            if not isinstance(runtime_id, str) or not runtime_id:
                raise ControlError("runtime.restart requires runtime_id")
            await self.runtime_restarter(runtime_id)
            return {"runtime_id": runtime_id}
        if isinstance(command, str) and (handler := self.handlers.get(command)) is not None:
            return await handler(request)
        raise ControlError(f"unknown control command: {command}")


async def request_control(
    descriptor_path: Path,
    command: str,
    timeout_seconds: float = 60.0,
    **parameters: object,
) -> Any:
    """Authenticate to a local control descriptor and execute one command.

    Args:
        descriptor_path: Filesystem path for the descriptor.
        command: Command or operation name to execute.
        timeout_seconds: Maximum duration to wait, in seconds.
        **parameters: JSON-safe command parameters merged into the request.

    Returns:
        Command-specific JSON response value.

    Security:
        Descriptor contents are sensitive and potentially stale. Host, protocol,
        port, and token shape are validated; connections are restricted to
        loopback and bounded by timeouts. The client remains necessary for CLI
        management. See
        `docs/security/trusted-boundaries.md#local-control-and-diagnostics`.
    """
    try:
        raw_descriptor = await asyncio.to_thread(descriptor_path.read_text, encoding="utf-8")
        descriptor = json.loads(raw_descriptor)
        host, port, token = _validate_descriptor(descriptor)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ControlError(f"cannot read control descriptor {descriptor_path}: {error}") from error

    try:
        async with asyncio.timeout(timeout_seconds):
            reader, writer = await asyncio.open_connection(host, port)
    except (OSError, TimeoutError) as error:
        raise ControlError(f"cannot connect to LiteyukiBot at {host}:{port}: {error}") from error
    try:
        request = {"token": token, "command": command, **parameters}
        writer.write(json.dumps(request, separators=(",", ":")).encode("utf-8") + b"\n")
        await writer.drain()
        async with asyncio.timeout(timeout_seconds):
            line = await reader.readline()
        response = json.loads(line)
        if not isinstance(response, dict) or not response.get("ok"):
            detail = response.get("error", "invalid control response") if isinstance(response, dict) else response
            raise ControlError(str(detail))
        return response.get("result")
    except (OSError, TimeoutError, json.JSONDecodeError) as error:
        raise ControlError(f"invalid control response: {error}") from error
    finally:
        writer.close()
        await writer.wait_closed()


def _validate_descriptor(value: Any) -> tuple[str, int, str]:
    """Validate a control descriptor before opening its socket.

    Args:
        value: Parsed, untrusted descriptor JSON.

    Returns:
        Normalized loopback host, TCP port, and bearer token.

    Notes:
        Protocol and exact integer port validation run before loopback resolution.

    Security:
        A replaced descriptor could redirect a bearer token. Requiring loopback
        prevents remote disclosure while the token authenticates the local peer.
    """
    if not isinstance(value, dict):
        raise ControlError("control descriptor must be an object")
    protocol = value.get("protocol")
    if type(protocol) is not int or protocol != 1:
        raise ControlError("unsupported control descriptor protocol")

    host = value.get("host")
    if not isinstance(host, str) or not host.strip():
        raise ControlError("control descriptor host must be a non-empty string")
    host = host.strip()
    is_loopback = host.lower() == "localhost"
    if not is_loopback:
        try:
            is_loopback = ip_address(host).is_loopback
        except ValueError:
            is_loopback = False
    if not is_loopback:
        raise ControlError("control descriptor host must be loopback")

    port = value.get("port")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ControlError("control descriptor port must be between 1 and 65535")
    token = value.get("token")
    if not isinstance(token, str) or not token:
        raise ControlError("control descriptor token must be a non-empty string")
    return host, port, token


__all__ = ["ControlError", "ControlServer", "request_control"]
