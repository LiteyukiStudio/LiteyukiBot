# Modules and Libraries

## `use` declaration

The grammar is:

```text
use-declaration = "use", namespace, [ "@", provider ] ;
```

Examples:

```lyf
use terminal@core
use agent@liteyukibot-v7-agent
use async@core
```

The provider may be omitted only when exactly one installed Provider exports
the requested namespace. If zero or multiple Providers match, preflight fails
and the source must add an explicit provider.

`core` is a reserved built-in Provider. Provider names identify installed
entry-point metadata, not a PyPI download request. Runtime package installation,
network resolution and arbitrary Python imports are outside LYF.

## Namespaces

After a `use`, an export is accessed through its namespace:

```lyf
terminal.echo("hello")
await async.sleep(1)
```

The namespace is not a Python module. Only exports declared by the selected
Provider are visible. An undeclared export is a preflight error even if a
Python attribute with that name happens to exist.

## Resource-pack ownership

Functions are loaded only from `functions/` inside an installed and enabled
Native or Cordis extension resource pack. A loose workspace pack listed only by
`resources/index.json` is not executable in Alpha 7 unless the host explicitly
binds it to an enabled extension.

Function IDs are local to one owning resource pack. Cross-pack behavior goes
through a declared Library or a host service; LYF does not perform implicit
cross-plugin function lookup.

## Preflight

The host parses every selected function before accepting events. It resolves all
`use` declarations, validates exported Tool and event metadata, and builds the
static contribution list. A runtime must fail startup rather than defer a
missing Provider or malformed declaration to the first event.
