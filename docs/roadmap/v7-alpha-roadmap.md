# LiteyukiBot v7 Alpha Roadmap

> **Planning reference only.** This document describes a possible development
> sequence. It does not describe the current implementation, promise a release
> date, or authorize publishing any artifact. Each stage is subject to review
> against the repository state and may be extended as `aN+1` when its exit
> criteria are not met.

## Direction

The Beta1-Beta7 series was primarily architecture validation. It is retained as
history and is not a maturity claim for the next release line. The planned
release line restarts at `7.0.0a1` so that substantial Agent, DSL, and tooling
work has an explicit design and validation phase.

Before RC1, the project should publish no PyPI package for the Alpha line. An
Alpha may publish an immutable GitHub Release asset containing a signed release
manifest and SHA-256 digests. The kernel, IPC, WebUI, DevCLI, Cordis, and broker
bridge use a lockstep Alpha version. Business plugins and independently
distributed PyPI packages retain their own versions, but must declare the
compatible kernel Alpha.

## Alpha stages

The following order is a default sequence, not a guarantee that every stage
fits in one release. A stage can be split into `aN+1` without changing the
scope of later work.

### Alpha 1: Version and protocol baseline

**Goal:** make the B7 architecture-validation result reproducible and establish
the release evidence format.

**Work:** implement the [Alpha 1 baseline](v7-alpha-1-baseline.md): freeze the
applicable LYIP v2 frame, Runtime IPC v6, broker v6, and configuration v5
contracts; align the seven shipped components at `7.0.0a1`; reserve DevCLI
without shipping it; and create one GitHub Release bundle with a canonical
SHA-256 manifest, CycloneDX SBOM, and tag-bound first-party Sigstore proof.

**Exit criteria:** the full test/build/install-verifier set passes from a clean
checkout; protocol contract checks are reproducible; a downloaded bundle can
be verified without importing the source tree; existing PyPI workflows reject
Alpha releases; and no PyPI publication is attempted.

### Alpha 2: Plugin API, Permission v2, and broker tools

**Goal:** establish the extension and authorization contracts before migrating
more first-party behavior.

**Work:** implement the [Alpha 2 plugin, permission, and tool baseline]
(v7-alpha-2-plugin-permission-tools.md): introduce the shared Extension API
v2; make Native limited and Cordis full-by-default but administratively
downscopable; add Permission v2 capability ceilings and principal checks; and
add the one Broker v6 Tool RPC catalog extension before freezing it.

**Exit criteria:** Native and Cordis authorization tests cover capability
ceilings, denied calls, and redaction; tool calls cover idempotency, timeout,
disconnect, result correlation, and context non-leakage; the post-Alpha-2
broker catalog has no planned compatibility-breaking additions.

### Alpha 3: First-party business plugins

**Goal:** migrate first-party business packages to the finalized plugin and
permission contracts.

**Work:** implement the [Alpha 3 business plugin migration]
(v7-alpha-3-business-plugin-migration.md): move the first-party chain to v2
Native and Cordis hosts, publish independent signed assets, retain Functions
only as a compatibility rebuild, and use Resources/Profile as the mandatory
Tool RPC proof before expanding the remaining business Tools.

**Exit criteria:** every migrated package can be installed, enabled, disabled,
and removed independently; cross-package dependencies are declared; Native and
Cordis host behavior, limited downscoping, hard-cut legacy-state rejection, and
the completed business Tool chain are covered without implicit kernel imports.

### Alpha 4: Generic and platform adapter dual track

**Goal:** validate a generic adapter bridge without losing platform-specific
ownership.

**Work:** implement the [Alpha 4 adapter bridge]
(v7-alpha-4-adapter-bridge.md): turn the generic adapter host into a mixed
broker bridge, migrate OneBot/Satori drivers, preserve platform transports,
use vault-only secret references, and make bot action ownership exact.

**Exit criteria:** generic, OneBot, and Satori paths pass broker-peer,
installation, restart, disconnect, action-return, vault-redaction, exact-owner,
and bounded-retry tests; no adapter SDK is imported by the root kernel.

### Alpha 5: Legacy runtime bridge migration

**Goal:** preserve the useful v6 interaction model while removing the old
runtime ownership boundary.

**Work:** implement the [Alpha 5 compatibility bridges]
(v7-alpha-5-compatibility-bridges.md): migrate v6 and MoFox to limited broker
bridges, retain only the selected matcher/session/message/send surface, and
remove legacy child-runtime/projection behavior.

**Exit criteria:** v6 matcher/session regressions, bridge lifecycle, topic
pattern, failure recovery, and MoFox workspace isolation pass; every retained
legacy entry point is marked migration, compatibility, or removal status.

### Alpha 6: Independent Agent Alpha

**Goal:** build Agent as an independent workload with explicit tool and data
boundaries, rather than expanding the kernel.

**Work:** implement the [Alpha 6 Agent bridge](v7-alpha-6-agent-bridge.md):
replace the old Agent runtime/plugin, add progressive Tool discovery,
Permissions v2 caller checks, subprocess sandbox workers, and experimental
SQLite RAG with replaceable embedding/rerank providers.

**Exit criteria:** Tool RPC is end-to-end and bounded; embedding/rerank
providers are replaceable; RAG retrieval is deterministic under its reference
workload; worker timeout, crash, and policy tests pass. Agent quality and
third-party containment are not Alpha stability claims.

### Alpha 7: Liteyuki Function DSL

**Goal:** replace the ad-hoc function surface with a documented, diagnosable
`.lyf` language while keeping execution constrained.

**Work:** implement the [Alpha 7 LYF DSL](v7-alpha-7-lyf-dsl.md): replace the
v6 executor with Lark-parsed resource-pack-only `.lyf`, explicit Function
Libraries, and Native/Cordis-shared Agent/Event decorator behavior.

**Exit criteria:** grammar and diagnostic golden tests pass; parse/execute
behavior is consistent across Native and Cordis hosts; library/decorator
boundaries are enforced; unsupported control flow has stable location-aware
diagnostics rather than silent interpretation.

### Alpha 8: Developer and update tooling

**Goal:** make the planned ecosystem usable and recoverable by developers and
operators.

**Work:** implement the [Alpha 8 DevCLI and updates]
(v7-alpha-8-devcli-updates.md): ship the separate Python scaffold and npm
launcher, verified GitHub/local bundle staging, daemon-managed full-instance
atomic updates, and read-only LYF editor integration.

**Exit criteria:** signature, digest, and lock failures are rejected; drain
timeout, rollback, restart, and interrupted-update recovery are tested; no
managed bridge or WebUI path can observe a half-updated instance.

If Alpha 8 is not sufficient, continue with `7.0.0aN` releases. Do not enter
Beta or RC solely because the numbered list is complete.

## Shared release gates

Every Alpha must pass the complete repository pytest suite, Ruff, Mypy,
workspace build, and package install verifiers. Contract changes require focused
wire, lifecycle, permission, disconnect, and upgrade-boundary tests. Artifacts
must be generated from a clean checkout and retain the exact manifest and
SHA-256 evidence used for verification.

Only after Alpha work is complete and reviewed should the project run the two
parallel qualification profiles: bare kernel and kernel with all installed
first-party packages. The 72-hour soak and the full-workspace theoretical
benchmark are post-Alpha qualification work; this roadmap records no result for
either. Their reviewed artifacts are prerequisites for a future Beta decision.

## Non-goals

- This roadmap does not make every existing package complete or stable.
- It does not promise a universal plugin ecosystem, arbitrary Python execution,
  durable broker delivery, or unrestricted Agent tools.
- It does not define final Function DSL grammar beyond the stated Alpha scope,
  select a production embedding/rerank provider, or guarantee model quality.
- It does not replace versioned specs, package READMEs, or release checklists;
  those documents become authoritative only when implementation lands.
