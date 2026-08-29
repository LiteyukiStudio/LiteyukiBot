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
Private and group messages, notices, and friend/group requests are published.
`message_sent`, lifecycle, and heartbeat events remain transport-internal and
are not sent to Cordis. Published events must carry a finite numeric `time`;
malformed events are discarded by the adapter.

The application status includes one account entry per configured runtime with
connection state, pending call count, queued event count and bytes, reconnect
count, and the last exception type. It never includes access tokens or message
payloads. The account event queue has both a count limit and a weighted byte
budget; shutdown drains queued events before reporting cleanup complete.
The service remains available while an account is reconnecting and reports a
`degraded` state until all configured accounts are connected.

Event delivery callbacks are async-only and are rejected during client
construction when synchronous callbacks are supplied. Account shutdown
rejects new calls before clearing the connection. If an already admitted
transport send ignores cancellation, connection close is deferred until its
send gate is released and the lingering task remains visible in status. The
client reports `cleanup_pending` or `failed` while cleanup is incomplete and
only reports `stopped` after queued events, transport close, and background
tasks have been released.

The profile maps text, mention, reply, image, record/audio, video, file, and
face/emoji segments to portable kernel types. Array messages use standard v11
segment objects and legacy strings parse CQ forms with v11 entity escaping.
Other valid segment or CQ types use an explicit `adapter` segment that retains
their native type and JSON-safe data.

Notice types are published as `notice.<notice_type>[.<sub_type>]`; requests use
`request.<request_type>[.<sub_type>]`. Event-specific IDs and values are
available through `EventEnvelope.details`, with top-level `*_id` values
normalized to strings. Group events use a group conversation, direct events
use a private conversation, and account-only notices have no synthetic
conversation.

Source-bound actions support sending, deleting messages, responding to the
source friend/group request, and calling remaining SnowLuma APIs through
`AdapterAction`. The extension path rejects the send/delete/request APIs that
already have portable actions. All paths require matching event, runtime, bot,
adapter, and configured account identities.

For a private event with `sub_type = "group"`, the adapter reads the source
group from `sender.group_id` (or the top-level `group_id` fallback) into
`ConversationRef.parent_id`. A reply to that conversation sends
`send_private_msg` with both `user_id` and `group_id`, preserving the temporary
session instead of turning it into an ordinary friend message.

SnowLuma is an external project. LiteyukiBot is not affiliated with it and
does not bundle SnowLuma source, assets or implementation code. The local
reference checkout is used only to verify interoperable wire behavior.
See the [SnowLuma project](https://github.com/SnowLuma/SnowLuma) for its own
license and distribution terms.
