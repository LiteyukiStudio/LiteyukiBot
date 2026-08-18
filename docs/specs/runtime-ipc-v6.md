# Broker Peer IPC v6

- Specification version: `6`
- Applies to: the B7 standalone broker peer contract, its stable NoneBot
  bridge, experimental AstrBot gateway, and in-process kernel peer.
- Compatibility: pre-stable hard cut. This contract is not interoperable with
  the former child-supervisor Runtime IPC v1 through v5 catalog.

## Scope And Status

The implemented B7 service is a standalone broker. It registers independent
bridge peers and routes their JSON-safe messages; it does not launch,
configure, supervise, or restart framework processes. Bridge processes own
their framework lifecycle and are discovered through the
`liteyukibot.bridges` entry-point group. Each entry point returns a validated
`BridgeDefinition(kind, grade, distribution, launch)`. The stable NoneBot
bridge and experimental AstrBot gateway are started with `liteyuki bridge run
<bridge-id>`; a support grade describes release qualification, not a different
wire protocol.

`kind = "kernel"` is a reserved in-process bridge, not an entry-point package
or a process launched with `liteyuki bridge run`. When present, `LiteyukiApp`
resolves its vault token and registers it as a normal `full` peer after the
native plugin manager has started. It must be unique, subscribe to at least one
topic, and declare no action-resource ownership. The standalone broker still
starts independently with `liteyuki broker run`.

The broker registry in `liteyuki.toml` is authoritative: a bridge must match
the configured access class, subscriptions, and action resources at
registration time. Bridge tokens are references into the local secret vault;
they are never sent through broker configuration or business payloads. The
former child-runtime hosts and `RuntimeSupervisor` protocol remain historical
implementation context, not this integration contract.

## LYIP v2 Peer Registration

LYIP v2 provides isolated directed `control` and `business` lanes. A bridge
uses the control lane to send `bridge.register` with its configured bridge ID,
instance token, and immutable manifest. The manifest declares an access class
(`full` or `limited`), event-topic subscriptions, and action-resource
declarations `(kind, resource_prefix)`.

The broker authenticates the token, binds the ZMQ peer identity, and returns a
broker-generated session ID in `bridge.registered`. Unknown bridges, invalid
tokens, already-live bridge IDs, identity rebinding, malformed messages, and
same-access resource conflicts are rejected. `bridge.unregister` requires the
active session ID and terminalizes outstanding deliveries for that peer.

Business frames are admitted only from a registered peer identity and must use
a session-bound stream ID of the form `bridge:<bridge-id>:<session-id>:...`.
Generation, lane, stream sequence, type ID, and frame lease remain validated
by the LYIP transport. Peers never communicate directly.

The control catalog is:

| Type ID | Message |
| ---: | --- |
| 600 | `bridge.register` |
| 601 | `bridge.registered` |
| 602 | `bridge.rejected` |
| 603 | `bridge.unregister` |
| 604 | `bridge.unregistered` |
| 605 | `broker.diagnostics.status` |
| 606 | `broker.diagnostics.list` |
| 607 | `broker.diagnostics.detail` |
| 608 | `broker.diagnostics.status.result` |
| 609 | `broker.diagnostics.list.result` |
| 610 | `broker.diagnostics.detail.result` |

Type IDs are scoped by LYIP lane. The control-plane diagnostic result at 610
therefore does not collide with the business-plane `event.ingress` type below.

### Read-only diagnostics

Diagnostics are authenticated independently of bridge registration with the
vault secret named by `broker.diagnostics_token_secret`; reusing a configured
bridge token is rejected. The requests and results above use the existing
`control` lane only, with the dedicated `broker:diagnostics:control` stream.
They never register a bridge or send a business frame.

`status` reports current bounded-ledger capacities and registered bridge IDs.
`list` accepts an opaque cursor and optional state/topic/source/target/failure
filters, and returns at most 500 redacted rows. `detail` returns one retained
event row plus its bounded lifecycle transitions. Diagnostics redact payloads,
credentials, raw action data, and raw source event IDs. This is an observation
surface only: it adds no persistence, replay, retry, delivery mutation, or
cross-process deadline contract.

## Business Catalog

Every business payload has `protocol: 6`, is JSON-safe, uses the `business`
lane, and must agree with its fixed LYIP type ID.

| Type ID | Direction | Message |
| ---: | --- | --- |
| 610 | bridge to broker | `event.ingress` |
| 611 | broker to bridge | `event.message` |
| 612 | bridge to broker | `event.accepted` |
| 613 | bridge to broker | `event.completed` |
| 614 | bridge to broker, then broker to owner | `action.request` |
| 615 | action owner to broker, then broker to caller | `action.result` |
| 616 | bridge to broker, then broker to owner | `tool.invoke` |
| 617 | Tool owner to broker, then broker to caller | `tool.result` |

`EventIngress` contains `source_event_id`, `topic`, `ordering_key`, and a
JSON-safe payload. It has no kernel event ID and cannot select recipients. The
broker creates the immutable `kernel_event_id`, attaches the registered source
bridge ID as provenance, and freezes the admitted event.

## Event Delivery And Ledger

The broker selects subscribers from registered manifests: `full` bridges
receive every topic and `limited` bridges receive only their declared topics.
Delivery is FIFO per `(source_bridge_id, ordering_key, target_bridge_id)` lane.
Only the head delivery is offered; its successor is offered only after the
head becomes terminal.

An `event.message` contains the admitted event, `delivery_id`, opaque
`lease_id`, `attempt: 1`, and positive `lease_ttl_ms`. The TTL is an advisory
remaining duration for the peer. The broker evaluates expiry on its own clock;
the wire contract deliberately carries no cross-process
`deadline_monotonic` value.

When a bridge issues an action through a delivery, the shared host runner also
uses that TTL as its local upper bound while awaiting the correlated result. It
does not reinterpret the value as a synchronized deadline; the broker remains
the authority for delivery expiry.

The delivery lifecycle is `pending -> offered -> accepted -> active ->`
`completed | failed | expired`. A bridge must acknowledge an offered delivery
with the matching lease; that acknowledgement advances it through accepted to
active. Only the target bridge may complete an active delivery. A failed,
expired, disconnected, or completed delivery is terminal. There is no retry,
persistence, replay, or exactly-once guarantee; `attempt` is fixed at `1`.

An event with no recipients settles immediately. Otherwise it settles after
all deliveries are terminal. Failed, expired, and disconnected deliveries are
retained as degraded terminal diagnostics alongside successful settled events.
The in-memory ledger defaults are:

| Setting | Default |
| --- | ---: |
| Active event capacity | `1024` |
| Terminal event capacity | `16384` |
| Terminal retention TTL | `3600` seconds |
| Delivery timeout | `30` seconds |

Active capacity exhaustion rejects new ingress. When an event settles, its
active delivery and FIFO indices are released. Terminal records, including
retained action results, are evicted when capacity or TTL requires it.

## Action Routing

A bridge may send `action.request` only while it owns an active event delivery
and presents that delivery's current lease in both the payload and LYIP frame.
The broker assigns `action_id`; callers must not provide one. Requests are
deduplicated within the event by target session, correlation ID, and canonical
JSON. Reusing the correlation ID with different content is rejected. The
selected owner alone may send the retained `action.result`. The broker copies
the request `correlation_id` into the result; an action owner does not choose
or rewrite it.

An action owner is resolved from matching `(kind, resource_prefix)` manifest
declarations. A `full` bridge class always takes priority over `limited`; within
the selected class the longest matching resource prefix wins. Ties at the same
class and prefix length are rejected as ambiguous. Registration also rejects
an exact resource declaration already owned by a live bridge in the same access
class. There is no fallback to a lower access class after a same-class conflict.

### B7 portable action

The first portable action is `message.send`. Its resource key is
`bot:<owner-bridge-id>:<bot-id>`, and its payload contains a protocol-neutral
`Message` plus either a conversation reference or a reply token. Generic
`CallApi`, message editing, and decorator-based function APIs are outside this
version of the contract.

### Alpha 2 Tool RPC

`tool.invoke` binds an active delivery and lease to a correlation ID, namespaced
Tool ID, JSON arguments, and `AuthorizationContext`. The broker assigns the
invocation ID. The declared Tool owner alone may return `tool.result`; results
contain JSON data or a stable error code with optional redacted JSON details.
Exception classes, messages, tracebacks, event payloads, and raw adapter data
never cross the wire. Reusing a correlation ID with different canonical JSON is
rejected; a completed result is retained and replayed without invoking the
owner again. Broker routing validates declaration shape and ownership, while
the caller and provider hosts validate their Draft 2020-12 schemas.

### B7 kernel peer dispatch

The kernel peer validates a delivered payload as an `EventEnvelope`, requires
its payload `id` to equal `source_event_id` and its `runtime_id` to equal the
authenticated source bridge, then replaces the envelope ID with the broker's
`kernel_event_id` before publishing it to the native EventBus. Native plugins
therefore see broker-issued event identities while retaining the source bridge
as the event runtime identity.

While that EventBus dispatch is active, the peer may translate a native
`SendMessage` action into the B7 portable `message.send` request. Its resource
key is resolved against the event's authenticated source bridge; the kernel
does not own action resources. `CallApi`, `EditMessage`, and locally injected
events have no B7 broker action path.

## Evidence

Run `uv run pytest tests/test_broker_peer.py tests/test_broker_business.py
tests/test_broker_routing.py tests/test_broker_kernel.py`. The executable definitions are under
`src/liteyukibot/broker/`; LYIP frame mechanics are specified by
[Runtime LYIP v2](runtime-lyip-v2.md).
