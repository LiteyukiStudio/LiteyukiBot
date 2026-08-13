# ADR 0018: Route Commands by Canonical Paths

- Status: Accepted
- Date: 2026-08-10

## Decision

`CommandSpec` adds an optional canonical parent `path`. A root command remains
`CommandSpec("echo")`; `CommandSpec("list", path=("plugin",))` registers
`plugin list`. Aliases apply only to the final segment, never to parent paths.

The registry indexes normalized token tuples and chooses the longest registered
path from command input. A registered parent may also own a handler. When a
longer child path is not registered, its remaining tokens stay in the parent's
raw arguments. Name and alias conflicts are checked within their complete path
and batch registration remains atomic. Snapshots sort by canonical path.

The invocation keeps its leaf `command` for existing handlers and adds the
canonical `command_path`. Kernel, runtime IPC, and Event/Action schemas do not
change.

## Consequences

Subcommands are deterministic without alias expansion ambiguity. Parent aliases
do not create implicit child aliases; plugins register each intended spelling.
Automatic parse-error replies and detailed hierarchical help are separate
consumer-layer work.
