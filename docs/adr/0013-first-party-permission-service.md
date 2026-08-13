# ADR 0013: Keep Access Policy in a First-Party Plugin

- Status: Superseded in part by ADR 0016
- Date: 2026-08-10

## Context

First-party commands need a consistent access decision, but authorization is a
consumer policy rather than an EventBus, runtime, or action-routing concern.
Putting users, roles, or adapter-specific superuser settings in the kernel
would enlarge its dependency and configuration surface before those models are
understood.

The alpha still needs an upgrade path from a simple operator allowlist to named
capabilities without forcing every command consumer to change its call shape.

## Decision

`liteyukibot-v7-permissions` is a separately distributable native plugin in the
repository's uv workspace. It provides `liteyukibot.permissions@1` and adds no
third-party runtime dependency beyond `liteyukibot-v7`.

The service accepts an `EventEnvelope` and an opaque permission string. Version
1 recognizes only `public` and `operator`; every unknown value is denied and
logged. This fail-closed string contract permits later capability names without
adding placeholder role or persistence systems now.

Operators are configured as exact `(runtime_id, bot_id, actor_id)` principals.
All fields are required, trimmed, and non-empty. Wildcards, actor-only global
identities, implicit adapter superusers, and duplicate entries are rejected.
Events without an actor may pass `public` checks but never `operator` checks.

The plugin is trusted in-process code under the existing native plugin model.
The permission result is an application policy decision, not a sandbox or a
security boundary against malicious plugins.

## Consequences

Command and other first-party plugins can depend on a small, versioned policy
surface while the kernel remains unaware of users and roles. Deployments must
enable the permission plugin explicitly and configure operator identities for
each runtime and bot.

Capability grants, roles, persistence, wildcard selectors, and compatibility
imports from NoneBot or v6 remain future work. Adding them requires explicit
configuration, migration, and service-contract tests.
