# Native plugin development

Native v7 plugins are trusted packages loaded into the core process. Publish a
`PluginDefinition` through the `liteyukibot.plugins` entry-point group; the
entry-point name and `PluginManifest.id` must be identical.

```toml
[project.entry-points."liteyukibot.plugins"]
"example.echo" = "liteyukibot_example_plugin:plugin"
```

The complete minimal package is in [`examples/native-plugin`](../../examples/native-plugin).
Its setup function subscribes an async handler and registers the matching
unsubscription through `context.defer_cleanup()`. Event handlers return protocol-neutral
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
- EventBus subscriptions and other registrations use `context.defer_cleanup()`;
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

## Kernel status

Plugins that need operational state declare the versioned kernel service rather
than importing or retaining `LiteyukiApp`:

```python
from typing import cast

from liteyukibot import KERNEL_STATUS_SERVICE, KernelStatusProvider

provider = cast(
    KernelStatusProvider,
    context.services.require(KERNEL_STATUS_SERVICE),
)
snapshot = provider.snapshot()
```

Add `ServiceRequirement(KERNEL_STATUS_SERVICE)` to the plugin manifest before
requiring it. Snapshots are immutable and contain only kernel version, state,
uptime, plugin/runtime states, and outstanding event count. Presentation and
access policy belong to the consuming plugin.

## Permissions

The first-party `liteyukibot-v7-permissions` package provides
`liteyukibot.permissions@1`. Consumers import `PERMISSION_SERVICE` and
`PermissionService` from `liteyukibot_permissions`, declare the service in
their manifest, and call `allows(event, permission)`.

The alpha implementation maps exact runtime, bot, and actor principals to
static named roles and exact capability tokens configured under
`plugins.config."liteyukibot.permissions"`. Every event has `public`;
`resolve(event)` exposes a frozen diagnostic snapshot and unknown capabilities
are denied. Plugins check capabilities rather than deployment role names. The
service is application policy for trusted plugins; it is not a sandbox
boundary.

## Commands

The first-party `liteyukibot-v7-commands` package provides
`liteyukibot.commands@1`. A consumer declares `COMMAND_SERVICE`, resolves a
`CommandService`, and registers `CommandSpec` plus a synchronous or asynchronous
handler. The handler receives `CommandInvocation` and returns the kernel's
`HandlerResult`; `invocation.reply()` builds a correlated `SendMessage` result.
The invocation also exposes the actual matched `prefix`, the canonical command
name, the alias used, and unparsed argument text. Attach an explicit
`CommandSchema` to the spec and call `invocation.parse()` for shared quoting,
positionals, options, flags, repeatable values, and typed conversion. Handler
annotations are not inspected.

Registrations are explicitly owned and must be unregistered in the consumer's
stop callback. `register_many()` is atomic, so a duplicate name or alias leaves
the previous registry unchanged. Raw argument text is always retained.
Hierarchical subcommand routing and schema-backed help are supported by
`CommandSpec(path=("parent",))`; aliases apply only to the final segment.
Essentials renders visible root commands and `/help <path>` details. Parse
errors are converted to short localized usage messages without exposing
converter exceptions.

## Resources and Profiles

`liteyukibot-v7-resources` provides the optional
`liteyukibot.resources@1` declaration layer. A resource spec defines a stable
path and named fields; a provider keeps ownership of its data, transactions,
schema migrations, and validation. Resources generate three commands through
the command service: `<path>`, `<path> set <field> <value>`, and
`<path> delete <field>`. Direct command registrations remain valid when this
convention does not fit a plugin.

The event actor is the target principal by default. `--actor <id>` requests an
operation for another actor in the same runtime and bot; it is denied unless
that field explicitly declares the capability for the requested operation.
Resources never permit overriding runtime or bot identity, and cross-principal
access is fail-closed.

`liteyukibot-v7-profile` is the reference business plugin. It stores nickname
and language under the exact `(runtime_id, bot_id, actor_id)` key in its private
SQLite database and provides `liteyukibot.profile@1`. It has no kernel database
dependency. Consumers may declare the profile service as optional, as
Essentials does for per-user language, and must preserve a documented fallback
when profile is not enabled or cannot be read.

## Essentials

`liteyukibot-v7-essentials` is a consumer plugin, not a kernel feature. It
registers public `help`/`帮助` and capability-protected `status`/`状态`, renders
only protocol-neutral text, and provides no service. Status requires
`liteyukibot.status.read`. Enable permissions and commands before essentials in
deployment configuration. Help filters registrations through the command
service for the current event; status reads the immutable kernel status
provider.

The `language` setting accepts `zh-CN` or `en`. When the optional profile
service is enabled and has a valid value for the event principal, Essentials
uses it; anonymous events, missing profile, and lookup failures use the static
setting. This dictionary is intentionally local to the package and does not
define a localization API for other plugins.
