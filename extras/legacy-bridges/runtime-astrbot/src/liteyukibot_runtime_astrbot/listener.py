"""Process-local handoff from AstrBot's public Star hook to the broker gateway."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

type EventPublisher = Callable[[Any], None]

_publisher: EventPublisher | None = None


def configure_publisher(publisher: EventPublisher | None) -> None:
    """Set the one gateway callback for this bridge process.

    Args:
        publisher: The publisher value used by the operation.

    Returns:
        None.
    """

    global _publisher
    _publisher = publisher


async def forward_native_event(event: Any) -> None:
    """Schedule broker observation without changing AstrBot's pipeline result.

    Args:
        event: Event associated with the operation.

    Returns:
        None.
    """

    publisher = _publisher
    if publisher is not None:
        publisher(event)
