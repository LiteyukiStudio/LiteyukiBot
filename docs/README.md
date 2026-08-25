# Documentation

`docs/` contains maintained v7 contracts and operational guidance. Write facts
that match the current implementation and tested release state; do not use this
tree for scratch plans or promises about unimplemented work.

The maintained [v7 Alpha roadmap](roadmap/v7-alpha-roadmap.md) is a planning
reference, not an implementation or release commitment. Its
[Alpha 1 baseline](roadmap/v7-alpha-1-baseline.md) records the agreed future
release contract. The [Alpha 2 baseline](roadmap/v7-alpha-2-plugin-permission-tools.md)
records the planned Plugin, Permission, and Tool RPC contract. The former
Beta1-Beta7 series is retained as architecture-validation history. The
[Alpha 3 business migration](roadmap/v7-alpha-3-business-plugin-migration.md)
records the planned first-party package boundary; none of these plans evidence
that an Alpha roadmap stage is complete. The
[Alpha 4 adapter bridge](roadmap/v7-alpha-4-adapter-bridge.md) records the
planned generic and platform adapter migration boundary. The
[Alpha 5 compatibility bridges](roadmap/v7-alpha-5-compatibility-bridges.md)
and [Alpha 6 Agent bridge](roadmap/v7-alpha-6-agent-bridge.md) record the
remaining compatibility and Agent boundaries. [Alpha 7 LYF DSL]
(roadmap/v7-alpha-7-lyf-dsl.md) and [Alpha 8 DevCLI updates]
(roadmap/v7-alpha-8-devcli-updates.md) record the language and operations
boundaries. Alpha8b implements the signed offline bundle, daemon update graph,
read-only editor artifacts, and WebUI resource diagnostics.
The [Alpha 9 runtime ecosystem plan](roadmap/v7-alpha-9-runtime-ecosystem.md)
extends the runtime proof with a bounded portable facade and an additional
provider facet. The [Alpha 12 ecosystem activation plan]
(roadmap/v7-alpha-12-ecosystem-activation.md) covers the governed plugin index
and managed NoneBot generations. The [Alpha 13 WebUI and TextMate plan]
(roadmap/v7-alpha-13-webui-textmate.md) records the current source-version
baseline. Alpha14 is an architecture-subtraction transition: retired bridge
experiments are excluded from the workspace and release graph, while their
source snapshots remain under `extras/legacy-bridges`.

- `specs/` contains the versioned, normative public contracts.
- `architecture/` describes the current system boundary and lifecycle.
- `development/` contains contributor, plugin-author, runtime-author, and
  release-maintainer guidance.
- `roadmap/` contains forward-looking release plans. Its documents must label
  planned behavior explicitly and must not redefine current contracts.
- `functions/` contains the Alpha7 LYF language specification, split by
  lexical, module, binding, function, decorator, Library, host and diagnostic
  concerns.
- `archive/` holds completed historical records that remain useful for design
  or release archaeology.
- top-level documents cover configuration, compatibility, and performance; the
  historical [Beta1 support contract](archive/2026-08-17/beta1-contract.md) is
  archived.

Keep relative Markdown links valid. Contract changes need focused tests in the
same pull request and a corresponding specification update. Git history, not a
documentation subtree, preserves removed design rationale.
