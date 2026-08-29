# LiteyukiBot OneBot Adapter

`liteyukibot-v7-adapter-onebot` is a pure-Python OneBot v11 client for
SnowLuma. It depends only on the kernel contracts and `websockets`; it does not
embed an HTTP listener or a framework runtime.

Alpha15 is distributed as a signed GitHub Release bundle rather than through
PyPI. Install the root bundle and use the workspace's pinned adapter package;
do not add this Alpha15 package from a public package index.

Configure one or more accounts in the application composition:

```toml
[onebot.v11.accounts.qq-main]
implementation = "snowluma"
self_id = "123456"
ws_url = "ws://127.0.0.1:3001/"
access_token = "onebot-token"
```

`OneBotService` owns all configured accounts, publishes private/group messages,
notices, and friend/group requests to the kernel `EventBus`, and can be passed
directly as the backend of `ActionService`. Sending, deletion, request
responses, and adapter extensions remain bound to their source event and
account. Reply routes belong to their source account and are discarded on
disconnect.
Inbound events are retained under both a 1024-event queue limit and a 16 MiB
weighted byte budget. Account shutdown drains queued events and exposes
unfinished transport cleanup in status.

The profile translates text, mention, reply, image, audio/record, video, file,
and face/emoji segments. Legacy string messages parse the same CQ forms with
v11 entity escaping. Other valid CQ codes and segment kinds retain their native
type and data in an explicit OneBot-targeted adapter segment. Private messages
with `sub_type = "group"` retain `sender.group_id` as the conversation parent
and send replies with `send_private_msg.group_id`.

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
reconnects after an actual disconnect with bounded backoff. Runtime status
exposes connection health and queue counters without credentials or payloads.

## Development

Run `uv run pytest packages/adapter-onebot/tests` and
`uv run ruff check packages/adapter-onebot` after changes.
