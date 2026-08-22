# v7 Alpha 10.1: Portable Facade Convergence

Alpha10.1 freezes the portable Runtime API shape built by Alpha9. It keeps
NoneBot and AstrBot as the only supported provider facets and does not add new
operations or providers.

## Canonical DTOs

The kernel owns the JSON-safe DTOs used by both provider API packages:

- `EventSnapshot`: `source_event_id`, `runtime_id`, `adapter`, `bot_id`,
  `event_type`, `conversation`, `actor`, `message`, and `extensions`.
- `BotSnapshot`: `bot_id`, `adapter`, `capabilities`, and `extensions`.
- `SendResult`: `sent`, `result`, and `extensions`.

The portable event `message` is always the kernel `Message` DTO. Provider-only
values are placed under a provider namespace such as `extensions.astrbot`.
Extensions are JSON-safe and are not required for portable consumers.

The shared catalog is Runtime API `1.2`. The operation names and input shapes
remain `event.snapshot`, `event.send`, `bot.snapshot`, and `bot.send`; only the
canonical result contract is converged.

## Compatibility

The two API packages retain their existing provider class names. NoneBot
snapshot classes are aliases of the kernel DTOs. AstrBot snapshot classes are
compatibility subclasses exposing `platform_id`, `platform_name`,
`session_id`, `message_type`, and related properties from its extension
namespace.

AstrBot's old `message: str` field is intentionally corrected to the portable
`Message` value. Consumers that need the former text projection use
`message_text` or `message.plain_text`; this correction is documented as an
Alpha migration rather than a framework SDK compatibility promise.

## Exit Criteria

- Both providers register the same version and input/output schema for each
  portable operation.
- Provider hosts construct the same kernel DTOs and preserve only explicitly
  namespaced provider extensions.
- Typed API proxies return the same `EventSnapshot`, `BotSnapshot`, and
  `SendResult` semantics.
- Invalid provider results fail with `RUNTIME_API_INVALID_RESULT`.
- API package tests, full repository gates, built wheel verifiers, and an
  authorized external workspace pass.

Catalog fingerprints, isolated API verifier promotion into ordinary CI, B7
peer examples, and plugin authoring examples are Alpha10.2 work.
