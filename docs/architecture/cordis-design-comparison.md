# Cordis Design Comparison

## Scope

This document compares three different uses of the Cordis design vocabulary:

- Koishi, which uses Cordis as the in-process application framework for a bot
  product;
- DeepSeek Harness, which vendors Cordis as a configuration-driven composition
  runtime for an agent product; and
- LiteyukiBot v7, which borrows selected lifecycle ideas for a supervised Rust
  processor plane.

The shared name must not be mistaken for a shared architecture. Liteyuki does
not embed the Cordis JavaScript framework, does not expose the Koishi Session or
Bot model, and does not adopt Cordis event-chain semantics. This is design
analysis, not a public protocol specification. The versioned specifications
remain authoritative for Liteyuki behavior.

## Summary

| System | Cordis role | Primary audience | Optimized property | Deliberate cost |
| --- | --- | --- | --- | --- |
| Koishi | Bot application framework | Bot/plugin authors in one JavaScript runtime | Fast framework extension | Shared framework-object coupling |
| DeepSeek Harness | Dynamic product composition runtime | Harness maintainers and product plugin authors | Replaceable capabilities and live composition | Runtime topology and lifecycle complexity |
| LiteyukiBot | Bounded processor plane below the kernel | Kernel/runtime maintainers; later, controlled processor authors | Cross-runtime correctness and ownership | IPC, ledger, packaging, and a smaller extension surface |

Koishi and Harness use Cordis as the place where application components meet.
Liteyuki uses the kernel for that role. Its Cordis plane is only one selected
event consumer and cannot decide global routing, own platform credentials, or
address a bot directly.

## Koishi

### Intended users and problem

Koishi targets authors who want to build a bot application and its plugins in
one TypeScript process. A plugin needs direct access to bot sessions, command
registration, database facilities, middleware, and platform abstractions. Its
`Context` extends the Satori context and provides these framework services at
application startup. The plugin model is therefore an ergonomic programming
model for a single bot framework, rather than a transport or ownership model.

### Design choices

- A shared `Context` is both a dependency container and the main extension
  handle.
- Named services are reached through `ctx.<name>` and can participate in
  scoped filtering.
- Session-oriented middleware and typed events form the message-processing
  chain.
- Plugins run in the same process as the framework and can use framework
  objects directly.

### Benefits

- Very low integration friction for a plugin author. A command, middleware,
  database helper, or bot capability can be registered without designing an
  IPC contract first.
- Framework-level scope and session filtering give plugins a natural way to
  target bots, users, channels, or platforms.
- The model supports a large cohesive ecosystem because common abstractions are
  immediately available from the context.

### Costs and failure modes

- The service namespace and the context are application-wide coordination
  points. Plugin behavior is often affected by registrations made elsewhere.
- Framework SDK objects, sessions, and plugin state can cross ordinary plugin
  boundaries. This is productive inside one framework, but it prevents a clean
  protocol-neutral boundary.
- Middleware ordering and short-circuit behavior determine user-visible
  behavior. A plugin can unintentionally change the result of another plugin.
- An in-process lifecycle does not describe delivery acknowledgement, action
  idempotency, restart attribution, or a source runtime's ownership of a
  platform action.

These costs are appropriate for Koishi because its main problem is application
extensibility within one framework. Requiring every plugin feature to cross an
immutable protocol boundary would make its core use case needlessly expensive.

## DeepSeek Harness

### Intended users and problem

DeepSeek Harness targets a modular agent product whose shell, model provider,
tools, storage, user interaction, and UI contributions need to be assembled in
different combinations. Its plugin authors need a stable capability name rather
than a concrete provider import, and its maintainers need a way to replace or
reload parts of a running composition.

### Design choices

- Cordis `Context` is a proxy-backed service repository. Child contexts can
  isolate a service name or intercept its configuration without mutating the
  parent composition.
- A `Fiber` owns one plugin instance, its event listeners, nested plugins, and
  cleanup effects. A disposer unwinds these registrations when the fiber stops.
- `inject` makes a service requirement executable: a consumer remains pending
  until providers exist, and is unloaded if a required provider disappears.
- The loader turns YAML into a plugin tree. Stable entry IDs, groups, isolation,
  and HMR allow incremental reconfiguration.
- Event dispatch mode is part of the contract. In particular, a waterfall
  listener can deliberately wrap or veto downstream behavior.

### Benefits

- The dependency graph, rather than configuration order, determines activation.
  A provider can be replaced without every consumer manually coordinating a
  restart.
- Reversible effects make hot reload materially safer than ad hoc resource
  registration: listeners, timers, and child plugins have an owning fiber.
- Isolation supports multiple instances of a capability, such as separately
  configured shell implementations, within one product composition.
- Explicit dispatch modes make interception behavior more legible than an
  unqualified global event emitter.

### Costs and failure modes

- The effective topology is dynamic. A configuration edit or service change can
  unload and reactivate a transitive set of plugins, making failures non-local.
- A missing injected provider produces a valid pending state. Without fiber
  diagnostics this can look like a plugin silently doing nothing.
- Service names remain a flat dynamic namespace, and TypeScript declaration
  merging provides type safety only when all relevant declarations are imported.
- Waterfall is powerful but hazardous: an observer that forgets to call
  `next()` silently turns into a veto.
- HMR, expression-aware configuration, and arbitrary code plugins improve
  developer speed but enlarge the operational and supply-chain surface.

These costs are acceptable because Harness values live recomposition and works
inside one controlled Node.js product runtime. It has deliberately invested in
fiber diagnostics, generated catalogs, loader validation, and extensive
composition tests to contain that complexity.

## LiteyukiBot v7

### Intended users and problem

Liteyuki is a protocol-neutral kernel supervising independently owned adapter
and framework runtimes. The primary users of the architecture are kernel and
runtime maintainers. Bot/plugin authors remain important users, but they use an
owned runtime, a native plugin API, or a future bounded processor capability;
they are not given a universal mutable application context.

The problem is not merely how to load a plugin. The kernel must retain the
answer to all of the following after processes disconnect or restart:

- Which source runtime produced the event?
- Which route plan applied at admission time?
- Which target accepted a delivery and under which lease?
- Which portable action is authorized to return to the bot owner?
- Whether a duplicate action request must reuse a recorded result?

### Design choices

- The kernel owns immutable event admission, routing, action authorization,
  runtime supervision, and observability.
- The event ledger freezes provenance, payload, route snapshots, delivery
  states, leases, deadlines, terminal outcomes, and action-deduplication
  records. It is transport- and framework-neutral.
- A processor plane is a selected child-runtime consumer. It receives a frozen
  delivery and may submit only protocol-neutral actions while its delivery lease
  is valid.
- Kernel native services use a versioned, startup-oriented registry with one
  provider for each service key. This avoids making dynamic service replacement
  part of the cross-runtime contract.
- The current Rust Cordis package is intentionally closed: it contains a
  compiled catcher manifest, restricted configuration overrides, deterministic
  action correlation IDs, and a bounded action count. It is not a marketplace,
  a general service container, or an HMR host.

### Benefits

- A framework SDK object, credential, adapter connection, or native session
  remains with its owning runtime. Other runtimes observe only frozen envelopes.
- The kernel can make timeout, overload, disconnect, lease, and duplicate-action
  outcomes explicit and attributable. These are requirements that an
  in-process plugin fiber cannot supply by itself.
- Route snapshots prevent a configuration change from retroactively changing
  the meaning of an admitted event.
- Rust processors can be deployed as supervised runtimes without introducing a
  second global routing authority or a framework-specific object model.

### Costs and current limits

- The kernel pays for process startup, IPC, protocol versioning, delivery
  state, deadline handling, wheel packaging, and fault tests. A small feature
  costs more than an in-process Cordis plugin.
- A closed catcher manifest intentionally has much lower ecosystem velocity
  than Koishi or Harness. New behavior requires a first-party release rather
  than loading arbitrary code at runtime.
- Processor code must translate its intent into portable actions. It cannot use
  a platform SDK convenience method directly.
- The ledger only provides bounded in-memory retention. It is not durable
  cross-kernel replay and must not be described as exactly-once delivery.
- The current package-core slice validates and plans catchers, but its Rust
  child executable deliberately cannot bootstrap until the common runtime
  transport loop is implemented. The processor plane is therefore not yet an
  enabled runtime capability.

The costs are acceptable when a processor needs an independently supervised
runtime and the kernel needs a durable-in-memory account of its side effects.
They are not acceptable for simple trusted native behavior, where a Liteyuki
native plugin has less latency, less operational overhead, and an existing
lifecycle surface.

## Architectural Differences That Must Remain Explicit

### Scope is not the same thing as delivery ownership

Cordis scope answers which service implementation a plugin resolves and which
registrations are disposed together. Liteyuki delivery ownership answers which
kernel admitted an event, which target is currently allowed to act, and which
runtime owns the external bot action. Scoped dependency access is useful inside
a processor, but it cannot replace event identity, leases, or kernel action
authorization.

### Lifecycle cleanup is not acknowledgement

Cordis fibers reliably undo owned registrations when a plugin unloads. That is
valuable for local resources, but disposal does not state whether a remote
delivery was accepted, completed, timed out, or retried. Liteyuki must preserve
both models at their respective layers: scoped cleanup inside a processor and
ledger transitions at the runtime boundary.

### Event interception is not routing

Koishi middleware and Harness waterfalls intentionally let locally registered
code order, transform, or veto behavior. Liteyuki route selection must instead
be frozen by the kernel before processor execution. A processor may make a
local decision about its own work, but it may not add targets, bypass the
action owner, or alter the route plan for an already admitted event.

## Decision

Liteyuki should borrow Cordis ideas only where they strengthen a local processor
implementation: explicit dependencies, cleanup ownership, dependency-cycle
validation, and observable lifecycle state. It should not adopt Cordis as the
kernel's universal composition framework.

The resulting division is intentional:

~~~text
native plugin:     trusted in-process behavior with Liteyuki lifecycle
classic runtime:   framework-local behavior with framework lifecycle
Cordis processor:  constrained processing with local scoped cleanup
kernel:            event identity, routing, leases, actions, and supervision
~~~

Adopting a universal `Context` here would create a competing service registry,
event model, plugin lifecycle, and routing vocabulary. It would make Liteyuki
look flexible in the short term while making cross-runtime correctness harder to
prove in the long term.
