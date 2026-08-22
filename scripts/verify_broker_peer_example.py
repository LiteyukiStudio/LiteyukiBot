"""Run the installable B7 broker-peer example from an isolated wheel environment."""

from __future__ import annotations

import asyncio

from liteyukibot_example_broker_peer import run_demo


def main() -> int:
    result = asyncio.run(run_demo())
    expected = {"runtime_result": "hello", "shutdown": "true"}
    if any(result.get(key) != value for key, value in expected.items()):
        raise RuntimeError(f"unexpected B7 example result: {result!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
