# v6 Compatibility

- Specification version: `1`
- Applies to: the bounded v6 compatibility runtime shipped during v7 pre-release
- Compatibility: a migration aid, not a promise that all v6 extension behavior
  or framework objects survive unchanged

The v6 runtime retains its process-local message, rule, matcher, and reply
model within the child boundary. The kernel sees only portable Events and
Actions through the negotiated runtime protocol. Direct EventBus ownership,
cross-runtime framework-object exchange, and unbounded compatibility queues
are excluded.

NoneBot adapters normalize platform data before it crosses the boundary. The
custom runtime guide and `docs/migration-v6.md` describe supported migration
workflows and known limits.

## Evidence

Run the focused v6/runtime compatibility tests and the relevant separately
published runtime package installation verifier.
