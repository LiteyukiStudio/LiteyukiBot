# v7 Alpha 14: Ownership And Release Baseline

Status: active. The source identity is `7.0.0a14` / `v7.0.0a14`. This page is
the authoritative Alpha14 route; earlier Alpha plans remain implementation
history and do not redefine the current boundary.

Alpha14 is an architecture-subtraction stage. It prioritizes LiteyukiBot's own
plugin and operations ecosystem, corrects ownership boundaries, completes the
release graph, and prepares a controlled Alpha15 freeze. It does not expand
framework compatibility or the WebUI product surface.

## Verified starting point

- Alpha13's WebUI and LYF TextMate source work is complete.
  `@liteyuki/lyf-textmate@0.1.0-alpha.13` was published by the
  `LiteyukiStudio/lyf-textmate` GitHub Actions trusted publisher through
  `.github/workflows/publish.yml`. The npm registry records SLSA provenance,
  package integrity
  `sha512-8vfqxmjMvJvO3KLctd1Yg4Pjl0lO9hEL4p9C7YxMFD8VEx0YchMk3TM8bRwQ1qyr8gjsb4H0kc0eNxCoEFod7A==`,
  and source `gitHead` `fc94c4280fb22e0cc937779734c975e5e0b6e373`.
- LiteyukiBot consumes that exact npm version in `webui/package.json` and
  locks the same version and integrity in `webui/pnpm-lock.yaml`; commit
  `62065111b9345b52120ca2d3d3de9fe485aed65b` replaced the temporary Git
  dependency.
- AstrBot, Neo-MoFox, and v6 compatibility packages are excluded from the
  workspace, lock, CI, and release graph. Their source snapshots under
  `extras/legacy-bridges/` are historical material, not supported mainline
  features.
- The Alpha14 release registry covers all 19 workspace distributions. Every
  first-party dependency is exact-pinned, 18 distributions have isolated
  install verifiers, and the reference NoneBot plugin has its external-host
  lifecycle E2E. Four bundle-only components remain outside the PyPI project
  projection.

This baseline does not create a tag, GitHub Release, PyPI upload, or npm
upload. Artifact publication requires a separate release decision after the
complete gates pass.

## Product and ownership boundary

- Liteyuki-first is the product priority. Do not add compatibility providers
  merely to increase ecosystem coverage before the LiteyukiBot path is
  coherent.
- The target kernel owns protocol-neutral JSON-safe DTOs and contracts,
  EventBus, shared lifecycle and service interfaces, capability declarations,
  and minimal common configuration. It does not own plugin installation and
  storage, daemon orchestration, WebUI business, update coordination, or
  concrete framework behavior.
- `liteyukibot-v7` remains the branded installation, CLI, and composition
  package. Composition may connect first-party implementations; kernel
  contracts must not import those implementations back.
- YAML is acceptable when required by common configuration. Any other kernel
  dependency needs an identified owner, a concrete kernel call site, and a
  written reason.
- Cordis is the public in-process business-plugin path. First-party business
  packages must become real Cordis implementations rather than wrappers around
  Native plugins. Native remains controlled infrastructure and bounded
  migration surface.
- Broker is the authenticated cross-process authority boundary. Untrusted
  execution must cross a capability-limited and rate-limited Broker bridge;
  Cordis permissions do not contain malicious in-process Python.

## Implementation route

1. Break the Broker/plugin-manager reverse dependency by moving neutral
   bridge, facet, probe, and target-resolution contracts to the kernel boundary
   and injecting concrete resolution from composition.
2. Extract the kernel contract nucleus without WebUI, plugin store/install,
   daemon, or Broker-service business. Preserve public imports only through
   deliberate composition re-exports, not implementation back-imports.
3. Extract Broker protocol, routing, peer, ledger, diagnostics, and LYIP
   ownership. Keep application settings and plugin management outside it.
4. Extract plugin discovery and lifecycle, artifact and generation stores,
   installation, sources, and managed-target ownership. Move concrete plugin
   operations out of kernel management.
5. Extract daemon process graph, control, operations, profiles, updates, and
   rollback ownership. The daemon may depend on kernel contracts, Broker, and
   plugin management; those layers must not depend on daemon orchestration.
6. Reduce the root package to composition and CLI mapping, then convert the
   first-party business chain to actual Cordis implementations.

Each step is a hard migration with focused tests. Do not add a compatibility
shim that restores the reverse dependency the step removes. Preserve live
generation fields such as `runtime_id`, `runtime_kind`, and
`PLUGIN_GENERATION_ENV` until their owning public contract is deliberately
migrated.

The first route step uses `liteyukibot.bridge_contracts` as the canonical
contract module. Broker may re-export those types but must not own or import
plugin-store implementations. The legacy `liteyukibot.managed_plugins` path is
only an implementation-free import compatibility surface. Concrete target
eligibility and entry-point discovery belong to composition and are injected
into plugin installation rather than rediscovered there.

## Diagnostic traceability

The diagnostic goal is to reconstruct the causal path of a failure from logs,
event and trace identities, handler order, action correlation, timing, and
recorded outcomes. It is not execution replay or an automatic regression
reproduction promise.

Retain bounded structured metadata needed to identify ordering, ownership,
result, error class, and elapsed time across Broker, kernel, Cordis handlers,
and actions. Do not capture message bodies, credentials, configuration values,
or other sensitive payloads for diagnosis. Existing `replayed` fields describe
retained-result or idempotency behavior, not diagnostic re-execution.

## Alpha14 exit

Alpha14 is complete only when:

- the kernel, Broker, plugin-manager, daemon, and root composition ownership
  boundaries above are implemented without reverse first-party imports;
- the retained Runtime concepts use honest provider-neutral bridge or managed
  target contracts, and retired compatibility remains outside mainline;
- first-party Cordis business plugins do not delegate their implementation to
  Native plugin wrappers;
- the 19-distribution registry, signed manifest/SBOM, exact pins, all install
  verifiers, reference E2E, full tests, Ruff, Mypy, and workspace build pass
  from built artifacts; and
- maintained architecture, operations, configuration, package, and release
  documents describe the implemented ownership, with both owners reviewing the
  retained evidence.

## Alpha15 and Beta gate

Alpha15 accepts defects, tests, documentation, performance work, and release
preparation only. A public-contract addition requires a blocker-level reason
and both owners' approval. WebUI remains feature-frozen through Alpha14 and
Alpha15; authentication, status, logs, and existing plugin operations may be
maintained, but no trace product, editor, or new management domain is added.

Beta requires both gates below; neither substitutes for the other:

1. **Public-contract freeze:** 14 consecutive days from an explicitly recorded
   Alpha15 baseline commit with no new public contract. An approved contract
   addition resets the clock.
2. **Reference soak:** a reviewed 72-hour deployment of the candidate built
   artifacts, retaining configuration identity, bounded logs and traces,
   errors, restarts, resource measurements, recovery or rollback evidence, and
   the exact start and end times.

Both owners must review the retained freeze and soak evidence before a Beta tag
is authorized. Short CI, benchmark, local endurance, or replay claims do not
satisfy either gate.
