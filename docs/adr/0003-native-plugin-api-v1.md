# ADR 0003: Freeze The Native Plugin API At Version 1

- Status: Accepted
- Date: 2026-08-09

## Context

v7 supports native plugins in the core process while retaining NoneBot and v6
as child-runtime compatibility paths. The native surface must be explicit,
dependency ordered, and safe to clean up after partial startup.

## Decision

Native discovery uses the `liteyukibot.plugins` entry-point group and explicitly
listed local module names. Entry points must resolve to `PluginDefinition`.
Local modules expose either `plugin` or `get_plugin()`. No recursive directory
scanning or import-time registration is part of the native API.

`PluginDefinition` contains a `PluginManifest` and an async
`setup(context)` callable. The v1 manifest contains:

| Field | Contract |
| --- | --- |
| `id` | Lowercase ASCII letters, digits, `-`, `_`, and `.`; dotted segments cannot be empty. |
| `name`, `version` | Non-blank metadata. |
| `api_version` | Literal `1`. |
| `provides`, `requires` | `ServiceKey` and `ServiceRequirement` declarations. |
| `storage` | `none` or `private`. |

Unknown manifest fields are rejected. A `setup` function returns `None` or a
`PluginHandle` with optional async `start` and `stop` callbacks.

`PluginContext` supplies the immutable plugin configuration, bound logger,
event bus, action service, `PluginServices`, managed tasks, and optional private
data/cache paths. A plugin may provide or require only services declared in its
manifest. Services use `name@major` keys, have exactly one provider, and form a
startup dependency graph. Missing required services, conflicting providers, and
cycles are startup errors.

Setup occurs in dependency order. Stop callbacks and managed task cleanup occur
in reverse dependency order, including after partial startup. If setup fails,
services already provided by that plugin are removed and its tasks are stopped.
Task failures are reported through the plugin-bound logger.

## Consequences

Plugins are trusted in-process code, not sandboxed code. They own only declared
private paths and should use managed tasks instead of untracked background work.

Changing the manifest shape, context surface, lifecycle ordering, or service
semantics requires a new plugin API version. A v1 core must reject unsupported
future manifests rather than guessing compatibility.
