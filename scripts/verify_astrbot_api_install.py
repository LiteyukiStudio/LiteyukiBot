"""Verify the independent AstrBot runtime API facade in an Alpha bundle."""

from __future__ import annotations

import argparse
import importlib.metadata


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version", required=True)
    args = parser.parse_args()
    observed = importlib.metadata.version("liteyukibot-v7-runtime-astrbot-api")
    if observed != args.expected_version:
        raise RuntimeError(f"AstrBot API version {observed!r} does not match {args.expected_version!r}")
    entry_points = {
        entry.name: entry.value
        for entry in importlib.metadata.entry_points(group="liteyukibot.runtime_api_proxies")
        if entry.name in {"astrbot.event", "astrbot.bot"}
    }
    expected = {
        "astrbot.event": "liteyukibot_runtime_astrbot_api:proxy_factory",
        "astrbot.bot": "liteyukibot_runtime_astrbot_api:bot_proxy_factory",
    }
    if entry_points != expected:
        raise RuntimeError(f"unexpected AstrBot API facade entry points: {entry_points!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
