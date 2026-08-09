# Native plugin development

Native v7 plugins are trusted packages loaded into the core process. Publish a
`PluginDefinition` through the `liteyukibot.plugins` entry-point group; the
entry-point name and `PluginManifest.id` must be identical.

```toml
[project.entry-points."liteyukibot.plugins"]
"example.echo" = "liteyukibot_example_plugin:plugin"
```

The complete minimal package is in [`examples/native-plugin`](../../examples/native-plugin).
Its setup function subscribes an async handler and returns a stop callback that
removes that subscription. Event handlers return protocol-neutral
`HandlerResult` values containing Actions; adapter objects do not belong in a
native plugin.

Enable an installed plugin explicitly:

```toml
[plugins]
enabled = ["example.echo"]

[plugins.config."example.echo"]
prefix = "answer: "
```

Use only the ownership surfaces supplied by `PluginContext`:

- configuration is read-only;
- services must be declared in the manifest before they are provided or
  required;
- background coroutines are started through `context.tasks.start()`;
- private data/cache paths exist only when `storage = "private"`;
- EventBus subscriptions are removed by the plugin's stop callback;
- replies and API calls use frozen models from `liteyukibot.events`.

## Testing

`PluginTestHarness` uses the production lifecycle and EventBus without importing
pytest:

```python
from pathlib import Path

from liteyukibot.testing import PluginTestHarness
from liteyukibot_example_plugin import plugin


async def verify(event) -> None:
    async with PluginTestHarness(
        plugin,
        root=Path(".test-data"),
        config={"prefix": "answer: "},
    ) as harness:
        result = await harness.publish(event)
        assert result.status == "processed"
        assert len(harness.recorded_actions) == 1
```

Dependency values are supplied with `dependencies={ServiceKey(...): value}`.
Use `require_service()` to inspect a plugin's declared output. An optional
`action_executor` can return real success/failure results; otherwise the harness
records the Action and returns a correlated success.

The harness is single-use and intentionally tests one plugin. Use
`LiteyukiApp` or the kernel components directly for multi-plugin topology and
full configuration tests.
