# ADR 0008: Integrate v6 Message Plugins Through Protocol v3

- Status: Accepted
- Date: 2026-08-09

## Context

ADR 0006 restores the process-local v6 message event, rule, matcher, and reply
intent APIs. ADRs 0005 and 0007 provide capability-gated core-to-child Events
and child-to-core Actions. The remaining compatibility boundary is the mapping
between those protocol-neutral envelopes and the supported v6 plugin API.

That mapping must preserve EventBus ordering, continue reading the child socket
while plugin handlers wait for Action results, and avoid reviving v6 Channel or
shared-memory transport.

## Decision

`LiteyukiApp` registers one internal EventBus handler when at least one enabled
`kind = "v6"` runtime is configured. It forwards message-bearing
`EventEnvelope` schema-v1 payloads to every v6 runtime concurrently through
`RuntimeSupervisor.dispatch_event()`. Events without a message remain valid but
are not forwarded by the application bridge. A runtime rejection or delivery
failure is reported as an isolated EventBus handler failure after every target
has been attempted.

The v6 child declares both `runtime.events.receive` and
`runtime.actions.send`. It keeps one receive pump and processes accepted Events
in bounded concurrent tasks. `max_concurrent_events` is a positive runtime
option with a default of 32. Exhausted capacity returns `overloaded`; an invalid
Event envelope returns `invalid`. A validated Event is acknowledged as
`accepted` only after matcher dispatch and every recorded reply attempt finish.

`RuntimeClient.execute_action()` owns child-side Action correlation and timeout
cleanup, but never reads the socket. The host remains the only caller of
`receive()`. That receive pump completes matching Action futures internally and
continues until it obtains a non-matching message for the host. Unmatched or
late Action results are exposed to the host. Duplicate in-flight correlation
identifiers are rejected before sending. EOF, protocol failure, and close fail
all pending Actions. The v6 reply timeout is the positive runtime option
`action_timeout_seconds`, defaulting to 10 seconds.

The `EventEnvelope` to `MessageEvent` mapping is:

| `MessageEvent` field | Source |
| --- | --- |
| `bot_id` | `EventEnvelope.bot_id` |
| `message_type` | `EventEnvelope.type` |
| `message` | JSON copies of normalized message segments |
| `raw_message` | normalized message plain text |
| `session_id` | conversation ID |
| `session_type` | conversation type |
| `user_id` | actor ID, or an empty string when absent |
| `data` | a deep JSON copy of `EventEnvelope.raw` |

No synthetic `Session` is attached. The standalone session models remain import
and construction compatibility because `thread` and `unknown` conversations
cannot be represented losslessly by the current `SceneType`.

Each reply intent becomes a separate `ActionEnvelope(SendMessage)` targeting
the source adapter runtime and bot. It preserves the source event ID,
conversation, and reply token. String replies become a portable text segment.
Mappings with a supported v7 segment type and object `data` are validated as
that segment. Unknown legacy types are retained inside an `adapter` segment as
`{"type": legacy_type, "data": legacy_data}`. Invalid mappings are logged and
skipped.

Reply Actions execute sequentially in recorded order. A matcher failure,
invalid reply, timeout, or rejected Action is logged and isolated from later
replies; it does not reclassify a validated Event as invalid. Shutdown, restart,
or disconnect cancels unfinished Event tasks and pending Actions.

## Consequences

Ordinary v6 message plugins using the supported matcher and `event.reply()` API
now run end to end inside the supervised compatibility process. Core and child
exchange only frozen JSON schemas; no Python framework or adapter object crosses
the process boundary.

Notices, requests, proactive v6 sends, adapter objects, Channel, shared memory,
the v6 process manager, hot reload, dependency installation, and arbitrary
message object emulation remain unsupported.
