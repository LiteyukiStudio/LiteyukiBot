# ADR 0011: Bound Pre-stable Protocol Versioning

- Status: Accepted
- Date: 2026-08-09

## Context

v7 is in rapid alpha development. Treating every wire or schema correction as
a permanent compatibility event would create artificial protocol versions such
as v20 or v99 before the design has reached a stable release. It would also
force the project to maintain experiments that have not been released as stable
contracts.

The current local runtime IPC version is v3. The repository still tests v1 and
v2 peers because that code exists and remains inexpensive to exercise, but this
must not be confused with a pre-stable compatibility promise.

## Decision

All v7 protocol contracts are explicitly unstable until the first stable v7
release. During this period, wire messages, Event/Action schemas, capabilities,
and their semantics may change without backwards-compatibility shims. Each
change still requires updated models, tests, documentation, and migration notes
where existing alpha users would otherwise be surprised.

Protocol numbering is intentionally bounded:

- v3 remains the default development protocol;
- small or medium corrections, additions, removals, and breaking changes modify
  v3 directly instead of incrementing the number;
- v4 or v5 is reserved for a large cross-cutting redesign where retaining the
  v3 identity would make wire direction, ownership, or negotiation materially
  misleading;
- no pre-stable protocol version may exceed v5;
- version gaps, date-based protocol numbers, and cosmetic increments are not
  used.

Retaining compatibility with v1, v2, or an earlier v3 shape is optional during
alpha. It is kept only when its implementation and testing cost remain low and
it does not distort the intended architecture. Removing such compatibility is
an ordinary reviewed change, not a major-version event.

Before the first stable release, the project will select the stable wire and
schema baselines, document their migration policy, and replace this alpha rule
with an explicit long-term compatibility policy.

## Consequences

The version number communicates architectural generations rather than commit
count. Fast iteration can correct contracts directly, while v4/v5 remain
available if a genuinely large protocol redesign occurs.

Accepted ADRs continue to record design intent and testable behavior, but their
compatibility language does not override this pre-stable policy. Review still
requires evidence and explicit documentation; instability is not permission for
undocumented wire drift.
