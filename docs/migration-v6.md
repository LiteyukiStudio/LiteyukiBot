# LiteyukiBot v6 Plugin Compatibility

v6 plugins run only inside a `kind = "v6"` child runtime. The `liteyuki`
namespace is a compatibility package; new plugins should import `liteyukibot`.

## Supported

- `PluginMetadata`, `PluginType`, and loaded-plugin metadata;
- Loguru-compatible `liteyuki.logger`, including `opt()`;
- `get_bot`, `get_config`, and `get_config_with_compat`;
- explicit `load_plugin` and non-recursive `load_plugins`;
- before/after startup and shutdown lifecycle decorators;
- process restart requests for the compatibility runtime;
- `MessageEvent`, session identity models, composable rules, matcher decorators,
  stable priority dispatch, and synchronous reply-intent collection.

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
intent; it does not send through a v6 Channel. Runtime event delivery and reply
Action translation are introduced separately so plugins cannot observe a
partially emulated cross-process object.

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

[runtimes.legacy.options.config]
nickname = ["Liteyuki"]
```
