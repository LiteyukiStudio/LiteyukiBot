# ADR 0007: Negotiate Runtime IPC Version 3 And Bidirectional Actions

- Status: Accepted
- Date: 2026-08-09

## Context

Protocol v2 permits the core to deliver events to a compatibility runtime, but
retains the protocol-v1 Action direction from core to child. LiteyukiBot v6
message handlers record reply intents inside the compatibility process, so they
need a versioned way to submit protocol-neutral Actions back to the core without
using shared memory or overloading `event_accepted`.

The existing `action` and `action_result` messages already provide correlation,
JSON validation, and deterministic success or failure. A new message shape is
not required, but the additional direction must not be enabled accidentally for
older children.

## Decision

The supervisor accepts runtime protocol versions 1, 2, and 3. Negotiation keeps
the exact-version rules in ADR 0005. Version 3 retains the framing,
authentication, limits, schemas, and bidirectional Event behavior of version 2.
It additionally changes the allowed directions of the existing Action pair:

| Type | v1/v2 direction | v3 direction |
| --- | --- | --- |
| `action` | core -> child | either direction |
| `action_result` | child -> core | either direction |

A v3 child opts into child-to-core Actions with the exact READY capability
`runtime.actions.send`. The same capability on a v1 or v2 connection has no
effect. A missing capability, older protocol, unavailable core Action sink, or
duplicate in-flight correlation identifier receives a correlated failed
`action_result`; it does not terminate the connection.

The supervisor validates direction and capability, tracks in-flight
child-originated requests, and owns the wire response. An injected Action sink
validates and routes the payload. Sink work runs outside the connection receive
loop so heartbeats and later frames continue to be read. Sink exceptions are
logged and converted to a deterministic `core action sink failed` response.
Disconnect cancels unfinished sink tasks.

`LiteyukiApp` validates the payload as the frozen `ActionEnvelope` schema and
uses the existing `ActionService`. The Action envelope's `runtime_id` names the
adapter runtime that owns the bot; it need not equal the compatibility runtime
that submitted the request. Routing an Action back to its source runtime is
rejected because synchronous self-routing would wait on the same connection and
form a protocol loop.

The serialized `ActionResult` is returned in `action_result.data`. The wire
`ok` flag mirrors `ActionResult.success`, and a failed result also exposes its
message through `action_result.error`.

## Consequences

V1 and v2 children remain valid and retain their previous Action direction.
Protocol v3 children may receive core events under `runtime.events.receive` and
submit Actions under `runtime.actions.send`; the capabilities are independent.

This decision does not add the v6 receive loop, matcher dispatch, reply-intent
translation, or a child-side concurrent response router. Those integrations can
now be implemented without another core protocol or Action-routing change.
