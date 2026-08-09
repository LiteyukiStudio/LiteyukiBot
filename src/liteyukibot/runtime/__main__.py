"""Built-in child runtime entry point."""

from __future__ import annotations

import argparse
import asyncio

from .client import RuntimeClient
from .protocol import (
    ActionRequest,
    ActionResponse,
    Shutdown,
)


async def run_noop(kind: str) -> None:
    client = RuntimeClient.from_environment(kind)
    try:
        await client.connect()
        if kind != "noop":
            raise RuntimeError(f"runtime kind {kind!r} is not installed")
        await client.ready(("noop",))
        while True:
            message = await client.receive()
            if isinstance(message, Shutdown):
                return
            if isinstance(message, ActionRequest):
                await client.send(
                    ActionResponse(
                        correlation_id=message.correlation_id,
                        ok=True,
                        data={"echo": message.payload},
                    ),
                )
    finally:
        await client.close()


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
