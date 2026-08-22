"""Built-in child runtime entry point."""

from __future__ import annotations

import argparse
import asyncio

from .client import RuntimeClient
from .protocol import (
    ActionRequest,
    ActionResponse,
    EventAccepted,
    EventCompleted,
    EventMessage,
    Shutdown,
)


async def run_noop(kind: str) -> None:
    """Run noop.

    Args:
        kind: The kind value used by the operation.

    Returns:
        None.
    """
    client = RuntimeClient.from_environment(kind)
    try:
        await client.connect()
        if kind != "noop":
            raise RuntimeError(f"runtime kind {kind!r} is not installed")
        await client.ready(("noop", "runtime.events.receive", "runtime.events.complete"))
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
            if isinstance(message, EventMessage):
                await client.send(
                    EventAccepted(
                        correlation_id=message.correlation_id,
                        status="accepted",
                    )
                )
                await client.send(
                    EventCompleted(
                        correlation_id=message.correlation_id,
                        status="completed",
                    )
                )
    finally:
        await client.close()


def main() -> None:
    """Run the command-line entry point.

    Returns:
        None.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", required=True)
    args = parser.parse_args()
    asyncio.run(run_noop(args.kind))


if __name__ == "__main__":
    main()
