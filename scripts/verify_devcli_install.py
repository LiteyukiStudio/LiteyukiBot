"""Verify the independent v7 DevCLI wheel in an isolated environment."""

from __future__ import annotations

import argparse
import importlib.metadata


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version", required=True)
    args = parser.parse_args()
    observed = importlib.metadata.version("liteyukibot-v7-devcli")
    if observed != args.expected_version:
        raise RuntimeError(f"DevCLI version {observed!r} does not match {args.expected_version!r}")
    from liteyuki_devcli.cli import build_parser

    if build_parser().prog != "liteyuki-dev":
        raise RuntimeError("DevCLI parser does not expose liteyuki-dev")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
