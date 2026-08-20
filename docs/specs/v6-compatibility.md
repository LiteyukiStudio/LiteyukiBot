# v6 Compatibility

- Specification version: `1`
- Applies to: the experimental limited v6 Broker bridge shipped during v7 pre-release
- Compatibility: a migration aid, not a promise that all v6 extension behavior
  or framework objects survive unchanged

The v6 bridge retains its process-local message, rule, matcher, and reply
model within its own process. The broker delivers only portable EventEnvelope
payloads and accepts only lease-bound `message.send` requests. Direct EventBus
ownership, cross-runtime framework-object exchange, and unbounded
compatibility queues are excluded.

The bridge loads only explicitly selected `liteyukibot.v6_plugins` entry
points. Legacy module paths, plugin directories, managed generations, and
historical runtime configuration are migration errors. Topic subscriptions
use dot-separated patterns where `*` matches exactly one complete segment.

NoneBot adapters normalize platform data before it crosses the boundary. The
custom runtime guide and `docs/migration-v6.md` describe supported migration
workflows and known limits.

## Evidence

Run the focused v6/runtime compatibility tests and the relevant separately
published runtime package installation verifier.
