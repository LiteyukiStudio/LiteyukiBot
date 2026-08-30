# Cordis Plugin v1

Cordis is the only Alpha15 extension system. It is a trusted in-process Python
composition layer over the kernel EventBus and ActionService.

## Public Surface

`Scope` provides `child`, `provide`, `use`, `own`, `on` and `aclose`.
`CordisManager` provides `activate`, `start`, `dispatch` and `aclose`.
Providers are lazy, scoped and cycle-checked. Concurrent requests share one
provider resolution. Owned resources close in reverse order. Ordered event
handlers stop after the first failure and report it through `DispatchResult`.
Factories may be synchronous or asynchronous, but ordered event handlers are
async-only and are rejected at registration if they are synchronous.
Owned disposers and resources exposing `aclose` or `close` must be async
callables as well. Synchronous cleanup is rejected at the scope boundary.

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
Configuration tables must be present only for enabled plugin IDs. Each plugin
factory owns validation of its table and should fail activation before
registering handlers or resources when the table is invalid.

The CLI plugin index uses schema 2 metadata. A current bundle declares its
PyPI distribution as `project_id` and its entry-point names in the selected
Cordis facet's `load.entry_points` array. The CLI verifies the wheel bytes,
installs it into the current Python interpreter with `uv pip`, and then checks
that those entry points belong to the declared distribution. Bundle metadata
and local activation state are managed by the host CLI only; adapter commands
cannot install, enable, disable, remove, or configure plugins.

There is no separate Cordis host entry point, native delegation, manifest
layer, scheduler, middleware, parallel fanout, runtime API or hot reload in
Alpha15.
