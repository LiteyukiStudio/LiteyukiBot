# LiteyukiBot OneBot Adapter

`liteyukibot-v7-adapter-onebot` is a pure-Python protocol package for the
`liteyukibot-v7-runtime-adapter` child host. It implements OneBot v11 and v12
over HTTP Post, forward WebSocket, and reverse WebSocket transports without
NoneBot, Node, or a platform SDK.

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

The adapter maps supported OneBot messages into frozen LiteyukiBot messages and
executes `SendMessage` plus constrained `CallApi` actions. Set `kind` to
`onebot-v12` for v12; its default callback path is `/onebot/v12/http`. For a
WebSocket transport, set `transport = "forward_websocket"` with `ws_url`, or
`transport = "reverse_websocket"` with `ws_host`, `ws_port`, and `ws_path`.

## Development

Keep OneBot HTTP parsing, identity checks, and API conversion in this package;
the adapter host owns child lifecycle and the kernel owns portable models.
Run `uv run pytest packages/adapter-onebot/tests` and
`uv run python -m scripts.run_onebot_adapter_install` after changes.
