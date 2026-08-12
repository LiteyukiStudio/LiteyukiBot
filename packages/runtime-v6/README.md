# LiteyukiBot v7 v6 Runtime

`liteyukibot-v7-runtime-v6` hosts bounded LiteyukiBot v6 plugin compatibility
in a supervised LiteyukiBot v7 child process. It provides the `liteyuki`
compatibility namespace only when this runtime package is installed.

It supports the documented v6 plugin, lifecycle, message matcher, and reply
bridge surfaces. It does not restore v6 channels, shared-memory transport,
adapter objects, or process-manager APIs.

## Development

Keep legacy session and matcher compatibility process-local. Do not recreate
shared-memory or adapter-object APIs. Run `uv run pytest packages/runtime-v6/tests`
and `uv run python -m scripts.run_v6_runtime_install` after changes.
