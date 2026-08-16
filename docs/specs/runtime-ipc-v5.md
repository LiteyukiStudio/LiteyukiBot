# Runtime IPC v5 (Historical)

- Specification version: `5`
- Applies to: superseded child-supervisor typed wire models and compatibility
  semantics.
- Compatibility: historical. It is not interoperable with the standalone
  broker peer protocol specified by [Broker Peer IPC v6](runtime-ipc-v6.md).

## Transport And Handshake

The former kernel loopback TCP endpoint and length-prefixed JSON framing were
retired. This document records the old `hello`, `welcome`, configuration,
readiness, lifecycle, controls, events, actions, agent tools, and management
catalog. It must not be used to implement a new broker peer.

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
`src/liteyukibot/runtime/protocol.py`; that source and its protocol tests are
the executable shape of this pre-stable specification.

## Evidence

Run `uv run pytest tests/test_runtime_v7.py tests/test_runtime_client_v7.py`.
The implemented broker transport is specified by `runtime-lyip-v2.md`.
