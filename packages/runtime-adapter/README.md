# LiteyukiBot Python Adapter Bridge

`liteyukibot-v7-runtime-adapter` is the mixed-grade Broker bridge for Python
platform adapters. Install this package with one or more separately published
driver distributions; the bridge intentionally includes no platform SDK or
protocol implementation.

Driver distributions publish entry points in `liteyukibot.adapters`. Each
driver owns its credentials, SDK objects, and network connections inside the
bridge process. The bridge exchanges only JSON-safe Broker events and the
portable `message.send` action.

```bash
uv add liteyukibot-v7-runtime-adapter
```

Configure the bridge in `broker.bridges`. Every configured bot must have one
exact `message.send` resource; `kind` selects the driver entry point while
`config` is opaque to the driver package:

```toml
[broker.bridges.adapter]
kind = "adapter"
token_secret = "broker.adapter.token"
access = "limited"
action_resources = [{ kind = "message.send", resource = "bot:adapter:123456" }]

[broker.bridges.adapter.options.adapters.qq-main]
kind = "qq"
bot_id = "123456"
config = { app_id = "...", access_token = { secret_ref = "qq-token" } }
```

Install `liteyukibot-v7-adapter-onebot` for the first real protocol entry
point, `onebot-v11`. It owns its HTTP Post callback listener and HTTP API
client, and needs no NoneBot or Node runtime. OneBot v12 and Satori remain
separately delivered packages.

## Development

Keep platform SDK objects inside driver packages and the bridge process. Run
`uv run pytest packages/runtime-adapter/tests` and
`uv run python -m scripts.run_adapter_runtime_install` after changes.
