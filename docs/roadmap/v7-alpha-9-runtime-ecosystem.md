# v7 Alpha 9: Runtime Ecosystem Facades and Adapter Facets

> **Implementation boundary.** Alpha9 continues the ecosystem work deferred by
> Alpha8a. It defines a supported portable facade surface; it does not mirror
> arbitrary upstream framework SDKs.

Alpha8 proves one Native or Cordis plugin can call an independently hosted
runtime bridge through a typed JSON-safe proxy. The proof intentionally exposes
only AstrBot `event.snapshot` and text `event.send`. The temporary Alpha8 plan
defers full framework facades and additional runtime adapters to Alpha9.

## Alpha9a: Runtime API v1.1

The v1.1 catalog is a minor extension of Runtime API v1. Callers declaring
`^1.0` remain compatible. Provider declarations are built through the shared
catalog helper, which binds operation schemas and capabilities to one runtime
kind.

The first portable surface is:

- `event.snapshot`: immutable event identity, conversation, actor, and
  portable message segments;
- `event.send`: text or a portable `Message` DTO;
- `bot.snapshot`: exact bot identity, provider adapter/platform, and declared
  capabilities;
- `bot.send`: exact bot ID, portable message, and `ConversationRef`.

AstrBot owns the AstrBot-specific translation and publishes the typed
`runtime-astrbot-api` package. Its bridge never places AstrBot events, native
chains, or platform objects on the Broker wire.

## Alpha9b: Runtime adapter facets

NoneBot is the first additional provider because its bridge is stable and its
OneBot/Satori conversion contract is already covered by package tests. The
separate `runtime-nonebot-api` package provides typed event and bot proxies;
the bridge publishes the same portable operation boundary and enforces exact
bot authorization before proactive sends.

MoFox remains an experimental compatibility bridge. It can adopt the shared
catalog later after its upstream API surface and distribution policy are stable
enough to freeze. Alpha9 does not require a broad MoFox SDK mirror.

## Security and lifecycle boundary

Runtime calls remain possible only while the caller owns an active event or
Tool delivery lease. Required runtime dependencies fail activation; optional
dependencies resolve to unavailable proxies. Provider failures become bounded
error codes. Framework objects, raw SDK handles, arbitrary API passthrough,
streaming, mutable group objects, and long-running LLM calls are excluded.

## Exit criteria

- Alpha8 v1 event proxy behavior remains compatible.
- AstrBot and NoneBot v1.1 catalogs validate JSON schemas and per-operation
  capabilities.
- Native and Cordis proxy resolution has parity for optional/required
  availability and provider disconnect behavior.
- Event snapshots and send results are JSON-safe and contain no framework
  instances or native message chains.
- Exact bot ownership is checked for every `bot.send` call.
- Built wheel install verifiers discover both typed facade packages outside the
  source tree.
- Full pytest, Ruff, mypy, workspace build, package verifiers, and authorized
  external workspace tests pass.

The bare/installed-first-party benchmark profiles, 72-hour soak, and
full-workspace theoretical benchmark remain post-Alpha qualification work as
defined by the main Alpha roadmap.
