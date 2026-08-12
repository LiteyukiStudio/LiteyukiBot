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

## Resource packs and functions

Plugins may declare packaged static resources without implementing a service:

```python
from liteyukibot import PluginManifest, ResourcePackDeclaration

manifest = PluginManifest(
    id="example.echo",
    name="Example",
    version="1.0.0",
    resource_packs=(ResourcePackDeclaration("liteyukibot_example_plugin"),),
)
```

The declared package root defaults to `resources/` and must contain
`metadata.yml`. Declare a pack only when the plugin has visible text, static
assets, or future control-plane presentation. Use package `lang/en-US.lang`
and `lang/zh-CN.lang` catalogs for visible text; declare `I18N_SERVICE` and
resolve text through the injected `Translator`, never a package-local Python
dictionary. Prefix keys with the plugin ID, for example `example.echo.name`.

`metadata.yml` may contain `name_key`, `description_key`, and `icon`. The icon
is package-relative, local-only `icon.png`: a transparent square PNG no larger
than 512 KiB. Resource metadata and `ResourceCatalog.icon()` form a read-only
future WebUI interface; v7 does not yet expose an HTTP asset route or WebUI.
Enabled plugin packs overlay kernel resources but are overridden by workspace
packs. Declare `RESOURCE_CATALOG_SERVICE` when a plugin needs to read the
resolved catalog.

`FUNCTION_DISPATCH_SERVICE` resolves read-only files under `functions/` and
dispatches them to a separately installed executor registered through
`liteyukibot.function_executors`. `liteyukibot-v7-functions` is the first
executor and supports only the v6 `.lyf`, `.lyfunction`, and `.mcfunction`
language. The kernel intentionally provides no function language or
command-execution capability; an unavailable executor raises an explicit error.

The v6 `api` and `cmd` instructions remain capability-gated. A caller must
explicitly supply the adapter API or command runner it intends to authorize;
resource packs never gain API access, Python evaluation, or shell execution
merely by being discovered.

Function source is cached for the lifetime of its dispatcher, matching the
read-only resource-pack contract. Restart the application or construct a new
dispatcher after changing a workspace function file.

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

Kernel-owned privileged capability names are defined in `liteyukibot.capabilities`.
In beta1, a child-originated `CallApi` action requires
`liteyukibot.adapter.call_api`, a v4 source-event provenance record, and an
enabled permission service. `SendMessage` remains protocol-neutral and uses its
existing event/runtime/bot routing checks.

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
