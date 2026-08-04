"""Built-in child runtime entry point."""

from __future__ import annotations

import argparse
import asyncio
import os
import time

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


async def run_noop(kind: str) -> None:
    host = os.environ["LITEYUKI_RUNTIME_HOST"]
    port = int(os.environ["LITEYUKI_RUNTIME_PORT"])
    token = os.environ["LITEYUKI_RUNTIME_TOKEN"]
    runtime_id = os.environ["LITEYUKI_RUNTIME_ID"]
    reader, writer = await asyncio.open_connection(host, port)
    await write_message(writer, Hello(runtime_id=runtime_id, kind=kind, token=token))
    welcome = await read_message(reader)
    config = await read_message(reader)
    if not isinstance(welcome, Welcome) or not isinstance(config, ConfigMessage):
        raise RuntimeError("invalid supervisor handshake")
    if kind != "noop":
        raise RuntimeError(f"runtime kind {kind!r} is not installed")
    await write_message(writer, Ready(capabilities=("noop",)))

    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(welcome.heartbeat_interval)
            await write_message(writer, Heartbeat(monotonic=time.monotonic()))

    heartbeat_task = asyncio.create_task(heartbeat(), name="runtime-heartbeat")
    try:
        while True:
            message = await read_message(reader)
            if isinstance(message, Shutdown):
                return
            if isinstance(message, ActionRequest):
                await write_message(
                    writer,
                    ActionResponse(
                        correlation_id=message.correlation_id,
                        ok=True,
                        data={"echo": message.payload},
                    ),
                )
    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
        writer.close()
        await writer.wait_closed()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", required=True)
    args = parser.parse_args()
    if args.kind == "v6":
        from .v6 import run as run_v6

        asyncio.run(run_v6())
        return
    if args.kind == "nonebot":
        from .nonebot import run as run_nonebot

        run_nonebot()
        return
    asyncio.run(run_noop(args.kind))


if __name__ == "__main__":
    main()
