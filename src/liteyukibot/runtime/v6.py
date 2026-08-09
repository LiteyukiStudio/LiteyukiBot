"""LiteyukiBot v6 plugin compatibility child runtime."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping, Sequence
from typing import Any

from yukilog import configure_child_runtime, get_logger

from liteyuki.bot import _emit_lifecycle, _install_runtime, _reset_runtime
from liteyuki.plugin import load_plugin, load_plugins

from .client import RuntimeClient
from .protocol import ActionRequest, ActionResponse, Shutdown


async def run() -> None:
    configure_child_runtime()
    logger = get_logger(component="legacy", runtime=os.environ.get("LITEYUKI_RUNTIME_ID", "v6"))
    runtime_id = os.environ["LITEYUKI_RUNTIME_ID"]
    client = RuntimeClient.from_environment("v6")
    runtime_installed = False
    restarting = False
    try:
        options = await client.connect()
        legacy_config = _mapping_option(options, "config")
        restart_requested = asyncio.Event()
        loop = asyncio.get_running_loop()

        def request_restart(_name: str | None) -> None:
            loop.call_soon_threadsafe(restart_requested.set)

        _install_runtime(legacy_config, request_restart)
        runtime_installed = True
        _load_configured_plugins(options)
        await _emit_lifecycle("before_start")
        await _emit_lifecycle("after_start")
        if int(os.environ.get("LITEYUKI_RUNTIME_RESTART_COUNT", "0")) > 0:
            await _emit_lifecycle("after_restart")
        await client.ready(("v6.plugins", "v6.lifecycle"))

        while True:
            incoming = asyncio.create_task(client.receive(), name="v6-runtime-receive")
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
                await client.send(
                    ActionResponse(
                        correlation_id=message.correlation_id,
                        ok=False,
                        error="v6 compatibility plugins do not expose a protocol adapter",
                    )
                )
        await _emit_lifecycle("after_shutdown")
    finally:
        if runtime_installed:
            _reset_runtime()
        await client.close()
    if restarting:
        logger.info("v6 compatibility runtime requested restart")
        raise RuntimeError("v6 compatibility runtime requested restart")

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
