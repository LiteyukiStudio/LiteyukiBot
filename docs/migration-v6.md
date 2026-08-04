# LiteyukiBot v6 Plugin Compatibility

v6 plugins run only inside a `kind = "v6"` child runtime. The `liteyuki`
namespace is a compatibility package; new plugins should import `liteyukibot`.

## Supported

- `PluginMetadata`, `PluginType`, and loaded-plugin metadata;
- Loguru-compatible `liteyuki.logger`, including `opt()`;
- `get_bot`, `get_config`, and `get_config_with_compat`;
- explicit `load_plugin` and non-recursive `load_plugins`;
- before/after startup and shutdown lifecycle decorators;
- process restart requests for the compatibility runtime.

## Unsupported

- constructing a nested `LiteyukiBot`;
- `Channel`, shared memory, and the v6 process-manager APIs;
- session/matcher APIs and implicit cross-process object sharing;
- development hot reload and runtime package installation.

Unsupported host construction raises `LegacyUnsupportedError`. Missing legacy
modules are not recreated as inert stubs: plugin import fails so the migration
gap remains visible. Compatibility also requires every plugin dependency to
support CPython 3.14.

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
