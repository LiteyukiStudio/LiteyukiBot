# Host and Runtime

## Ownership

The parent Native or Cordis extension owns the resource pack and its Function
Host. LYF has no independent plugin identity, storage root, configuration table
or process lifecycle.

`liteyukibot-v7-functions` supplies the parser, immutable AST, bounded evaluator,
Library registry and host-neutral protocol. The Kernel may discover that
implementation through a Function Host entry point, but does not import the
first-party package directly.

## Startup

The application performs the following steps before accepting events:

1. Discover enabled Native/Cordis extensions and resource pack declarations.
2. Parse every selected `functions/` file and verify its `@version`.
3. Resolve `use` Providers and build the pack-to-extension ownership index.
4. Preflight Tool schemas, prompt presets, event topics and function symbols.
5. Collect static Tool contributions before the Kernel Broker peer registers.
6. Create one Function Host per active extension and bind its lifecycle.
7. Register event subscriptions and Tool handlers, then enter READY state.

Missing Providers, invalid syntax, duplicate contribution IDs and invalid
resource ownership fail startup. They are not deferred to the first invocation.

## Native and Cordis

Native `PluginContext` and Cordis `Scope` receive the same Function Host
protocol. The adapters differ only in lifecycle binding:

- Native uses PluginContext tasks, EventBus subscriptions, service access and
  cleanup callbacks.
- Cordis uses Scope ownership, providers, event registrations, Tool bindings
  and deterministic scope cleanup.

The evaluator never receives a raw `LiteyukiApp`, Cordis Scope, adapter object or
Python plugin instance.

## Broker Tools

LYF Tools are merged into the Kernel bridge's initial Broker manifest. Their
full IDs are namespaced by the parent extension. Registration is immutable for
the lifetime of the bridge; changing a function resource requires a restart or
an explicit future reload protocol.

Tool calls validate the original event authorization, input schema, capability
ceiling, output schema and JSON size. Exceptions and tracebacks never cross the
Broker wire.

## Prompt catalog and controls

The Kernel preflights prompt presets and owns the verified catalog projection.
The Agent bridge uses the existing control message family:

- `agent.function.catalog`: Agent requests the bounded LYF Tool and prompt
  catalog during an active event delivery.
- `agent.prompt.catalog`: compatibility control that returns only the prompt
  subset of the same verified catalog.
- `agent.prompt.select`: the Kernel requests a preset switch from the Agent
  bridge through the active Tool delivery.

The Agent bridge may declare `agent.prompt.select` alongside its existing
`agent.history.clear` control to enable prompt switching. Only registered Tool
IDs, preset IDs and verified preset content cross the boundary.
Unknown IDs, raw prompt text, stale leases, wrong principals and replayed
conflicting requests fail closed.

## Limits

Alpha 7 uses bounded execution: maximum function nesting is 32, a source file
is limited to 256 KiB, a single returned JSON value to 256 KiB, and a prompt
preset to 16 KiB of prompt text plus 64 KiB of examples. A parent extension may
not register more than 64 prompt presets or 128 event subscriptions. The
active EventBus/Broker deadline remains the outer execution deadline.

These limits constrain workload size; Native/Cordis remain trusted in-process
Python and LYF is not a hostile-code sandbox.
