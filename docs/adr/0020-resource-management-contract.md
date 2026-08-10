# ADR 0020: Native Resource Management Contract

## Status

Accepted for the alpha resource/profile chapter.

## Decision

The optional `liteyukibot.resources@1` plugin provides a registry for
declarative resource fields. It owns path resolution, field capability checks,
and the inspect/set/delete operation boundary. It registers canonical resource
commands through `liteyukibot.commands@1`: `<path>`, `<path> set <field>
<value>`, and `<path> delete <field>`. A resource provider owns its data,
storage, transactions, and migrations.

Resources target an exact `(runtime_id, bot_id, actor_id)` principal. A command
without `--actor` targets the event actor. A different actor is rejected unless
the field declares the capability for the requested operation and the current
principal has that capability. Runtime and bot IDs cannot be overridden.

The registry is optional and does not modify kernel Event/Action models,
runtime IPC, or the command service contract. Plugins that do not use the
declarative layer may continue registering commands directly.

## Consequences

- Profile and future business plugins can reuse one command and authorization
  convention without sharing a database abstraction.
- Resource providers remain independently testable and may choose SQLite,
  files, remote storage, or memory.
- Cross-principal access is explicit per operation and fail-closed.
- The alpha API may be revised directly; no v6 `sudo` or superuser compatibility
  is promised.
