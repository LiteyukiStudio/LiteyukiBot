# Runtime API v1

## Status

Applies to the Alpha8a Broker protocol v7 and the Native/Cordis Extension API
v2 hosts. Alpha9 adds a backward-compatible v1.1 portable facade catalog. This
is a supported compatibility surface, not a promise to mirror every framework's
complete public SDK.

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

The Alpha8 proof catalog contains `event.snapshot` for safe event metadata and
message component projection, plus `event.send` for native-chain sending.
The existing protocol-neutral `message.send` Action remains available as a
fallback. Streaming, LLM calls, group objects, native object returns, and the
remaining public methods are outside the Alpha8 proof.

## Alpha9 v1.1 portable facade

The v1.1 catalog is a minor extension of the v1 contract. A caller using
`^1.0` may resolve a v1.1 provider. Existing v1 callers retain the original
`event.snapshot` fields and text form of `event.send`.

The first supported portable operation set is:

| API | Arguments | Result boundary |
| --- | --- | --- |
| `event.snapshot` | none | immutable event identity, conversation, actor, and portable message DTO |
| `event.send` | text or portable `Message` | JSON-safe sent/result object |
| `bot.snapshot` | none | exact bot identity, provider adapter/platform, and declared capabilities |
| `bot.send` | exact `bot_id`, portable `Message`, `ConversationRef` | JSON-safe sent/result object |

`bot.send` must use the bot identity authenticated by the active event
authorization. Providers reject cross-bot requests even when another bot is
present in the same process. NoneBot and AstrBot publish these operations from
their separate bridge packages; the kernel imports neither framework SDK.

The shared catalog helper supplies the Draft 2020-12 schemas for portable
`Message` and `ConversationRef` values. Provider-specific DTOs remain typed
facades in separately distributed `runtime-*-api` packages. Framework objects,
native message chains, arbitrary API passthrough, mutable group objects,
streaming, and long-running LLM calls remain outside v1.1.

Provider failures use bounded stable error codes. Missing retained events and
unavailable bots return `RUNTIME_EVENT_UNAVAILABLE` or
`RUNTIME_BOT_UNAVAILABLE`; invalid portable values return
`RUNTIME_API_INVALID_ARGUMENTS`; provider send failures return
`RUNTIME_API_SEND_FAILED`.

## Compatibility and security

Runtime API versions use caret SemVer ranges such as `^1.0`; major versions
are incompatible and minor versions are backward compatible. Each operation
gets a capability named `runtime.<kind>.<namespace>.<operation>`. Native
activation remains limited by the configured Permission v2 ceiling; Cordis
keeps its existing full-by-default/downscoped policy. Missing optional APIs
produce an unavailable proxy, never an empty successful result.
