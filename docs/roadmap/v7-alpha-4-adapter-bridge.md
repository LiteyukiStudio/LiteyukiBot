# v7 Alpha 4: Generic Adapter Broker Bridge

> **Planned implementation contract.** This document records the agreed Alpha 4
> boundary. It does not claim that the adapter bridge, driver packages, or
> release assets are implemented.

Alpha 4 migrates the generic Python adapter host and the OneBot/Satori drivers
from the historical runtime child boundary to an independently launched broker
bridge. It starts only after Alpha 3 is merged.

## Release boundary

The lockstep set advances to `7.0.0a4` under tag `v7.0.0a4`. The signed GitHub
Release rebuilds every independent first-party package for this Alpha and adds
`liteyukibot-v7-adapter-onebot==0.2.0a1` and
`liteyukibot-v7-adapter-satori==0.2.0a1` as independent assets pinned to the
Alpha 4 kernel and adapter bridge host. The Alpha GitHub Release, manifest,
Sigstore proof, and no-PyPI rule remain unchanged.

## Shared adapter bridge

`liteyukibot-v7-runtime-adapter` becomes the `adapter` entry in
`liteyukibot.bridges`; it is not a `liteyukibot.runtimes` child and does not
use `RuntimeClient`. One bridge process may load multiple configured adapter
instances from `broker.bridges.<id>.options.adapters`.

The driver entry-point group remains separate. Each driver declaration contains
its kind, distribution, support grade, and connection factory. OneBot v11 is
`stable`; OneBot v12 and Satori are `experimental`. The shared bridge is
`mixed`, and diagnostics/WebUI must report each configured instance's grade.

The root kernel imports neither adapter drivers nor platform SDKs. All platform
connections, listener sockets, SDK values, reply-route state, and credentials
remain inside the adapter bridge process.

## Ingress, actions, and configuration

Drivers send JSON-safe `EventIngress` values only. The portable, platform-
prefixed message topics are:

- `onebot.v11.message.private` and `onebot.v11.message.group`;
- `onebot.v12.message.private`, `onebot.v12.message.group`, and
  `onebot.v12.message.channel`;
- `satori.message.private` and `satori.message.channel`.

Platform subtypes and raw JSON remain in the normalized event payload. The
only portable cross-bridge action is `message.send`. `CallApi` and
`EditMessage` are removed from the adapter bridge boundary.

Adapter bridges use limited access with no delivery subscriptions. Every
configured bot ID must be unique and have an explicit exact action resource
`bot:<bridge-id>:<bot-id>`. Broker manifests gain exact resource declarations;
they are resolved before legacy prefix resources and reject duplicate owners.
The adapter host cross-validates the configured instances against the manifest.

Legacy `[runtimes.*] kind = "adapter"` configuration is rejected with
`migration_required`; only `broker.bridges` is accepted. Sensitive adapter
options use structured vault references, for example
`access_token = { secret_ref = "onebot-token" }`. `bridge run` resolves them
into a launcher-only runtime options copy. Settings, broker wire messages,
diagnostics, and logs keep only secret references or redacted values.

## Lifecycle

OneBot HTTP Post, forward WebSocket, reverse WebSocket, and Satori gateway
transport are retained and revalidated. Invalid configuration, authentication,
listener failure, or any unrecoverable adapter failure closes every connection
and exits the bridge nonzero; the broker does not supervise or restart it.

Satori and WebSocket transient connection failures retry at 1, 2, and 4
seconds. Exhaustion closes the entire bridge and reports failure to the external
process manager. Restart must clear reply-route and connection state before the
next generation accepts events.

## Completion gate

Tests cover legacy-runtime rejection, secret reference resolution and redaction,
mixed driver grades, multi-instance startup, duplicate and prefix-colliding bot
IDs, manifest mismatch, platform topic normalization, identity binding, reply
and proactive sends, unsupported action rejection, lease/result replay,
disconnect, restart, and bounded retry exhaustion.

The complete quality gate, workspace build, adapter/driver isolated verifiers,
and signed Alpha bundle verifier must pass. Legacy v6 runtime migration, Agent,
Function DSL, and broker process supervision remain outside Alpha 4.

## Alpha 5 handoff

Alpha 5 applies the same owned broker-bridge boundary to v6 compatibility and
MoFox while preserving the selected matcher/session/message surface only.
