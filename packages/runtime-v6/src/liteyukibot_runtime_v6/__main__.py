"""Reject the removed legacy child-runtime launch path."""

from __future__ import annotations


def main() -> None:
    """Run the command-line entry point.

    Returns:
        None.
    """
    raise SystemExit(
        "migration_required: liteyukibot-v7-runtime-v6 is a broker bridge; "
        "configure it under broker.bridges and use 'liteyuki bridge run'"
    )


if __name__ == "__main__":
    main()
