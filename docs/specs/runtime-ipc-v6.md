# Runtime IPC v6

- Specification version: `6`
- Applies to: the current typed runtime message catalog transported by LYIP ABI
  v2.
- Compatibility: pre-stable hard cut. A runtime negotiates exactly protocol
  `6`; v1 through v5 are not accepted by the v7 kernel.

## Boundary

LYIP carries all child lifecycle and business messages over authenticated,
directed ZMQ lanes. Runtimes never communicate directly. The kernel is the
only event owner, route planner, delivery lessor, and action router.

`hello`, `welcome`, configuration, readiness, heartbeat, shutdown, controls,
management, actions, and agent tools retain their typed, JSON-safe model
boundary. The executable definitions are in
`src/liteyukibot/runtime/protocol.py`; this specification defines their public
meaning.

## Event Ownership

An ingress runtime sends:

```json
{"type":"event_ingress","source_event_id":"source-id","payload":{}}
```

It does not select routes or supply a kernel event identity. After validation,
the kernel admits the event into its bounded in-memory ledger and sends each
selected target an `event` message containing:

- `kernel_event_id` and immutable `source` provenance;
- `delivery_id`, target runtime ID, positive attempt number, and lease ID;
- an absolute monotonic deadline; and
- the frozen event payload, with an optional agent-tool catalog.

The target returns exactly one `event_accepted` for a delivery ID. A target
that has accepted the delivery later returns one `event_completed` with
`completed` or `failed`. Child-originated `action` and `agent_tool` messages
must include the active delivery ID; their lease is validated against the
kernel-owned delivery before a side effect is admitted.

## Route Semantics

Every configured route explicitly declares `policy` and `completion`:

- `required` failures contribute to the event's terminal failure; a
  `best_effort` failure is recorded but does not do so.
- `sync` makes the `runtime.routes` EventBus handler wait for the selected
  required delivery terminal result. `async` returns after delivery admission.

The ledger preserves FIFO delivery per
`(source runtime, bot, conversation, target runtime)` lane. It has no retry,
persistence, or cross-kernel replay behavior. A restart or shutdown can
terminalize in-flight work. Action deduplication is scoped to the event target,
correlation ID, and canonical JSON payload; an identical completed request
reuses its recorded result, while a conflicting reuse is rejected.

## Capability And Failure Rules

Capability declarations remain exact. A runtime must declare the capabilities
required by the message directions it uses. Disconnect, stale heartbeat,
invalid frame, lease mismatch, deadline expiry, or unsupported capability
becomes an explicit bounded delivery/runtime failure. No runtime receives
payloads, credentials, or arbitrary framework objects from another runtime.

## Evidence

Focused protocol, ledger, supervisor, and child-host tests must be updated in
the same pull request as further v6 wire changes. No compatibility claim is
made for v1 through v5 after this hard cut.
