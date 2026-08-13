# LiteyukiBot AstrBot Runtime

This AGPL-3.0-or-later package runs AstrBot as an agent-only headless runtime.
It owns an AstrBot workspace below its assigned runtime state directory and
does not start AstrBot platform adapters or its dashboard.

## Development

Keep AstrBot APIs and projected plugin loading inside this child host. Run
`uv run pytest packages/runtime-astrbot/tests` and
`uv run python -m scripts.run_astrbot_runtime_install` after changes.
