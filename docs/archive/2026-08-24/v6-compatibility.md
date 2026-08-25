# v6 Compatibility

> Historical pre-release specification. This contract is not part of the
> LiteyukiBot v7.0.0 mainline support surface.

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

NoneBot adapters normalized platform data before it crossed the boundary. The
adjacent `v6-plugin-migration.md` file records the retired migration workflow
and known limits.

## Evidence

The former focused tests and installation verifier are retained with the source
snapshot under `extras/legacy-bridges`.
