# LiteyukiBot NoneBot Runtime

`liteyukibot-v7-runtime-nonebot` hosts a NoneBot2 bridge for the standalone
Liteyuki broker. It is discovered through the `liteyukibot.bridges` entry-point
group as a `stable` bridge definition and launched with `liteyuki bridge run
<bridge-id>`.

Install the base host and one adapter family:

```bash
uv add "liteyukibot-v7-runtime-nonebot[onebot]"
```

The B7 bridge publishes normalized NoneBot messages as `message.created` and
owns only the portable `message.send` action. Its action resource keys are
bridge-scoped (`bot:<bridge-id>:<bot-id>`). NoneBot plugins, adapters, drivers,
and Bot objects remain local to the bridge process. Bridge-local NoneBot
initialization is configured under `broker.bridges.<id>.options` with
`config`, `adapters`, `plugins`, and `plugin_dirs`; generic `CallApi` and
message editing are not part of this bridge contract.

Alpha12 plugin-store deployments use immutable managed generations. The kernel
creates an isolated environment, materializes the complete NoneBot load plan,
and runs a real NoneBot initialization probe before activation. The daemon then
restarts the bridge with `LITEYUKI_PLUGIN_GENERATION` pointing at that
generation. Managed generations reject `plugins` and `plugin_dirs` in bridge
configuration so manually configured and store-managed plugins cannot be
loaded together accidentally. A failed candidate startup restores the previous
generation; garbage collection retains only the active and previous
generations and their referenced artifacts.

The package implements the neutral `ManagedFacetInstaller` and
`ManagedFacetProbe` contracts from `liteyukibot.bridge_contracts`. It consumes
only verified archive extraction plus the runtime kind, artifact digests, and
load plan needed for materialization; Broker does not own the plugin store.

With the separately installed `liteyukibot-v7-runtime-nonebot-api` package, the
bridge publishes the Alpha10.1 v1.2 `event.snapshot`, `event.send`,
`bot.snapshot`, and `bot.send` runtime APIs. Only kernel-owned portable JSON
DTOs cross the Broker boundary; NoneBot and adapter objects remain local to
this process.

The configured bridge ID is passed into every normalized event. Source event
IDs use the shared `v1:` composite of bridge ID, adapter/bot scope, and upstream
event ID. Ingress forwarding is bounded and best-effort: temporary broker
failures or queue overflow do not fail NoneBot's local event pipeline.

The `stable` grade is package metadata on the bridge definition, not a promise
that the broker wire protocol accepts framework-specific actions. NoneBot SDK
objects and credentials remain in this package; the kernel never imports them.

## Development

Keep NoneBot imports and adapter conversion in this package. Event forwarding
must not suppress NoneBot matcher dispatch. Run
`uv run pytest packages/runtime-nonebot/tests` and
`uv run python -m scripts.run_nonebot_runtime_install` after changes. Plugin
generation changes additionally require `uv run python
scripts/run_nonebot_plugin_e2e.py` against built workspace wheels.
