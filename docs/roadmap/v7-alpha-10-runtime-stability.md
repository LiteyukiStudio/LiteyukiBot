# v7 Alpha 10: Runtime Identity and Ingress Stability

Alpha10 follows Alpha9's runtime facade and provider work. Its first gate is
correctness hardening for the existing NoneBot and AstrBot bridges; it does not
add another provider or expand the Runtime API catalog.

## Alpha10.0: Identity and ingress correctness

### Decisions

- The configured bridge ID is the only runtime identity used in a provider's
  `EventEnvelope.runtime_id`. A provider kind such as `nonebot` or `astrbot`
  is not an identity fallback at the host boundary.
- A source event ID is a deterministic, collision-safe composite of bridge ID,
  provider scope, and upstream event ID. Components are URL-encoded after
  validation and are prefixed with `v1:`.
- Provider ingress is best-effort and decoupled from the local framework
  pipeline. The host uses one bounded FIFO publisher with a 256-item queue and
  a one-second per-item broker deadline. Queue overflow, conversion errors,
  broker failures, and timeouts are recorded and do not escape into the local
  event pipeline.
- Shutdown stops the ingress publisher before the bridge broker session. Items
  still waiting in the bounded queue may be dropped; broker delivery has no
  persistence or exactly-once guarantee.

### Work

- Pass the configured bridge ID explicitly through NoneBot and AstrBot event
  translation and runtime snapshots.
- Replace provider-specific source IDs with the shared canonical source ID
  helper and retain the upstream ID in the provider raw extension where useful.
- Use the shared bounded ingress publisher in both provider hosts.
- Test non-default bridge IDs, delimiter collisions, queue overflow, handler
  failures, timeouts, and shutdown cleanup.

### Exit criteria

- NoneBot and AstrBot ingress payloads pass the authenticated bridge identity
  check for non-default bridge IDs.
- Source identity components remain distinct when bridge, provider, or
  upstream IDs contain separators or overlap across platforms.
- Broker unavailability, conversion failure, queue overflow, and shutdown do
  not fail the provider's local event pipeline.
- Full pytest, Ruff, mypy, workspace build, runtime/API wheel verifiers, and an
  authorized external workspace test pass.

## Deferred Alpha10.x work

Portable snapshot/result DTO convergence, provider conformance tooling,
catalog fingerprints, API package CI coverage, and a third-party provider pilot
remain later Alpha10 gates. They depend on the identity and failure policy
defined here and are not part of Alpha10.0.
