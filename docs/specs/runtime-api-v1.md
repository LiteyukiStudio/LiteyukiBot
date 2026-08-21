# Runtime API v1

## Status

Applies to the Alpha8a Broker protocol v7 and the Native/Cordis Extension API
v2 hosts. This is a first feasibility contract, not a promise to mirror any
framework's complete public SDK.

## Boundary

Native and Cordis extensions may declare a runtime kind, optional bridge ID,
API namespace, operation set, SemVer range, and optionality in their manifest.
The `@runtime` decorator binds one namespace to an explicit keyword-only
proxy parameter. The host validates the decorator against the manifest before
registration.

Runtime API calls are allowed only while an event or Tool invocation owns an
active Broker delivery. The call carries the original event authorization,
extension identity, current delivery lease, API operation, and JSON-safe
arguments. Setup, start, and background tasks have no runtime API context.

## Catalog and wire contract

Each bridge registers immutable runtime API declarations containing the runtime
kind, namespace, operation, API version, input schema, output schema, and
required capability. The Broker routes `runtime.api.invoke` and
`runtime.api.result` independently from `bridge.control.invoke`; it validates
owner uniqueness, active leases, canonical request replay, result replay,
expiry, and owner disconnect.

The provider host validates the declared input and output schemas; the kernel
validates JSON safety, provenance, permissions, and the active delivery lease.
Provider exceptions never cross the wire; results use stable error codes and
bounded JSON error details.

## Alpha8a AstrBot proof

The framework-neutral AstrBot SDK owns typed DTOs and proxy classes without
depending on AstrBot. The bridge host owns AstrBot imports and maps the proof
facade to the real `AstrMessageEvent`.

The proof catalog contains `event.snapshot` for safe event metadata and
message component projection, plus `event.send` for native-chain sending.
The existing protocol-neutral `message.send` Action remains available as a
fallback. Streaming, LLM calls, group objects, native object returns, and the
remaining public methods are deferred to Alpha9.

## Compatibility and security

Runtime API versions use caret SemVer ranges such as `^1.0`; major versions
are incompatible and minor versions are backward compatible. Each operation
gets a capability named `runtime.<kind>.<namespace>.<operation>`. Native
activation remains limited by the configured Permission v2 ceiling; Cordis
keeps its existing full-by-default/downscoped policy. Missing optional APIs
produce an unavailable proxy, never an empty successful result.
