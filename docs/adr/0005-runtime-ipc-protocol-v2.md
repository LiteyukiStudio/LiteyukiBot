# ADR 0005: Negotiate Runtime IPC Version 2 And Bidirectional Events

- Status: Accepted
- Date: 2026-08-09

## Context

Protocol v1 only sends events from a child runtime to the core. Useful
LiteyukiBot v6 message-plugin compatibility requires the core to deliver a
normalized event to a supervised compatibility runtime without adding a second
transport or exposing framework objects across the process boundary.

ADR 0002 freezes every v1 message shape and direction. The existing `hello` and
`welcome` messages already carry a protocol number, so a new direction must be
selected explicitly through those fields.

## Decision

The supervisor accepts runtime protocol versions 1 and 2. A child requests one
exact version in `hello.protocol`; the supervisor confirms that same version in
`welcome.protocol`. A different confirmation, an unsupported version, or an
invalid handshake order is fatal to the connection. Children do not retry with
a lower version because reconnect and restart policy remain supervisor-owned.

Version 1 retains the complete contract in ADR 0002. Version 2 retains the same
framing, authentication, frame limit, JSON validation, message fields, and
Action directions. It changes only the allowed directions of the existing event
request/response pair:

| Type | v1 direction | v2 direction |
| --- | --- | --- |
| `event` | child -> core | either direction |
| `event_accepted` | core -> child | either direction |

A v2 child opts into core-to-child events by including the exact capability
`runtime.events.receive` in `ready.capabilities`. Capabilities are scoped to the
current authenticated connection and are cleared on disconnect.

`RuntimeSupervisor.dispatch_event()` sends an `event` only when the runtime is
READY, negotiated v2, and declared that capability. It validates the payload as
JSON-safe, requires a unique in-flight correlation identifier, and waits for the
matching `event_accepted`. The existing `accepted`, `overloaded`, and `invalid`
statuses and optional detail retain their v1 meanings.

Timeout removes the pending request. Disconnect fails it with
`ConnectionError`. Duplicate in-flight correlation identifiers are rejected
before another frame is sent. An unmatched or late `event_accepted` has no
effect.

Child-originated Event handling runs in tracked work outside the connection
reader. This keeps later Action responses and heartbeats routable when an Event
handler waits for an Action result on the same runtime connection. The
supervisor bounds that tracked work with each runtime's `max_inbound_events`
limit (default `100`), replying `overloaded` before creating a task when full.
A duplicate in-flight child Event correlation ID receives `invalid`, and
disconnect cancels unfinished Event work.

## Consequences

V1 and v2 children may connect to the same supervisor concurrently. Existing v1
children remain valid but cannot receive core events, even if they advertise the
v2 capability string.

Framework runtimes own conversion from a received `EventEnvelope` schema-v1
payload to their local matcher/event model. This decision does not add that
conversion, change EventBus ordering, or make NoneBot and v6 runtimes advertise
event reception automatically.

Future protocol changes must use a new negotiated version or a capability whose
semantics are fully expressible by the selected protocol version.
