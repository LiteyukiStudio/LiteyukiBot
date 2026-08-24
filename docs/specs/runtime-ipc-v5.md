# Runtime IPC v5 (Historical)

- Specification version: `5`
- Applies to: superseded child-supervisor typed wire models and compatibility
  semantics.
- Compatibility: historical. It is not interoperable with the standalone
  Broker peer protocol specified by [Broker Peer IPC v7](runtime-ipc-v7.md).

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
bounded completion. v4+ deliveries carry immutable trace provenance. Alpha6
removes the former Agent Tool request/response and Agent history control models
from the executable v5 catalog. Agent functionality now uses the Broker Peer
IPC v7 bridge Tool and control messages.

Actions remain kernel-to-child and are correlated with their original Event
delivery. Management results are structured and redacted. This document
remains a record of the superseded child-runtime wire format; it must not be
used to implement a new Agent integration.

## Evidence

The executable implementation and its conformance tests have been removed.
The current Broker transport is specified by `runtime-lyip-v2.md`.
