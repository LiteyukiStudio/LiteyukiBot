# LiteyukiBot Python Adapter Runtime

`liteyukibot-v7-runtime-adapter` hosts Python platform adapters as supervised
LiteyukiBot child runtimes. Install this package with one or more separately
published adapter distributions; the base host intentionally includes no
platform SDK or protocol implementation.

Adapter distributions publish an entry point in `liteyukibot.adapters`. Each
adapter owns its credentials and SDK objects inside this child process and
exchanges only frozen LiteyukiBot Event and Action envelopes with the kernel.

```bash
uv add liteyukibot-v7-runtime-adapter
```

Runtime configuration names individual adapter instances. `kind` selects the
adapter entry point while `config` is opaque to the adapter package:

```toml
[runtimes.platform]
kind = "adapter"

[runtimes.platform.options.adapters.qq-main]
kind = "qq"
bot_id = "123456"
config = { app_id = "..." }
```

Install `liteyukibot-v7-adapter-onebot` for the first real protocol entry
point, `onebot-v11`. It owns its HTTP Post callback listener and HTTP API
client, and needs no NoneBot or Node runtime. OneBot v12 and Satori remain
separately delivered packages.
