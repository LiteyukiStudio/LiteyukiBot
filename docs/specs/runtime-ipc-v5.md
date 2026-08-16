# Runtime IPC v5 (Historical)

- Specification version: `5`
- Applies to: superseded typed wire models and compatibility semantics.
- Compatibility: superseded by Runtime IPC v6. Its former length-prefixed TCP
  child transport is removed and must not be restored as a fallback.

## Transport And Handshake

The former kernel loopback TCP endpoint and length-prefixed JSON framing are
retired. `hello`, `welcome`, configuration, readiness, lifecycle, controls,
events, actions, agent tools, and management messages retain their typed
catalog and capability semantics, but travel through the LYIP v1 codec and
directed ZMQ lanes. Runtime-to-runtime transport remains forbidden.

The child declares capabilities in `ready`. The supervisor treats disconnect,
timeout, stale heartbeat, invalid frame, and unsupported capability as bounded
runtime failures. Runtime health exposes liveness and bounded counters only;
it never exposes payloads, child credentials, environment values, or secrets.

## Delivery And Controls

Core-to-child Events receive an accepted/overloaded/invalid response and have
bounded completion. v4+ deliveries carry immutable trace provenance. v5 adds
narrow, capability-gated kernel controls and child-originated requests for one
registered kernel management command. Neither direction is a generic RPC,
shell, or arbitrary command channel.

Actions remain kernel-to-child and are correlated with their original Event
delivery. Control and management results are structured and redacted. The
exact Pydantic wire models, discriminators, and frame validation live in
`src/liteyukibot/runtime/protocol.py`; v5 is retained only as historical
context. The current protocol is specified by
[Runtime IPC v6](runtime-ipc-v6.md).

## Evidence

Do not use this document to implement a new runtime. The active lifecycle
transport is specified by `runtime-lyip-v1.md`.
