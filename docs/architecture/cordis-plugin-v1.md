# Cordis Plugin v1

## Status

This is the accepted Beta6 contract and implementation target. It describes a
Python-first in-process plugin model; it is not a promise of JavaScript Cordis
or Koishi compatibility and does not replace Native Plugin v1.

## Distribution And Discovery

The implementation is the independently buildable `packages/cordis` package,
published as `liteyukibot-v7-cordis`. The root kernel must not import this
package or depend on it in workspace metadata.

The kernel discovers exactly one Cordis host implementation from
`liteyukibot.cordis_hosts`. That host adapts the shared EventBus, ActionService,
logging, and lifecycle without widening Native Plugin v1's `PluginManager`.
The host discovers plugin factories from `liteyukibot.cordis_plugins`.

Cordis is optional. Its root configuration is:

```toml
[cordis]
enabled = ["example.plugin"]
config = { "example.plugin" = { mode = "safe" } }
```

`enabled` contains plugin IDs and `config` is JSON-safe package configuration.
No local executable module loading is part of this contract. Disabled Cordis
must not import or start the host package. A missing or duplicate host is a
configuration error when Cordis is enabled.

## Author API And Lifecycle

A discovered entry point returns a declarative factory receiving `Scope`.
`on`, `parallel`, `middleware`, `route(name, predicate, handler)`, and
`schedule` register the four official composition presets and custom scheduling.
`use` activates a provider on first use and caches it in the scope that owns
that provider.

The manager owns a manager scope, one scope per activated plugin, and a child
scope per event. It detects dependency cycles and closes providers, listeners,
schedulers, tasks, and other disposers in reverse dependency order. Scope
closure is idempotent; event closure cannot unload plugin-owned providers.

## Event, Dispatch, And Audit

`CordisEvent` wraps one immutable `EventEnvelope`, exposed as `event.envelope`.
It never mints a second event identity or mutates the envelope. `CordisSession`
is a scoped lifecycle and action facade, not a framework SDK object.

| Preset | Failure behavior |
| --- | --- |
| Ordered listener | Record failure and stop the current chain. |
| Parallel fanout | Wait for every branch and aggregate results. |
| Waterfall middleware | Record failure and stop the current chain. |
| Directed route | Run matching named routes independently and isolate failure. |

Action failures are dispatch results; no handler or action receives implicit
retries. Custom schedulers run through the host-managed best-effort task
wrapper.

Cordis plugins have full in-process access. Beta6 provides only bounded,
redacted audit records and structured logs for observable operations. It does
not enforce permissions, consult the Permissions package, or add WebUI/CLI
audit queries. Audit records exclude payloads, credentials, and configuration.

## Non-Goals

- JavaScript Cordis/Koishi compatibility or platform Session/Bot objects.
- A Rust/PyO3 runtime, supervised catcher child, or second kernel.
- Permission enforcement, Function DSL, implicit retries, HMR, or marketplace.
