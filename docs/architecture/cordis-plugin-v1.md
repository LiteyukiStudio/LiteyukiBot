# Cordis Plugin v1

Cordis is the only Alpha15 extension system. It is a trusted in-process Python
composition layer over the kernel EventBus and ActionService.

## Public Surface

`Scope` provides `child`, `provide`, `use`, `own`, `on` and `aclose`.
`CordisManager` provides `activate`, `start`, `dispatch` and `aclose`.
Providers are lazy, scoped and cycle-checked. Concurrent requests share one
provider resolution. Owned resources close in reverse order. Ordered event
handlers stop after the first failure and report it through `DispatchResult`.

The manager activates the built-in feature chain in this order:

1. permissions
2. commands
3. resources
4. profile
5. essentials

These features are part of the root distribution and are not independently
published or optional.

## Third-Party Discovery

Configured plugin IDs are loaded from the `liteyukibot.cordis_plugins` entry
point group. Only IDs listed in `[cordis].enabled` are loaded, in configuration
order. Missing, duplicate or non-callable entries fail startup. Each factory
receives one child scope and its JSON-safe `[cordis.config.<id>]` table.

There is no separate Cordis host entry point, native delegation, manifest
layer, scheduler, middleware, parallel fanout, runtime API or hot reload in
Alpha15.
