# Runtime LYIP v2

- Specification version: `2`
- LYIP frame protocol marker: `1` (the v2 specification changes broker transport
  semantics and catalog contracts; it does not change the frame marker).
- Applies to: the implemented B5 standalone broker peer transport.
- Compatibility: pre-stable. LYIP v2 replaces the child-supervisor lifecycle
  description for new broker work; it does not make legacy runtime hosts broker
  peers automatically.

## Frame And Lanes

LYIP v2 is a directed, generation-scoped transport with separate `control` and
`business` lanes. Each frame carries its transport protocol marker, positive
generation, lane, fixed type ID, stream ID, per-stream sequence, lease ID, and
opaque payload. Send and receive reject generation or sequence mismatches; a
full lane does not advance its sender sequence.

Alpha11 limits opaque payloads to 8 MiB and encoded wire frames to 12 MiB.
Constructors and encoders reject oversized outbound content; decoders and ZMQ
sockets reject oversized inbound frames. Large binary objects belong in an
explicit bounded blob transport rather than the JSON/base64 frame path.

ZMQ uses separate ROUTER/DEALER sockets and high-water marks for the two lanes,
so business saturation cannot consume control capacity. Router identity plus
stream ID owns sequence state. A peer must use its broker-issued session-bound
business stream after control registration; broker business traffic is directed
to that identity and is never broadcast.

The control lane carries the protocol-6 bridge registration catalog. The
business lane carries the protocol-6 event and action catalog. Decoders reject
a message whose lane, fixed type ID, or payload discriminator does not agree.

## Scope

The B5 transport is host-initialized: `BrokerPeerServer` binds endpoints and
`BridgeClient` connects using supplied endpoints, identity, manifest, and
instance token. It does not define environment injection, process creation,
runtime readiness, heartbeats, restart policy, or a generic RPC surface.
Those are future integration concerns, not implied by the broker transport.

The native shared-memory primitive remains only a potential future transport
backend. It has no broker peer adapter and is not an implicit ZMQ replacement.

## Evidence

Run `uv run pytest tests/test_lyip.py tests/test_broker_peer.py
tests/test_broker_business.py`.
