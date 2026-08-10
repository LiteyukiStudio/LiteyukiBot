"""Run the LiteyukiBot v6 compatibility host under the supervisor."""

from __future__ import annotations

import asyncio

from .host import run


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
