# Runtime LYIP v1

- Specification version: `1`
- Applies to: the Beta3 supervised child-runtime lifecycle, transport-neutral
  LYIP frame, ZMQ backend, and typed runtime message codec.
- Compatibility: pre-stable. Every supervised child uses LYIP v1. The former
  v5 length-prefixed TCP lifecycle is historical and is not a fallback.

## Frame And Ordering

Every frame has protocol `1`, a positive kernel generation, lane, fixed type
ID, stream ID, per-stream sequence, lease ID, and opaque bytes. Send and
receive both reject generation or sequence mismatches. A full lane must not
advance the sender sequence.

Business and control are isolated lanes. The ZMQ implementation uses separate
ROUTER/DEALER sockets and HWM values for each lane, so business saturation
cannot consume control capacity. ROUTER identity plus stream ID owns sequence
state; frames are never broadcast between runtimes.

Each launch receives a new loopback endpoint pair, positive generation, lease,
and opaque DEALER identity. A child sends `runtime:<runtime-id>:<lane>` and
accepts only `kernel:<runtime-id>:<lane>` on the matching lane. The kernel
binds identity only after the authenticated control-lane `hello`; changed
identity, generation, lease, lane, or stream is rejected. Restarting rotates
all of these session values.

## Runtime Codec

`runtime.lyip` assigns each existing typed runtime wire message a fixed type
ID and selects its lane. Lifecycle, control, and management messages use the
control lane. Event, action, and agent-tool messages use the business lane.
The codec verifies that frame type ID, decoded discriminator, and lane agree.

## Backend Availability

The active lifecycle backend is ZMQ. The native package exposes an ABI and
shared-memory SPSC ring primitive, but no SHM LYIP transport adapter yet; it
therefore cannot be selected for a child lifecycle. The ring remains an
optional native foundation, not an implicit transport switch.

## Evidence

Run `uv run pytest tests/test_lyip.py tests/test_runtime_lyip.py
tests/test_runtime_client_v7.py tests/test_runtime_v7.py`.
