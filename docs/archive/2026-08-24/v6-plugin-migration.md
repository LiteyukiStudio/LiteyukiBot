# LiteyukiBot v6 Plugin Compatibility

> Historical Alpha source snapshot. The v6 compatibility bridge is retired
> from the v7.0.0 workspace, release, CI, and support surface. Its code is kept
> under `extras/legacy-bridges/runtime-v6` for possible future extraction as an
> independently owned add-on.

`liteyukibot-v7-runtime-v6` is an experimental, limited Broker bridge. It is
not a child runtime and is never configured under `[runtimes.*]`. The bridge
owns the `liteyuki` compatibility namespace inside its own process and sees
only broker-delivered, JSON-safe event envelopes.

## Configure the bridge

The retired bridge was installed and configured as follows:

```toml
[broker.bridges.v6]
kind = "v6"
token_secret = "broker.v6.token"
access = "limited"
subscriptions = ["onebot.*.message.*", "satori.message.*"]

[broker.bridges.v6.options]
v6_plugins = ["my-v6-plugin"]
max_concurrent_events = 32
```

The `v6_plugins` values are entry-point names, not import paths or filesystem
paths. A plugin distribution must declare the selected module in the
`liteyukibot.v6_plugins` group:

```toml
[project.entry-points."liteyukibot.v6_plugins"]
my-v6-plugin = "my_package.plugin"
```

Only explicitly selected entry points are imported. `plugins`, `plugin_dirs`,
managed generations, and historical runtime `config` options fail with a
`migration_required` diagnostic. The bridge does not load arbitrary modules,
plugin directories, or Liteyuki-managed projections.

## Retained surface

- `PluginMetadata`, `PluginType`, and the `liteyuki` logger;
- `get_bot`, empty `get_config`, and lifecycle callbacks;
- `MessageEvent`, `Session`, rules, matcher decorators, priority ordering,
  blocking, and ordered `event.reply()` collection;
- conversion of each reply into the source bridge's ordered `message.send`
  action, using the broker delivery lease and exact `bot:<bridge>:<bot>` owner.

The matcher registry, session objects, and lifecycle callbacks are process
local. A reply action failure is recorded and does not discard later replies.
The broker remains the owner of delivery identity, ordering, leases, and
action routing.

## Removed surface

The bridge does not restore `Channel`, shared memory, adapter objects, object
transport, process-manager APIs, hot reload, `CallApi`, `EditMessage`, or the
old `ActionEnvelope` route. Constructing a nested `LiteyukiBot` and accessing
unsupported `liteyuki` modules raises `LegacyUnsupportedError`.

Calling `python -m liteyukibot_runtime_v6` is also rejected. A restart request
runs the bounded lifecycle cleanup callbacks, unregisters the bridge, and exits
with a restart failure for an external process manager to handle. The broker
does not supervise or restart this bridge.

## Resource functions

Install `liteyukibot-v7-functions` separately for v6 resource packs that use
the legacy `.lyf`, `.lyfunction`, or `.mcfunction` language. The executor
requires explicit API and command capabilities; a resource pack alone cannot
invoke an adapter API or execute a local command.
