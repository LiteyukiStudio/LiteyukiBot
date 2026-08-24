# LiteyukiBot v7 v6 Runtime

> Retired source snapshot. This project is not part of the LiteyukiBot v7.0.0
> workspace, release, CI, or support surface. See `../README.md`.

`liteyukibot-v7-runtime-v6` hosts bounded LiteyukiBot v6 plugin compatibility
in an experimental limited LiteyukiBot v7 Broker bridge. It provides the
`liteyuki` compatibility namespace only when this bridge package is installed.

It loads only configured `liteyukibot.v6_plugins` entry points and supports the
documented v6 lifecycle, message matcher, session, and ordered reply surface.
It does not restore v6 channels, shared-memory transport, adapter objects,
legacy module/directory loading, `ActionEnvelope`, or process-manager APIs.

## Development

Keep legacy session and matcher compatibility process-local. Do not recreate
shared-memory or adapter-object APIs. Configure the package under
`broker.bridges`; run `uv run pytest packages/runtime-v6/tests` and
`uv run python -m scripts.run_v6_runtime_install` after changes.
