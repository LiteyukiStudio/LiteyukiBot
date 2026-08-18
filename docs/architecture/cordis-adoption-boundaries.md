# Cordis Adoption Boundaries

## Decision

Liteyuki adopts Cordis as the design basis for a Python, in-process plugin
framework. It does not embed or claim compatibility with the JavaScript Cordis
or Koishi plugin ecosystems. Koishi compatibility belongs to a separately
owned Classic runtime bridge.

Cordis and Native Extension API v2 intentionally coexist. Native is the small,
limited explicit surface. Cordis is the full-access
composition surface for authors who need scopes, dynamic dependency activation,
fiber-owned cleanup, and richer event composition.

## Kernel And Broker Boundary

The kernel remains the Liteyuki framework and IPC definition. It is not a
plugin and it is not normally a framework runtime's parent process. A
standalone broker owns bridge registration, directed subscriptions, event
identity, ledger state, and diagnostics. Framework hosts own their own
lifecycle and load a bridge through their native plugin API.

The broker retains authority over cross-process identity and delivery state. A
Cordis plugin may alter in-process event behavior but must not forge broker
event identity or bypass an action-owning bridge.

## Accepted Plugin Model

- Python Cordis plugins run in-process with full host access. Their risk is a
  deployment choice, not a sandbox claim.
- Native Plugin v1 and Cordis Plugin v1 have equal in-process event-semantic
  authority. Neither is a subordinate processor class.
- The framework supplies ordered listener, parallel fanout, waterfall
  middleware, and directed route as composable presets. Third-party custom
  schedulers are allowed.
- A custom scheduler is run through a host-managed task wrapper so cancellation,
  exceptions, and terminal results have a common best-effort boundary. Internal
  topology and metrics remain optional for third parties.
- Scoped dependencies, reversible registration, and deterministic fiber cleanup
  are required Cordis lifecycle concepts.

## Access And Governance

`full` and `limited` describe technical access, not event priority or plugin
quality. Native extensions are limited by Permissions v2 capability ceilings;
Cordis is full by default and may only be administratively downscoped through
`[cordis.access]`. This is an in-process host boundary, not a malicious-Python
sandbox. Limited is also enforceable for isolated runtime/bridge peers through
their authenticated manifests.

`stable-first` is independent governance. First-party packages and paths marked
stable are release gates. Third-party packages may state their own stability,
but do not create a Liteyuki compatibility commitment.

## Rejected Directions

- A Rust-only, closed catcher runtime as the public Cordis extension model.
- Treating a Python API wrapper as a security sandbox.
- Direct framework-object transfer or runtime-to-runtime sockets.
- Requiring third-party custom schedulers to expose first-party-grade metrics.
- Treating existing Koishi plugins as Cordis Plugin v1 inputs.

## Delivery Sequence

Beta5 establishes broker/bridge Runtime IPC v6 and ledger ownership. Beta6
implements Cordis Plugin v1 alongside Native Plugin v1. Beta7 delivers the
bridge SDK and stable AstrBot/NoneBot2 paths. The prior Rust catcher work is a
design spike and may supply reusable transport or diagnostic evidence only.

## Beta6 Package Boundary

Beta6's accepted implementation is the independent Python package
`liteyukibot-v7-cordis` under `packages/cordis`. The root kernel may define a
small host protocol, but it must not import this package or add it as a
workspace dependency. The package is discovered through:

- `liteyukibot.cordis_hosts` for the one host implementation that adapts
  Cordis to the kernel EventBus and ActionService; and
- `liteyukibot.cordis_plugins` for declarative plugin factories.

The root `[cordis]` section is limited to an `enabled` plugin-ID list and a
JSON-safe `config` object. Package discovery is disabled when Cordis is
disabled. Missing or duplicate host implementations are configuration errors.

The former `packages/runtime-cordis` Rust/PyO3 catcher package was rejected
and removed from the workspace and release metadata. Its temporary Beta6 plan
is historical evidence only; it is not a compatibility target.

## Beta6 Composition And Scope

Cordis Plugin v1 provides four official presets: ordered listener, parallel
fanout, waterfall middleware, and directed route. A public custom scheduler is
also accepted, but it always runs through the host-managed best-effort task
wrapper. The fixed failure contract is:

- ordered and waterfall stop the current chain after recording failure;
- parallel waits for every branch and aggregates results;
- directed routes isolate failures per matching named route; and
- action failure is a result, not an implicit retry.

Plugins return a factory that registers handlers and dependencies against a
`Scope`. The manager owns a manager scope, plugin scopes, and per-event child
scopes. `use` activates and caches dependencies in the scope that owns the
provider, detects cycles, and closes providers and registrations in reverse
dependency order.
Scope closure is idempotent; topology changes affect only that scope.

`CordisEvent` retains the original immutable `EventEnvelope` as its sole event
identity. `CordisSession` is a lifecycle and action facade; it is not a second
platform SDK object and cannot forge broker identity or bypass the action owner.

Cordis remains full access by deployment choice. Beta6 has no permission
enforcement or per-plugin permission matrix. Its audit service records plugin
identity, scope/event identity, operation, outcome, duration, and error type
with bounded retention and redaction. It does not record payloads, enforce
denials, depend on the Permissions package, or add a WebUI/CLI surface; those
are later diagnostics work.
