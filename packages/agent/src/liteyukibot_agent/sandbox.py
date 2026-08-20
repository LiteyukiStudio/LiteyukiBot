"""Policy-bound sandbox Tool declarations and fresh worker execution."""

from __future__ import annotations

import asyncio
import http.client
import importlib
import inspect
import ipaddress
import json
import os
import socket
import ssl
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse
from uuid import uuid4

from liteyukibot_agent_resolver import AgentToolDescriptor

from liteyukibot.events.models import JsonValue

from .catalog import SandboxToolDefinition

SANDBOX_FILE_READ = "agent.sandbox.file.read"
SANDBOX_FILE_WRITE = "agent.sandbox.file.write"
SANDBOX_HTTP_FETCH = "agent.sandbox.http.fetch"
SANDBOX_COMMAND_EXEC = "agent.sandbox.command.exec"

_BUILTIN_FILE_READ = "builtin:file_read"
_BUILTIN_FILE_WRITE = "builtin:file_write"
_BUILTIN_HTTP_FETCH = "builtin:http_fetch"
_BUILTIN_COMMAND_EXEC = "builtin:command_exec"
_DEFAULT_MAX_FILE_BYTES = 256 * 1024
_DEFAULT_MAX_OUTPUT_BYTES = 32 * 1024
_DEFAULT_WALL_TIMEOUT_SECONDS = 15.0


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to one already-validated address while retaining hostname SNI."""

    def __init__(self, hostname: str, port: int, address: str, *, timeout: float) -> None:
        self._ssl_context = ssl.create_default_context()
        super().__init__(hostname, port, timeout=timeout, context=self._ssl_context)
        self._address = address

    def connect(self) -> None:
        raw_socket = socket.create_connection((self._address, self.port), self.timeout)
        try:
            self.sock = self._ssl_context.wrap_socket(raw_socket, server_hostname=self.host)
        except BaseException:
            raw_socket.close()
            raise


@dataclass(frozen=True, slots=True)
class SandboxPolicy:
    """Validated worker policy; it is copied into every fresh worker request."""

    file_roots: tuple[Path, ...]
    command_allowlist: tuple[str, ...]
    allowed_hosts: tuple[str, ...]
    allowed_ports: tuple[int, ...]
    allow_private_network: bool
    wall_timeout_seconds: float
    max_output_bytes: int
    max_file_bytes: int
    work_directory: Path

    @classmethod
    def from_options(cls, options: Mapping[str, Any], *, default_root: Path) -> SandboxPolicy:
        file_roots = _paths(options.get("file_roots", (str(default_root),)), "file_roots")
        if not file_roots:
            raise ValueError("sandbox file_roots must not be empty")
        command_allowlist = _strings(options.get("command_allowlist", ()), "command_allowlist")
        allowed_hosts = tuple(item.casefold() for item in _strings(options.get("allowed_hosts", ()), "allowed_hosts"))
        allowed_ports = _ports(options.get("allowed_ports", (443,)))
        allow_private_network = _bool(options.get("allow_private_network", False), "allow_private_network")
        wall_timeout_seconds = _positive_float(
            options.get("wall_timeout_seconds", _DEFAULT_WALL_TIMEOUT_SECONDS), "wall_timeout_seconds"
        )
        max_output_bytes = _positive_int(
            options.get("max_output_bytes", _DEFAULT_MAX_OUTPUT_BYTES), "max_output_bytes"
        )
        max_file_bytes = _positive_int(options.get("max_file_bytes", _DEFAULT_MAX_FILE_BYTES), "max_file_bytes")
        work_directory = _path(options.get("work_directory", str(default_root / "worker")), "work_directory")
        for root in file_roots:
            root.mkdir(parents=True, exist_ok=True)
        work_directory.mkdir(parents=True, exist_ok=True)
        return cls(
            file_roots=file_roots,
            command_allowlist=command_allowlist,
            allowed_hosts=allowed_hosts,
            allowed_ports=allowed_ports,
            allow_private_network=allow_private_network,
            wall_timeout_seconds=wall_timeout_seconds,
            max_output_bytes=max_output_bytes,
            max_file_bytes=max_file_bytes,
            work_directory=work_directory,
        )

    def wire(self) -> dict[str, JsonValue]:
        return {
            "file_roots": tuple(str(path) for path in self.file_roots),
            "command_allowlist": self.command_allowlist,
            "allowed_hosts": self.allowed_hosts,
            "allowed_ports": self.allowed_ports,
            "allow_private_network": self.allow_private_network,
            "wall_timeout_seconds": self.wall_timeout_seconds,
            "max_output_bytes": self.max_output_bytes,
            "max_file_bytes": self.max_file_bytes,
            "work_directory": str(self.work_directory),
        }


@dataclass(frozen=True, slots=True)
class SandboxExecutionResult:
    success: bool
    result: JsonValue = None
    error_code: str | None = None
    error_details: Mapping[str, JsonValue] | None = None


def builtin_sandbox_tools() -> tuple[SandboxToolDefinition, ...]:
    return (
        SandboxToolDefinition(
            AgentToolDescriptor(
                id=SANDBOX_FILE_READ,
                module_id="sandbox.builtin",
                title="Read a sandbox file",
                description="Read UTF-8 text from a configured sandbox file root.",
                input_schema={
                    "type": "object",
                    "properties": {"path": {"type": "string", "minLength": 1}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
            ),
            _BUILTIN_FILE_READ,
        ),
        SandboxToolDefinition(
            AgentToolDescriptor(
                id=SANDBOX_FILE_WRITE,
                module_id="sandbox.builtin",
                title="Write a sandbox file",
                description="Write UTF-8 text inside a configured sandbox file root.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "minLength": 1},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
            ),
            _BUILTIN_FILE_WRITE,
        ),
        SandboxToolDefinition(
            AgentToolDescriptor(
                id=SANDBOX_HTTP_FETCH,
                module_id="sandbox.builtin",
                title="Fetch an HTTPS resource",
                description="Fetch a public HTTPS resource under the configured network policy.",
                input_schema={
                    "type": "object",
                    "properties": {"url": {"type": "string", "minLength": 1}},
                    "required": ["url"],
                    "additionalProperties": False,
                },
            ),
            _BUILTIN_HTTP_FETCH,
        ),
        SandboxToolDefinition(
            AgentToolDescriptor(
                id=SANDBOX_COMMAND_EXEC,
                module_id="sandbox.builtin",
                title="Run an allowed command",
                description="Run one explicitly allowlisted command without a shell.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                        "input": {"type": "string"},
                    },
                    "required": ["command"],
                    "additionalProperties": False,
                },
            ),
            _BUILTIN_COMMAND_EXEC,
        ),
    )


async def execute_in_fresh_worker(
    definition: SandboxToolDefinition,
    arguments: Mapping[str, JsonValue],
    policy: SandboxPolicy,
) -> SandboxExecutionResult:
    """Run exactly one Tool invocation in a new native Python subprocess."""

    correlation_id = str(uuid4())
    request = json.dumps(
        {
            "correlation_id": correlation_id,
            "tool_id": definition.descriptor.id,
            "worker_ref": definition.worker_ref,
            "arguments": dict(arguments),
            "policy": policy.wire(),
        },
        ensure_ascii=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8") + b"\n"
    environment = {
        name: value
        for name in ("PATH", "PATHEXT", "SystemRoot", "TEMP", "TMP", "LANG")
        if (value := os.environ.get(name)) is not None
    }
    environment["PYTHONIOENCODING"] = "utf-8"
    process: asyncio.subprocess.Process | None = None
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "liteyukibot_agent.sandbox_worker",
            cwd=str(policy.work_directory),
            env=environment,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await asyncio.wait_for(
            process.communicate(request), timeout=policy.wall_timeout_seconds
        )
    except TimeoutError:
        if process is not None:
            process.kill()
            await process.wait()
        return SandboxExecutionResult(False, error_code="SANDBOX_TIMEOUT")
    except asyncio.CancelledError:
        if process is not None:
            process.kill()
            await process.wait()
        raise
    except OSError:
        return SandboxExecutionResult(False, error_code="SANDBOX_START_FAILED")
    if len(stdout) > policy.max_output_bytes:
        return SandboxExecutionResult(False, error_code="SANDBOX_OUTPUT_LIMIT")
    if process.returncode != 0:
        return SandboxExecutionResult(False, error_code="SANDBOX_CRASH")
    try:
        response = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return SandboxExecutionResult(False, error_code="SANDBOX_PROTOCOL_INVALID")
    if not isinstance(response, dict) or response.get("correlation_id") != correlation_id:
        return SandboxExecutionResult(False, error_code="SANDBOX_PROTOCOL_INVALID")
    success = response.get("success")
    if not isinstance(success, bool):
        return SandboxExecutionResult(False, error_code="SANDBOX_PROTOCOL_INVALID")
    result = response.get("result")
    error_code = response.get("error_code")
    if success:
        if error_code is not None:
            return SandboxExecutionResult(False, error_code="SANDBOX_PROTOCOL_INVALID")
        return SandboxExecutionResult(True, cast(JsonValue, result))
    if not isinstance(error_code, str) or not error_code:
        return SandboxExecutionResult(False, error_code="SANDBOX_PROTOCOL_INVALID")
    details = response.get("error_details")
    return SandboxExecutionResult(False, cast(JsonValue, result), error_code, _mapping_or_none(details))


def _resolve_path(raw: object, policy: Mapping[str, object], *, write: bool) -> tuple[Path | None, str | None]:
    if not isinstance(raw, str) or not raw.strip():
        return None, "SANDBOX_INVALID_ARGUMENTS"
    roots = tuple(Path(item).resolve() for item in _sequence_strings(policy.get("file_roots")))
    if not roots:
        return None, "SANDBOX_POLICY_DENIED"
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = roots[0] / candidate
    candidate = candidate.resolve(strict=False)
    root = next((root for root in roots if candidate.is_relative_to(root)), None)
    if root is None or _contains_symlink(root, candidate):
        return None, "SANDBOX_PATH_DENIED"
    if not write and (not candidate.is_file() or candidate.is_symlink()):
        return None, "SANDBOX_FILE_NOT_FOUND"
    return candidate, None


def builtin_file_read(arguments: Mapping[str, object], policy: Mapping[str, object]) -> tuple[JsonValue, str | None]:
    path, error = _resolve_path(arguments.get("path"), policy, write=False)
    if error is not None or path is None:
        return None, error
    max_bytes = _policy_int(policy, "max_file_bytes", _DEFAULT_MAX_FILE_BYTES)
    if path.stat().st_size > max_bytes:
        return None, "SANDBOX_FILE_LIMIT"
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None, "SANDBOX_FILE_READ_FAILED"
    return {"path": _relative_source(path, policy), "content": content}, None


def builtin_file_write(arguments: Mapping[str, object], policy: Mapping[str, object]) -> tuple[JsonValue, str | None]:
    path, error = _resolve_path(arguments.get("path"), policy, write=True)
    content = arguments.get("content")
    if error is not None or path is None:
        return None, error
    if not isinstance(content, str):
        return None, "SANDBOX_INVALID_ARGUMENTS"
    encoded = content.encode("utf-8")
    if len(encoded) > _policy_int(policy, "max_file_bytes", _DEFAULT_MAX_FILE_BYTES):
        return None, "SANDBOX_FILE_LIMIT"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encoded)
    except OSError:
        return None, "SANDBOX_FILE_WRITE_FAILED"
    return {"path": _relative_source(path, policy), "bytes": len(encoded)}, None


def builtin_http_fetch(arguments: Mapping[str, object], policy: Mapping[str, object]) -> tuple[JsonValue, str | None]:
    raw_url = arguments.get("url")
    if not isinstance(raw_url, str) or not raw_url.strip():
        return None, "SANDBOX_INVALID_ARGUMENTS"
    parsed = urlparse(raw_url)
    hostname = parsed.hostname.casefold() if parsed.hostname else None
    if (
        parsed.scheme.casefold() != "https"
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None, "SANDBOX_NETWORK_DENIED"
    allowed_hosts = tuple(item.casefold() for item in _sequence_strings(policy.get("allowed_hosts")))
    if allowed_hosts and hostname not in allowed_hosts:
        return None, "SANDBOX_NETWORK_DENIED"
    try:
        port = parsed.port or 443
    except ValueError:
        return None, "SANDBOX_NETWORK_DENIED"
    if port not in _policy_ports(policy):
        return None, "SANDBOX_NETWORK_DENIED"
    address = _resolve_network_address(
        hostname,
        port,
        allow_private=_policy_bool(policy, "allow_private_network", False),
    )
    if address is None:
        return None, "SANDBOX_NETWORK_DENIED"
    target = parsed.path or "/"
    if parsed.params:
        target += ";" + parsed.params
    if parsed.query:
        target += "?" + parsed.query
    host_header = hostname
    if port != 443:
        host_header = f"[{hostname}]" if ":" in hostname else hostname
        host_header += f":{port}"
    connection = _PinnedHTTPSConnection(
        hostname,
        port,
        address,
        timeout=_policy_float(policy, "wall_timeout_seconds", _DEFAULT_WALL_TIMEOUT_SECONDS),
    )
    try:
        connection.request(
            "GET",
            target,
            headers={"Host": host_header, "User-Agent": "LiteyukiBot-Agent-Sandbox/1"},
        )
        response = connection.getresponse()
        body = response.read(_policy_int(policy, "max_output_bytes", _DEFAULT_MAX_OUTPUT_BYTES) + 1)
        if len(body) > _policy_int(policy, "max_output_bytes", _DEFAULT_MAX_OUTPUT_BYTES):
            return None, "SANDBOX_OUTPUT_LIMIT"
        return {
            "url": raw_url,
            "status": int(response.status),
            "content": body.decode("utf-8", errors="replace"),
        }, None
    except (http.client.HTTPException, TimeoutError, OSError):
        return None, "SANDBOX_NETWORK_FAILED"
    finally:
        connection.close()


def builtin_command_exec(arguments: Mapping[str, object], policy: Mapping[str, object]) -> tuple[JsonValue, str | None]:
    raw_command = arguments.get("command")
    if not isinstance(raw_command, Sequence) or isinstance(raw_command, (str, bytes)):
        return None, "SANDBOX_INVALID_ARGUMENTS"
    command = tuple(item for item in raw_command if isinstance(item, str))
    if len(command) != len(raw_command) or not command:
        return None, "SANDBOX_INVALID_ARGUMENTS"
    allowlist = _sequence_strings(policy.get("command_allowlist"))
    if command[0] not in allowlist:
        return None, "SANDBOX_COMMAND_DENIED"
    stdin = arguments.get("input", "")
    if not isinstance(stdin, str):
        return None, "SANDBOX_INVALID_ARGUMENTS"
    try:
        completed = subprocess.run(
            command,
            cwd=str(policy.get("work_directory", Path.cwd())),
            input=stdin,
            text=True,
            capture_output=True,
            shell=False,
            timeout=_policy_float(policy, "wall_timeout_seconds", 15.0),
            env={"PATH": os.environ.get("PATH", ""), "SystemRoot": os.environ.get("SystemRoot", "")},
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, "SANDBOX_TIMEOUT"
    except OSError:
        return None, "SANDBOX_COMMAND_FAILED"
    output = (completed.stdout + completed.stderr).encode("utf-8", errors="replace")
    limit = _policy_int(policy, "max_output_bytes", _DEFAULT_MAX_OUTPUT_BYTES)
    if len(output) > limit:
        output = output[:limit]
        truncated = True
    else:
        truncated = False
    return {
        "return_code": completed.returncode,
        "output": output.decode("utf-8", errors="replace"),
        "truncated": truncated,
    }, None


def load_worker_callable(reference: str) -> Any:
    module_name, separator, attribute = reference.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError("invalid sandbox worker reference")
    value: Any = importlib.import_module(module_name)
    for part in attribute.split("."):
        value = getattr(value, part)
    if not callable(value):
        raise TypeError("sandbox worker reference is not callable")
    return value


async def run_worker_callable(
    reference: str, arguments: Mapping[str, object], policy: Mapping[str, object]
) -> tuple[JsonValue, str | None]:
    builtin = reference.startswith("builtin:")
    if builtin:
        handlers = {
            _BUILTIN_FILE_READ: builtin_file_read,
            _BUILTIN_FILE_WRITE: builtin_file_write,
            _BUILTIN_HTTP_FETCH: builtin_http_fetch,
            _BUILTIN_COMMAND_EXEC: builtin_command_exec,
        }
        handler = handlers.get(reference)
        if handler is None:
            return None, "SANDBOX_TOOL_NOT_FOUND"
    else:
        try:
            handler = load_worker_callable(reference)
        except (ImportError, AttributeError, TypeError, ValueError):
            return None, "SANDBOX_TOOL_NOT_FOUND"
    try:
        value = handler(arguments, policy)
        if inspect.isawaitable(value):
            value = await value
    except PermissionError:
        return None, "SANDBOX_POLICY_DENIED"
    except Exception:
        return None, "SANDBOX_TOOL_FAILED"
    if builtin:
        if not isinstance(value, tuple) or len(value) != 2 or not isinstance(value[1], (str, type(None))):
            return None, "SANDBOX_PROTOCOL_INVALID"
        return cast(JsonValue, value[0]), value[1]
    return cast(JsonValue, value), None


def _paths(value: object, field: str) -> tuple[Path, ...]:
    return tuple(_path(item, field) for item in _sequence_strings(value))


def _path(value: object, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"sandbox {field} entries must be non-empty strings")
    return Path(value).resolve()


def _strings(value: object, field: str) -> tuple[str, ...]:
    result = _sequence_strings(value)
    if len(set(result)) != len(result):
        raise ValueError(f"sandbox {field} must not contain duplicates")
    return result


def _sequence_strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("sandbox option must be an array")
    result = tuple(item for item in value if isinstance(item, str) and item.strip())
    if len(result) != len(value):
        raise ValueError("sandbox option array must contain trimmed strings")
    return result


def _ports(value: object) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("sandbox allowed_ports must be an array")
    result = tuple(item for item in value if isinstance(item, int) and not isinstance(item, bool))
    if len(result) != len(value) or any(not 1 <= item <= 65_535 for item in result):
        raise ValueError("sandbox allowed_ports must contain valid TCP ports")
    if len(result) != len(set(result)):
        raise ValueError("sandbox allowed_ports must not contain duplicates")
    return result


def _positive_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"sandbox {field} must be a positive integer")
    return value


def _positive_float(value: object, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"sandbox {field} must be a positive number")
    return float(value)


def _bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"sandbox {field} must be boolean")
    return value


def _contains_symlink(root: Path, candidate: Path) -> bool:
    relative = candidate.relative_to(root)
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            return True
    return False


def _relative_source(path: Path, policy: Mapping[str, object]) -> str:
    roots = tuple(Path(item).resolve() for item in _sequence_strings(policy.get("file_roots")))
    for index, root in enumerate(roots):
        if path.is_relative_to(root):
            return f"root-{index}/{path.relative_to(root).as_posix()}"
    return "sandbox/unknown"


def _resolve_network_address(hostname: str, port: int, *, allow_private: bool) -> str | None:
    try:
        raw_addresses = tuple(
            address for item in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
            if isinstance((address := item[4][0]), str)
        )
    except socket.gaierror:
        return None
    addresses = tuple(dict.fromkeys(raw_addresses))
    if not addresses:
        return None
    if not allow_private:
        try:
            if any(not ipaddress.ip_address(address.split("%", 1)[0]).is_global for address in addresses):
                return None
        except ValueError:
            return None
    return addresses[0]


def _policy_int(policy: Mapping[str, object], key: str, default: int) -> int:
    value = policy.get(key, default)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else default


def _policy_float(policy: Mapping[str, object], key: str, default: float) -> float:
    value = policy.get(key, default)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else default


def _policy_bool(policy: Mapping[str, object], key: str, default: bool) -> bool:
    value = policy.get(key, default)
    return value if isinstance(value, bool) else default


def _policy_ports(policy: Mapping[str, object]) -> tuple[int, ...]:
    value = policy.get("allowed_ports", (443,))
    if not isinstance(value, Sequence):
        return (443,)
    return tuple(item for item in value if isinstance(item, int) and not isinstance(item, bool))


def _mapping_or_none(value: object) -> Mapping[str, JsonValue] | None:
    return cast(Mapping[str, JsonValue], value) if isinstance(value, Mapping) else None


__all__ = [
    "SANDBOX_COMMAND_EXEC",
    "SANDBOX_FILE_READ",
    "SANDBOX_FILE_WRITE",
    "SANDBOX_HTTP_FETCH",
    "SandboxExecutionResult",
    "SandboxPolicy",
    "builtin_sandbox_tools",
    "builtin_command_exec",
    "builtin_file_read",
    "builtin_file_write",
    "builtin_http_fetch",
    "execute_in_fresh_worker",
    "run_worker_callable",
]
