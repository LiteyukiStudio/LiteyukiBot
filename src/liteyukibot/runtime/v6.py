"""LiteyukiBot v6 plugin compatibility child runtime."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Mapping, Sequence
from typing import Any

from yukilog import configure_child_runtime, get_logger

from liteyuki.bot import _emit_lifecycle, _install_runtime, _reset_runtime
from liteyuki.plugin import load_plugin, load_plugins

from .protocol import (
    ActionRequest,
    ActionResponse,
    ConfigMessage,
    Heartbeat,
    Hello,
    Ready,
    Shutdown,
    Welcome,
    read_message,
    write_message,
)


async def run() -> None:
    configure_child_runtime()
    logger = get_logger(component="legacy", runtime=os.environ.get("LITEYUKI_RUNTIME_ID", "v6"))
    host = os.environ["LITEYUKI_RUNTIME_HOST"]
    port = int(os.environ["LITEYUKI_RUNTIME_PORT"])
    token = os.environ["LITEYUKI_RUNTIME_TOKEN"]
    runtime_id = os.environ["LITEYUKI_RUNTIME_ID"]
    reader, writer = await asyncio.open_connection(host, port)
    await write_message(writer, Hello(runtime_id=runtime_id, kind="v6", token=token))
    welcome = await read_message(reader)
    config_message = await read_message(reader)
    if not isinstance(welcome, Welcome) or not isinstance(config_message, ConfigMessage):
        raise RuntimeError("invalid supervisor handshake")

    options = config_message.options
    legacy_config = _mapping_option(options, "config")
    restart_requested = asyncio.Event()
    loop = asyncio.get_running_loop()

    def request_restart(_name: str | None) -> None:
        loop.call_soon_threadsafe(restart_requested.set)

    _install_runtime(legacy_config, request_restart)
    restarting = False
    try:
        _load_configured_plugins(options)
        await _emit_lifecycle("before_start")
        await _emit_lifecycle("after_start")
        if int(os.environ.get("LITEYUKI_RUNTIME_RESTART_COUNT", "0")) > 0:
            await _emit_lifecycle("after_restart")
        await write_message(writer, Ready(capabilities=("v6.plugins", "v6.lifecycle")))

        heartbeat_task = asyncio.create_task(
            _heartbeat(writer, welcome.heartbeat_interval),
            name="v6-runtime-heartbeat",
        )
        try:
            while True:
                incoming = asyncio.create_task(read_message(reader), name="v6-runtime-receive")
                restart = asyncio.create_task(restart_requested.wait(), name="v6-runtime-restart")
                done, pending = await asyncio.wait(
                    (incoming, restart),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                if restart in done and restart.result():
                    restarting = True
                    await _emit_lifecycle("before_process_restart", runtime_id)
                    break
                message = incoming.result()
                if isinstance(message, Shutdown):
                    await _emit_lifecycle("before_process_shutdown", runtime_id)
                    break
                if isinstance(message, ActionRequest):
                    await write_message(
                        writer,
                        ActionResponse(
                            correlation_id=message.correlation_id,
                            ok=False,
                            error="v6 compatibility plugins do not expose a protocol adapter",
                        ),
                    )
        finally:
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)
        await _emit_lifecycle("after_shutdown")
    finally:
        _reset_runtime()
        writer.close()
        await writer.wait_closed()
    if restarting:
        logger.info("v6 compatibility runtime requested restart")
        raise RuntimeError("v6 compatibility runtime requested restart")


async def _heartbeat(writer: asyncio.StreamWriter, interval: float) -> None:
    while True:
        await asyncio.sleep(interval)
        await write_message(writer, Heartbeat(monotonic=time.monotonic()))


def _mapping_option(options: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = options.get(key, {})
    if not isinstance(value, Mapping):
        raise ValueError(f"v6 runtime option {key!r} must be an object")
    return value


def _string_list_option(options: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = options.get(key, [])
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"v6 runtime option {key!r} must be an array of strings")
    if any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"v6 runtime option {key!r} must contain non-empty strings")
    return tuple(value)


def _load_configured_plugins(options: Mapping[str, Any]) -> None:
    failed = [name for name in _string_list_option(options, "plugins") if load_plugin(name) is None]
    directories = _string_list_option(options, "plugin_dirs")
    loaded_from_directories = load_plugins(*directories, ignore_warning=False)
    if failed:
        raise RuntimeError(f"failed to load v6 plugins: {', '.join(failed)}")
    if directories and not loaded_from_directories:
        raise RuntimeError("configured v6 plugin directories did not load any plugins")


__all__ = ["run"]
