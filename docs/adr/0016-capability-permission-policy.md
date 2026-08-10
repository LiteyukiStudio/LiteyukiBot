# ADR 0016: Resolve Static Roles into Exact Capabilities

- Status: Accepted
- Date: 2026-08-10

## Context

ADR 0013 established a first-party permission service outside the kernel and
deliberately limited its first alpha to `public` and `operator`. Native plugins
now need independent permissions without teaching the kernel about users or
forcing every privileged command into one broad operator category.

The project remains in rapid alpha development. Keeping both an operator
allowlist and a capability model would create two policy languages before
either is stable. Dynamic policy, persistence, wildcard selectors, and role
inheritance would also add ownership and migration questions that the current
static application configuration does not answer.

## Decision

`liteyukibot-v7-permissions` continues to provide
`liteyukibot.permissions@1`. The consumer call shape remains
`allows(event, capability)`, but the `operator` constant and `operators`
configuration are removed. This record replaces the policy details in ADR
0013 and the status permission in ADR 0015; the package and kernel boundaries
established there remain unchanged.

A principal is still the exact `(runtime_id, bot_id, actor_id)` tuple. Static
configuration defines named roles as sets of capability tokens and grants roles
or direct capabilities to exact principals. Roles do not inherit from other
roles. Grants are additive and cannot contain deny entries or wildcards.

The service exposes `resolve(event) -> PermissionSnapshot`. The frozen snapshot
contains the resolved principal, role names, and fully expanded capabilities.
Every event has the reserved `public` capability; an event without an actor has
no principal or other capability. Plugins check capability names and never
role names.

Role names and capabilities are case-sensitive, trimmed, non-empty tokens
without whitespace. `public` cannot be configured explicitly. Duplicate
entries, duplicate principals, empty roles or grants, undefined roles, unknown
fields, and malformed values fail plugin setup. Runtime checks are exact and
fail closed. An ordinary missing capability is not logged as a warning.

Role expansion is completed once during setup. Runtime resolution performs no
I/O, mutation, inheritance traversal, or adapter-specific lookup. The service
is application policy for trusted in-process plugins, not a sandbox boundary.

## Consequences

Deployments can group capabilities without coupling plugins to deployment role
names. Permission snapshots are suitable for diagnostics and tests while
remaining deeply immutable.

Existing alpha configurations using `operators` must migrate to `roles` and
`grants`. This is an intentional pre-stable contract correction; the runtime
does not maintain dual configuration paths.

Persistent policy, remote updates, deny rules, wildcard scopes, role
inheritance, and adapter superuser imports remain future work. They require a
new decision because they change conflict resolution and operational ownership.
