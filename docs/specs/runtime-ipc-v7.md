# Broker Peer IPC v7

- Specification version: `7`
- Applies to: the Alpha8 Broker v7 control/business catalogs and bridge
  registration contract.
- Compatibility: hard cut from the v6 broker catalog; v6 peers are rejected.

## Baseline

The registration, LYIP lane, event delivery, action, Tool, control, lease,
replay, and retention rules are the v6 baseline described in
[`runtime-ipc-v6.md`](runtime-ipc-v6.md). Alpha8 changes the broker wire
version and adds the runtime API catalog without reusing the v6 control
commands.

## Runtime API Catalog

`BridgeManifest.runtime_apis` contains immutable declarations with
`runtime_kind`, namespace, operation, API version, JSON input/output schemas,
and per-operation capabilities. A configured external bridge may provide its
catalog dynamically at registration, but every declaration must use the
configured bridge kind and duplicate `(runtime_kind, namespace.operation)`
entries are rejected.

Runtime API requests use `runtime.api.invoke` and results use
`runtime.api.result`. Requests carry the source event ID, caller extension ID,
API version range, authorization context, arguments, and the active delivery
lease. The broker validates event provenance, active lease ownership, unique
provider ownership, canonical correlation replay, result replay, expiry, and
provider session ownership.

Providers validate declared input and output schemas. Provider exceptions are
converted to stable error codes and do not cross the wire. Runtime API calls
cannot be initiated without an active delivery lease.

## Versioning

Alpha8 accepts exact versions and caret ranges such as `^1.0`. A caret range
matches the same major version with an offered minor version at or above the
requested minor version. Major versions are incompatible.
