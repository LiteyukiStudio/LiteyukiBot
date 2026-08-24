# Broker peer development

New cross-process integrations target the standalone Broker peer contract.
Run the Broker with `liteyuki broker run` and a configured bridge with
`liteyuki bridge run <bridge-id>`. Bridge launchers are discovered from
`liteyukibot.bridges`.

A bridge receives its configured ID and vault-resolved token from its launcher,
constructs `BridgeClient`, and registers a `BridgeManifest` using the protocol-7
catalog described by [Broker Peer IPC v7](../specs/runtime-ipc-v7.md).
Registration declares:

- `full` or `limited` access;
- literal or single-segment wildcard topic subscriptions;
- action `(kind, resource)` or `(kind, resource_prefix)` ownership;
- optional Runtime API and tool declarations.

The Broker assigns the session ID and kernel event ID. A bridge must not create
either value, select event recipients, set an absolute monotonic deadline, or
connect directly to another bridge.

`kind = "kernel"` is reserved for LiteyukiApp's in-process full peer. It is not
a `liteyukibot.bridges` entry point, cannot own action resources, and must not
be launched with `liteyuki bridge run`.

For each `EventMessage`, retain its opaque lease and respond once with
`EventAccepted`, then with `EventCompleted` after the active delivery reaches a
terminal outcome. `lease_ttl_ms` is advisory; the Broker evaluates its timeout.
An action request is valid only while the bridge owns the active delivery and
presents the current lease. There is no execution replay protocol.

The Broker does not provide framework environment bootstrap, heartbeats,
persistence, or child-process restart policy. Configuration lives under
`broker.bridges`; the owning bridge package supplies framework startup and
shutdown through `BridgeDefinition(kind, grade, distribution, launch)`.

Keep framework SDK objects, credentials, connections, and event/action
conversion in the package that owns the framework. The kernel must not import
the framework SDK. Document lifecycle behavior and test against the real peer
contract before raising a bridge's support grade.

The installable [Broker peer example](../../examples/broker-peer) exercises
registration, ingress, a lease-bound Runtime API call, completion, unregister,
and shutdown over the real ZMQ transport. Use it as a protocol smoke test, not
as a framework adapter template.

## Runtime API facade

Native and Cordis extensions share kernel-owned `RuntimeRequirement` and
`@runtime` declarations. This Runtime API is a capability-routed Broker facade;
it is unrelated to the retired child Runtime package.

```python
from typing import Any

from liteyukibot import runtime


@runtime("astrbot", api="event", version="^1.2", optional=True, as_="astrbot")
async def handler(event: object, *, astrbot: Any) -> None:
    if not astrbot.available:
        return
    snapshot = getattr(astrbot, "snapshot", None)
    if callable(snapshot):
        await snapshot()
```

The extension manifest must contain the same provider kind, API, version,
optional flag, and operation list. Use `bridge_id` on both declarations when
targeting one configured bridge. See
[`runtime-api-conformance.md`](runtime-api-conformance.md) for the operation
catalog, fingerprint rule, provider checklist, and failure behavior.

The v6 and MoFox compatibility packages are limited Broker bridges. They are
not `liteyukibot.runtime` entry points and do not use the retired supervised
child lifecycle.
