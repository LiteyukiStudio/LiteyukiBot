# Broker Peer IPC v6

- Specification version: `6`
- Applies to: the implemented B5-1/B5-2/B5-3 standalone broker peer contract.
- Compatibility: pre-stable hard cut. This contract is not interoperable with
  the former child-supervisor Runtime IPC v1 through v5 catalog.

## Scope And Status

The implemented B5 foundation is a standalone broker service. It registers
independent bridge peers and routes their JSON-safe broker messages; it does
not launch, configure, supervise, or restart framework processes. Existing
child-runtime hosts and their `RuntimeSupervisor` protocol remain historical
implementation context, not the broker integration contract.

No production framework bridge, runtime configuration, native adapter, or
custom-runtime example is wired to this broker yet. Such integrations must
declare their manifests, lifecycle ownership, and failure behavior before this
specification may be treated as an integration migration guide.

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
selected owner alone may send the retained `action.result`.

An action owner is resolved from matching `(kind, resource_prefix)` manifest
declarations. A `full` bridge class always takes priority over `limited`; within
the selected class the longest matching resource prefix wins. Ties at the same
class and prefix length are rejected as ambiguous. Registration also rejects
an exact resource declaration already owned by a live bridge in the same access
class. There is no fallback to a lower access class after a same-class conflict.

## Evidence

Run `uv run pytest tests/test_broker_peer.py tests/test_broker_business.py
tests/test_broker_routing.py`. The executable definitions are under
`src/liteyukibot/broker/`; LYIP frame mechanics are specified by
[Runtime LYIP v2](runtime-lyip-v2.md).
