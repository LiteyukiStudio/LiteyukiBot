# LiteyukiBot Satori Adapter

`liteyukibot-v7-adapter-satori` connects the Python adapter runtime to an
external Satori v1 service. It is an external gateway client: LiteyukiBot does
not embed a Satori server and does not require Node.js.

```toml
[runtimes.platform]
kind = "adapter"

[runtimes.platform.options.adapters.satori-main]
kind = "satori"
bot_id = "discord:bot"

[runtimes.platform.options.adapters.satori-main.config]
gateway_url = "ws://127.0.0.1:5500/v1/events"
api_root = "http://127.0.0.1:5500/v1"
access_token = "replace-with-a-vault-backed-token"
```

The adapter implements `IDENTIFY`, `READY`, `PING/PONG`, event resume by
sequence number, reconnect, `message.create`, and `message.update`. Satori
elements remain structured Liteyuki segments; elements that cannot be mapped
remain adapter segments.
