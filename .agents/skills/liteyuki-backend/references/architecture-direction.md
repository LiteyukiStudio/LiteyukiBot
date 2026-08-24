# Approved Alpha14 And Alpha15 Direction

The items here are approved implementation direction, not Alpha13 facts.
Preserve that distinction in code reviews, plans, migration notes, and release
claims.

## Product And Ownership

- Liteyuki-first is the product priority. Build a coherent LiteyukiBot plugin
  and operations ecosystem before expanding compatibility with other bot
  ecosystems.
- The target kernel owns public protocol-neutral DTOs, contracts, EventBus,
  shared lifecycle/service interfaces, capability declarations, and minimal
  configuration primitives. It does not own plugin store/install business,
  daemon orchestration, WebUI business, update coordination, or concrete
  framework behavior.
- Alpha14 extracts clear kernel, Broker, daemon, and plugin-manager ownership
  boundaries while retaining `liteyukibot-v7` as the branded installation and
  CLI composition package. Avoid compatibility shims that reintroduce reverse
  dependencies into kernel.
- YAML is an accepted kernel dependency when required by common configuration.
  Other dependencies need an identified owner, concrete kernel call site, and
  written reason. Do not enforce an arbitrary dependency count.
- Subpackages may retain independent versions, but every package participating
  in an Alpha bundle must pin the exact current kernel Alpha. Update the full
  source registry, lock, verifier, and bundle together when that pin changes.

## Extension And Process Boundaries

- Cordis is the public business-plugin path. Convert first-party business
  packages to real Cordis implementations instead of wrapping Native plugins.
- Native remains only for controlled infrastructure and bounded migration. It
  is not the recommended third-party business API and should not regain public
  product prominence through convenience exports or examples.
- Cordis code is trusted in-process. Permissions constrain product authority
  and mistakes; they do not contain malicious Python. Untrusted execution must
  cross an authenticated, capability-limited, rate-limited Broker bridge.
- Broker is the cross-process contract and authority boundary. Alpha14 removes
  the legacy Runtime production path and migrates retained concepts to honest
  bridge/managed-target names. Before deleting or renaming anything, scan all
  imports, configuration, CLI, wire fields, examples, docs, tests, metadata,
  verifiers, and generated public API declarations.

## Diagnostic Observability

The reproducibility goal means reconstructing the causal path of a failure from
logs, event identities, traces, handler order, action correlation, timing, and
recorded outcomes. It does **not** mean replaying captured inputs to reproduce
the same execution or regression automatically.

- Preserve event and trace identity across Broker, kernel, Cordis handlers, and
  actions. Record enough bounded, structured metadata to identify ordering,
  ownership, result, error class, and elapsed time.
- Do not capture message bodies, credentials, configuration values, or other
  sensitive payloads merely to improve diagnosis.
- Do not promise execution replay, deterministic reruns, input capture, random
  source control, or side-effect reproduction. Broker fields named `replayed`
  describe retained-result/idempotency behavior, not diagnostic re-execution.

## Freeze And Beta Gate

- Alpha14 is architecture subtraction, ownership correction, hard migration,
  tests, and document reconstruction. Avoid unrelated feature growth.
- Alpha15 accepts defects, tests, documentation, performance work, and release
  preparation only. Public-contract additions require a blocker-level reason
  and owner approval.
- WebUI is frozen across both stages. Maintain authentication, existing status,
  logs, plugin operations, and defects; do not add a trace product, editor, or
  new management domain.
- Beta qualification requires 14 consecutive days without a new public
  contract plus a reviewed 72-hour reference deployment soak. Traceability is
  part of diagnosing the soak; it is not a replay guarantee.
- Do not call either gate complete without retained evidence and both owners'
  review.

## Documentation Ownership

- Rebuild maintained documentation around current architecture, contracts,
  guides, Beta readiness, and a small historical archive. Git history carries
  discarded prose; archive only material with continuing decision value.
- `docs/tmp/` is the tracked temporary decision area. Every file needs status,
  owner, topic, applies-to, supersedes, expires, and promotes-to metadata. The
  default lifetime is at most 30 days; use a shorter expiry for urgent setup
  checklists.
- Root `tmp/` is only for tests, disposable workspaces, runtime state, build
  evidence, and generated artifacts. Never use it as a documentation library.
