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
    if not importlib.metadata.entry_points(group="liteyukibot.runtime_api_proxies"):
        raise RuntimeError("AstrBot API facade did not publish its runtime API entry point")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
