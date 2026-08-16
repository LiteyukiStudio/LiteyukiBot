# Cordis Adoption Boundaries

## Purpose

This document turns the comparison in
[Cordis Design Comparison](cordis-design-comparison.md) into implementation
criteria. It prevents two opposite mistakes:

- rejecting all Cordis ideas because the JavaScript framework itself is not
  embedded; and
- importing a general-purpose Cordis plugin model into a kernel that has
  different ownership and reliability requirements.

## Accepted Ideas

### Scoped local dependencies

A future Cordis processor may make catcher dependencies explicit and validate
them before activation. The scope is local to that processor instance. It must
not expose kernel services, runtime SDK objects, credentials, or another
runtime's object graph.

**Why:** local dependencies make cleanup and configuration validation easier to
reason about.

**Cost:** processor authors need explicit capability declarations and cannot
reach arbitrary application state.

**Acceptance:** acceptable. The restriction is the point of the processor
plane, not an accidental limitation.

### Reversible registration and deterministic cleanup

Every processor-owned registration, timer, child task, or resource must have a
single owner and a defined cleanup path. Cleanup must run when a catcher is
disabled, the processor stops, or its delivery lease expires.

**Why:** this imports the strongest part of the Fiber/effect model without
giving local code authority over global runtime state.

**Cost:** resource acquisition must be structured, and shutdown paths need
focused tests.

**Acceptance:** required for a non-trivial processor. It should remain an
internal Rust lifecycle contract rather than a second public plugin framework.

### Explicit execution and completion modes

Each route must state whether delivery is required or best effort and whether
the kernel waits for synchronous completion. A processor may internally define
ordered catchers, but its external completion must use the common runtime
protocol and ledger state machine.

**Why:** this retains the useful Cordis lesson that dispatch semantics are part
of the contract, while preserving a single kernel source of truth.

**Cost:** route and protocol schemas become more detailed; feature work cannot
skip failure-state design.

**Acceptance:** required. The event ledger already provides the correct
ownership point.

### First-class diagnostics for inactive work

Harness demonstrates that a valid pending dependency can otherwise appear as a
silent failure. Liteyuki should expose redacted diagnostics for disabled
catchers, invalid manifests, missing local dependencies, rejected deliveries,
expired leases, and terminal route outcomes.

**Why:** a constrained architecture must remain operable, not merely correct in
source code.

**Cost:** diagnostic state consumes bounded memory and requires a stable
redaction policy.

**Acceptance:** acceptable and necessary. Retention must remain bounded; a
diagnostic plane must not become unbounded event storage.

## Rejected Ideas

### A universal mutable context

Liteyuki must not add a cross-runtime equivalent of `ctx.<service>`. A global
context would duplicate the native service registry, tempt runtimes to exchange
framework objects, and blur whether an operation is local, kernel-authorized,
or platform-owned.

**Rejected cost avoided:** non-local behavior caused by dynamic registrations
and loss of protocol-neutral boundaries.

### Runtime-to-runtime direct dependencies

A processor cannot inject a Classic runtime, an adapter, a bot object, or a
credential provider. It submits an action to the kernel, which validates and
routes it to the action owner.

**Rejected cost avoided:** a process graph whose failures, authorization, and
restart behavior cannot be attributed to the kernel.

### Arbitrary third-party catchers and a runtime marketplace

The Cordis processor must not become a generic dynamically loaded plugin host
until it has a separately designed trust, packaging, compatibility, and
revocation model. Compiled first-party catchers with restricted configuration
are the present boundary.

**Rejected cost avoided:** treating child-process isolation as a security
sandbox, unbounded supply-chain exposure, and an unsupported extension ABI.

### HMR as a production control plane

HMR is valuable for a Node.js product composition where live replacement is a
primary feature. It is not a substitute for an event ledger in a bot kernel.
Reloading a processor while deliveries are active would require explicit lease
termination, route behavior, action deduplication, and recovery semantics.

**Rejected cost avoided:** silent or ambiguous in-flight work during live code
replacement.

Development-only restart tooling may exist, but it must use the same supervisor
and terminal-state transitions as any other runtime restart.

### Waterfall as a global routing mechanism

Local interception can be useful inside a single processor, but no processor
may veto, reorder, or retarget another processor's delivery. The kernel freezes
the route plan at event admission and aggregates the terminal outcomes.

**Rejected cost avoided:** behavior depending on plugin registration order and
an unclear authority to suppress another runtime's work.

## Cost Assessment

| Cost | Koishi/Harness accept it because | Liteyuki position |
| --- | --- | --- |
| Shared mutable context | One process is the product boundary | Reject across runtime boundary |
| Dynamic provider replacement | Live composition is a product feature | Reject for kernel services; consider only processor-local replacement with explicit teardown |
| HMR | Developer/product iteration speed | Reject as a production protocol feature |
| Arbitrary code plugins | Ecosystem and deployment flexibility | Reject for Cordis until a separate trust model exists |
| Typed in-process event chains | Components share one runtime and object model | Keep only inside an owner; do not use for kernel routing |
| IPC and delivery ledger | Usually unnecessary in one process | Accept where independently supervised runtimes must cooperate |
| Restricted manifest and action set | Limits extension velocity | Accept initially to prove correctness before broadening capability |

## Admission Criteria For New Cordis Capability

A proposed Cordis catcher or processor feature is admissible only when all of
the following are true:

1. It cannot be implemented more simply as a trusted native Liteyuki plugin or
   as framework-local behavior in the owning Classic runtime.
2. Its input is a frozen, JSON-safe delivery and its output is a portable,
   kernel-authorized action or an explicit terminal result.
3. It declares bounded resource use, action limits, timeout behavior, and
   cleanup ownership.
4. It has no direct adapter, bot, credential, or cross-runtime object access.
5. Its configuration is declarative, validated, and unable to load arbitrary
   executable extensions.
6. Failure, overload, lease expiry, duplicate action, and restart behavior are
   specified and tested through the common runtime protocol.
7. Its diagnostics expose only redacted state and fit the ledger retention
   limits.

Failure to satisfy any item is evidence that the capability belongs in a native
plugin, a Classic runtime, or a separately designed extension system, not in
the Cordis processor plane.

## Implementation Sequence

The current order remains deliberate:

1. Keep the kernel ledger and route semantics authoritative.
2. Complete one minimal supervised processor path using the common child
   runtime transport.
3. Prove acceptance, completion, timeout, restart, ordering, and
   duplicate-action behavior with focused tests.
4. Add local catcher lifecycle features only after the runtime boundary is
   proven.
5. Reconsider a broader extension surface only with an explicit trust and
   compatibility proposal.

This sequence pays the reliability cost before expanding developer ergonomics.
That is the opposite ordering from an application framework, and it is correct
for Liteyuki's role as a multi-runtime kernel.
