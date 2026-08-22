# LiteyukiBot AstrBot Gateway

`liteyukibot-v7-runtime-astrbot` owns one native AstrBot installation as an
`experimental` Liteyuki broker bridge. It is discovered through
`liteyukibot.bridges` and launched with `liteyuki bridge run <bridge-id>`.

AstrBot owns its platform adapters, local plugins, pipeline, and native output.
The gateway additionally publishes native messages as `message.created` and
owns bridge-scoped `message.send` actions. It never suppresses AstrBot's local
pipeline or its native replies.

With the separately installed `liteyukibot-v7-runtime-astrbot-api` package, the
bridge publishes the Alpha9 v1.1 `event.snapshot`, `event.send`,
`bot.snapshot`, and `bot.send` runtime APIs. Only portable JSON DTOs cross the
Broker boundary.

The configured bridge ID is passed into every translated event and snapshot.
Source event IDs use the shared `v1:` composite of bridge ID, platform/bot
scope, and upstream event ID. Ingress forwarding is bounded and best-effort:
temporary broker failures or queue overflow do not fail AstrBot's local
pipeline.

The `experimental` grade is declared by this package's bridge definition. The
gateway uses AstrBot's public extension surface and does not use the legacy
Liteyuki child-runtime protocol or runtime event routes.

The bridge workspace is `core.data_dir/bridges/<bridge-id>/astrbot` by default.
Set `broker.bridges.<bridge-id>.options.workspace` to a string path to use an
existing AstrBot workspace. No Liteyuki runtime state, plugin projection, or
child-runtime configuration is used.

## Development

Keep AstrBot APIs inside this package. Run `uv run pytest
packages/runtime-astrbot/tests` and `uv run python -m
scripts.run_astrbot_runtime_install` after changes.
