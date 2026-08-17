# v7 Alpha 2: Plugin, Permission, and Tool Baseline

> **Planned implementation contract.** This document records the agreed Alpha 2
> boundary. It does not claim that Plugin API v2, Permission v2, or Broker Tool
> RPC is implemented or released.

Alpha 2 establishes the extension and authorization contracts before the
business-package migration. It starts only after the Alpha 1 release baseline
is merged.

## Release boundary

The lockstep release set advances to `7.0.0a2` under tag `v7.0.0a2`. The
seven-component bundle, GitHub Release, Sigstore manifest proof, and PyPI ban
remain unchanged from Alpha 1.

`liteyukibot-v7-permissions==0.3.0a1` is an additional independent,
first-party plugin asset in the signed release bundle. It requires
`liteyukibot-v7==7.0.0a2` and does not join the lockstep version. The release
manifest must mark it as an independent plugin component; no other business
package is added in Alpha 2.

## Extension API v2

Native and Cordis extensions use one `ExtensionManifest(api_version=2)` with
identity, service/resource declarations, requested capabilities, coexistence,
and tool declarations. A `ToolDeclaration` has a globally unique ID prefixed
by its extension ID, a description, Draft 2020-12 input and output schemas,
and the capabilities required to invoke it.

Native extensions are always `limited`. Cordis defaults to unrestricted
`full`; an administrator may only lower an enabled Cordis extension through
`[cordis.access]`. An extension cannot grant or elevate its own access. The
term `stable-first` remains release/documentation language and is not an API,
configuration, or authorization value.

`PluginManifest` and `PluginDefinition` remain temporary deprecated source
aliases that construct v2 values. Explicit API v1 values, v1 loading, and v1
authorization semantics are rejected. This keeps unmodified business packages
buildable while reserving their behavior migration for Alpha 3.

## Permission v2

Permission v2 replaces event-object authorization with a minimal
`AuthorizationContext`: event ID, runtime ID, bot ID, and optional actor ID.
It does not carry message content, raw adapter payload, tool input, or tool
output. Decisions remain exact-principal, fail closed, bounded, and redacted.

The Permissions plugin owns a `plugin_capabilities` grant map keyed by
extension ID. A limited extension may activate only when every requested
capability is within its configured ceiling; unknown or disabled grant targets
and over-ceiling declarations fail startup. Full Cordis extensions require no
capability declaration or grant and accept the resulting risk explicitly.

Limited hosts enforce every v2 privileged entry point: tool invocation and
provision, capability service access, adapter privileges, and management
privileges. Both the caller and provider host authorize the original context.
Full hosts bypass principal checks by policy and retain audit records. This is
an in-process host contract, not a sandbox against malicious Python imports.

## Broker Tool RPC

Broker protocol remains v6 and gains exactly two BUSINESS-lane catalog entries:
`tool.invoke` at type ID `616` and `tool.result` at type ID `617`. This is the
only planned compatibility-breaking catalog addition in the Alpha line.

`ToolInvoke` binds delivery ID, lease ID, correlation ID, tool ID, JSON
arguments, and `AuthorizationContext`; the broker assigns the invocation ID.
`ToolResult` binds that ID and contains either JSON result data or a stable
error code with optional redacted JSON details. Exception classes, messages,
tracebacks, and event payloads never cross the wire.

Tool declarations become immutable `BridgeManifest` entries. External bridges
remain configuration-authoritative. The authenticated, configured full kernel
bridge may project the enabled Native/Cordis manifests once during registration.
The broker enforces globally unique exact tool ownership, active lease binding,
canonical request deduplication, retained result replay, expiry, and owner
disconnect. It validates JSON-safe wire data and declaration shape only; the
calling and providing hosts validate the declared JSON schemas.

Native setup and Cordis Scope activation register exactly one handler for each
declared tool before kernel bridge registration. Registration cannot change
after that bridge starts. `BridgeClient`, `BrokerBridgeRunner`,
`KernelBrokerPeer`, diagnostics, and the event-delivery view expose the same
bounded lifecycle without adding broker business execution.

## Completion gate

Alpha 2 completes only when v2 model validation, source-alias behavior,
Cordis downscoping, activation denial, redacted auditing, caller/provider dual
authorization, schema validation, and minimal-context non-leakage are covered.

Broker tests must cover wire IDs and lanes, malformed input, manifest mismatch,
kernel catalog projection, ownership collision, idempotent replay, stale lease,
timeout, owner disconnect, and stable result codes. The complete quality gate,
workspace build, affected install verifiers, and signed Alpha bundle verifier
must pass.

Agent, RAG, sandbox workers, Function DSL, and business-package behavior
migration remain outside Alpha 2.
