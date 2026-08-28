# LiteyukiBot OneBot Adapter

`liteyukibot-v7-adapter-onebot` is a pure-Python OneBot v11 client for
SnowLuma. It depends only on the kernel contracts and `websockets`; it does not
embed an HTTP listener or a framework runtime.

```bash
uv add liteyukibot-v7-kernel liteyukibot-v7-adapter-onebot
```

Configure one or more accounts in the application composition:

```toml
[onebot.v11.accounts.qq-main]
implementation = "snowluma"
self_id = "123456"
ws_url = "ws://127.0.0.1:3001/"
access_token = "onebot-token"
```

`OneBotService` owns all configured accounts, publishes supported private and
group message events to the kernel `EventBus`, and can be passed directly as
the backend of `ActionService`. It exposes only source-bound `message.send`
actions. Reply routes belong to their source account and are discarded on
disconnect.

## SnowLuma Notice

This package is an independently written OneBot protocol client. It does not
ship SnowLuma source code, native addons, or assets. SnowLuma is an external
project and LiteyukiBot is not affiliated with or endorsed by it; see the
[SnowLuma project](https://github.com/SnowLuma/SnowLuma) for its own terms and
license. Operators are responsible for the external service's terms, privacy,
and platform risks.

No SnowLuma code may be copied into this package under Liteyuki's license. If
future work adds third-party or derived files, keep the complete upstream
license and notices in a separate third-party notice and obtain any required
written permission before public distribution.

`ws://` URLs are accepted only for loopback endpoints; remote endpoints must
use `wss://`. When configured, the token is sent as
`Authorization: Bearer <access_token>`. WebSocket handshakes and action calls
have fixed 30-second timeouts; a healthy connected socket remains open and
reconnects after an actual disconnect.

## Development

Run `uv run pytest packages/adapter-onebot/tests` and
`uv run ruff check packages/adapter-onebot` after changes.
