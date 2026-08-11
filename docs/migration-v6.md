# LiteyukiBot v6 Plugin Compatibility

v6 plugins run only inside a `kind = "v6"` child runtime. Install
`liteyukibot-v7-runtime-v6` to provide the `liteyuki` compatibility namespace;
new plugins should import `liteyukibot`.

## Supported

- `PluginMetadata`, `PluginType`, and loaded-plugin metadata;
- Loguru-compatible `liteyuki.logger`, including `opt()`;
- `get_bot`, `get_config`, and `get_config_with_compat`;
- explicit `load_plugin` and non-recursive `load_plugins`;
- before/after startup and shutdown lifecycle decorators;
- process restart requests for the compatibility runtime;
- `MessageEvent`, session identity models, composable rules, matcher decorators,
  stable priority dispatch, and synchronous reply-intent collection;
- supervised delivery of normalized message events and ordered string or
  mapping replies through protocol-neutral Actions.

## Unsupported

- constructing a nested `LiteyukiBot`;
- `Channel`, shared memory, and the v6 process-manager APIs;
- session `receive_channel` and implicit cross-process object sharing;
- development hot reload and runtime package installation.

Unsupported host construction raises `LegacyUnsupportedError`. Missing legacy
modules are not recreated as inert stubs: plugin import fails so the migration
gap remains visible. Compatibility also requires every plugin dependency to
support CPython 3.14.

Session matchers are process-local. `event.reply()` records an ordered reply
intent; it does not send through a v6 Channel. The v6 runtime translates each
intent after matcher dispatch and waits for its Action result before submitting
the next reply. Handler, reply validation, and Action failures are isolated from
later replies.

Only events with normalized message content are forwarded by the application
bridge. `MessageEvent.data` is a deep JSON copy of the adapter event's raw
payload; no adapter object or synthetic `Session` crosses into the plugin.

Supported matcher constructors are `on_message`, `on_keywords`,
`on_startswith`, `on_endswith`, and `on_fullmatch`. Larger numeric priorities
run first as in v6; a matching blocking matcher stops lower priorities after all
matchers at its own priority have run.

Configure modules and directories explicitly:

```toml
[runtimes.legacy]
kind = "v6"

[runtimes.legacy.options]
plugins = ["my_legacy_plugin"]
plugin_dirs = ["plugins"]
max_concurrent_events = 32
action_timeout_seconds = 10.0

[runtimes.legacy.options.config]
nickname = ["Liteyuki"]
```
