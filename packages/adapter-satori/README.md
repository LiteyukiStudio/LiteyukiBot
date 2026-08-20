# LiteyukiBot Satori Adapter

`liteyukibot-v7-adapter-satori` connects the Python adapter Broker bridge to an
external Satori v1 service. It is an external gateway client: LiteyukiBot does
not embed a Satori server and does not require Node.js.

```toml
[broker.bridges.adapter]
kind = "adapter"
token_secret = "broker.adapter.token"
access = "limited"
action_resources = [{ kind = "message.send", resource = "bot:adapter:discord:bot" }]

[broker.bridges.adapter.options.adapters.satori-main]
kind = "satori"
bot_id = "discord:bot"

[broker.bridges.adapter.options.adapters.satori-main.config]
gateway_url = "ws://127.0.0.1:5500/v1/events"
api_root = "http://127.0.0.1:5500/v1"
access_token = { secret_ref = "satori-token" }
```

The adapter implements `IDENTIFY`, `READY`, `PING/PONG`, event resume by
sequence number, reconnect, and `message.create`. Satori elements remain
structured Liteyuki segments; elements that cannot be mapped remain adapter
segments. Only the Broker `message.send` action is exposed.
