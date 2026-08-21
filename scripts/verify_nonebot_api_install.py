"""Verify the independent NoneBot runtime API facade in an Alpha bundle."""

from __future__ import annotations

import argparse
import importlib.metadata


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version", required=True)
    args = parser.parse_args()
    distribution = "liteyukibot-v7-runtime-nonebot-api"
    observed = importlib.metadata.version(distribution)
    if observed != args.expected_version:
        raise RuntimeError(f"NoneBot API version {observed!r} does not match {args.expected_version!r}")
    entry_points = {
        entry.name: entry.value
        for entry in importlib.metadata.entry_points(group="liteyukibot.runtime_api_proxies")
        if entry.name in {"nonebot.event", "nonebot.bot"}
    }
    expected = {
        "nonebot.event": "liteyukibot_runtime_nonebot_api:event_proxy_factory",
        "nonebot.bot": "liteyukibot_runtime_nonebot_api:bot_proxy_factory",
    }
    if entry_points != expected:
        raise RuntimeError(f"unexpected NoneBot API facade entry points: {entry_points!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
