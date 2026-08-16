# LiteyukiBot NoneBot Runtime

`liteyukibot-v7-runtime-nonebot` hosts a NoneBot2 bridge for the standalone
Liteyuki broker. It is discovered through the `liteyukibot.bridges` entry-point
group and launched with `liteyuki bridge run <bridge-id>`.

Install the base host and one adapter family:

```bash
uv add "liteyukibot-v7-runtime-nonebot[onebot]"
```

The B5 bridge publishes normalized NoneBot messages as `message.created` and
owns only the portable `message.send` action. Its action resource keys are
bridge-scoped (`bot:<bridge-id>:<bot-id>`). NoneBot plugins, adapters, drivers,
and Bot objects remain local to the bridge process. Bridge-local NoneBot
initialization is configured under `broker.bridges.<id>.options` with
`config`, `adapters`, `plugins`, and `plugin_dirs`; generic `CallApi` and
message editing are not part of this bridge contract.

## Development

Keep NoneBot imports and adapter conversion in this package. Event forwarding
must not suppress NoneBot matcher dispatch. Run
`uv run pytest packages/runtime-nonebot/tests` and
`uv run python -m scripts.run_nonebot_runtime_install` after changes.
