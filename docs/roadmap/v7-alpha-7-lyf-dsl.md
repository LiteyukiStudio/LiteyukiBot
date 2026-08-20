# v7 Alpha 7: Liteyuki Function DSL

> **Planned implementation contract.** The detailed syntax and host design is
> documented under [`docs/functions`](../functions/README.md). This document
> does not claim that the LYF language or its runtime has been implemented or
> released.

Alpha 7 replaces the historical line-oriented v6 function executor with a
restricted, resource-pack-only DSL shared by Native and Cordis hosts.

## Boundary

The canonical extension is `.lyf`; `.liteyukifunction` and
`.liteyukifunctions` are syntax-equivalent aliases. Historical `.lyfunction`
and `.mcfunction` execution is rejected, not translated. Programs load only
from `functions/` in installed and enabled Native/Cordis extension resource
packs.

The parser uses Lark, builds a source-span-preserving AST, and emits stable
location-aware diagnostics. `tmp/example.lyf` is directional input only and
does not define compatibility behavior.

## Runtime

The first executable subset is `use`, bindings, `fn`/`async fn`, calls,
returns, tuple destructuring, `@agent`, and `@events`. Loops, `terminal`,
`sync fn`, and unsupported control flow parse and diagnose but do not execute.
No arbitrary Python import or filesystem script execution is available.

`use` resolves only installed, enabled `liteyukibot.function_libraries` exports
declared by metadata. Libraries behave like explicit Python-like namespaces but
cannot import arbitrary modules. Native and Cordis hosts inject the same
Function Host service and own lifecycle, Tool registration, prompts, and event
subscriptions. Function files are resources owned by their parent extension,
not independent plugins or bridges.

`@agent(tool)` exports a DSL Tool. `@agent(prompt, name=...)` creates an
immutable named prompt preset; Agent configuration selects a default and an
authorized Tool may switch a conversation only to a registered preset.
`@events(topic)` registers a host-owned DSL event handler.

## Completion

Release `v7.0.0a7` with every independent first-party package rebuilt against
that exact kernel. Parser and diagnostic golden tests, Native/Cordis execution
parity, library declaration rejection, decorator lifecycle cleanup, prompt
selection, Tool schema/permission behavior, and unsupported-syntax failures
must pass.
