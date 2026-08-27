# SnowLuma OneBot v11 Profile

`liteyukibot-v7-adapter-onebot` implements an outbound OneBot v11 WebSocket
client profile for SnowLuma-compatible endpoints. OneBot v11 is the wire
protocol; SnowLuma is one implementation profile, not a protocol fork.

Each `[onebot.v11.accounts.<id>]` table requires:

- `implementation = "snowluma"`
- `self_id`
- `ws_url`
- optional `access_token`

The table key is the kernel `runtime_id`. Multiple accounts are independent.
Plain `ws://` endpoints must be loopback; remote endpoints require `wss://`.
Only private and group message events are accepted. Lifecycle, heartbeat,
notice, request and `message_sent` events are ignored.

The profile translates only text, mention, reply and image segments and
executes only source-bound `SendMessage` actions. Unknown segment kinds cause
the event to be discarded instead of widening the kernel model.

SnowLuma is an external project. LiteyukiBot is not affiliated with it and
does not bundle SnowLuma source, assets or implementation code. The local
reference checkout is used only to verify interoperable wire behavior.
See the [SnowLuma project](https://github.com/SnowLuma/SnowLuma) for its own
license and distribution terms.
