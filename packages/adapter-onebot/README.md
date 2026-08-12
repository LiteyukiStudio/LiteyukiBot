# LiteyukiBot OneBot Adapter

`liteyukibot-v7-adapter-onebot` is a pure-Python protocol package for the
`liteyukibot-v7-runtime-adapter` child host. Its first release implements the
OneBot v11 HTTP Post event transport and HTTP API actions; it has no NoneBot,
Node, or platform-SDK dependency.

```bash
uv add liteyukibot-v7-runtime-adapter liteyukibot-v7-adapter-onebot
```

Configure an adapter instance in the independently installed adapter runtime:

```toml
[runtimes.platform]
kind = "adapter"

[runtimes.platform.options.adapters.qq-main]
kind = "onebot-v11"
bot_id = "123456"

[runtimes.platform.options.adapters.qq-main.config]
event_host = "127.0.0.1"
event_port = 5700
event_path = "/onebot/v11/http"
api_root = "http://127.0.0.1:5701"
access_token = "replace-with-the-onebot-http-token"
```

Point the OneBot implementation's HTTP Post callback at `event_path`. The
adapter verifies `Authorization: Bearer <access_token>` when configured and
requires a token for non-loopback listeners. It verifies matching `self_id` /
`X-Self-ID` values before forwarding an event.

The adapter accepts private and group message events, maps text, mentions,
replies, image/record/video media, and adapter-specific segments into frozen
LiteyukiBot messages, and executes `SendMessage` plus constrained `CallApi`
actions through the configured OneBot HTTP API root. OneBot v12 is intentionally
not part of this release.
