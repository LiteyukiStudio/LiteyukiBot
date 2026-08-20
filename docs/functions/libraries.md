# Function Library Contract

Function Libraries are installed Python packages that expose small, explicit
operations to LYF. They are not LYF plugins and they do not grant the language
general Python access.

## Entry point

Libraries use the `liteyukibot.function_libraries` entry-point group. A
Provider returns a host-neutral definition containing:

```text
namespace
provider
version
exports: name -> (input_schema, output_schema, async, capabilities, callback)
```

The host validates namespace/provider identity, duplicate exports, JSON schemas,
capability names and callback contracts before making the Library visible.
Callbacks receive JSON-safe arguments and a restricted FunctionContext. They
must return JSON-safe data or an awaitable JSON-safe result.

Libraries must not import or expose arbitrary modules through a dynamic name.
An export is callable only when it appears in the selected Provider manifest.

## Core Provider

`core` is installed with the Function runtime and has no platform SDK access.
The initial namespaces are:

- `terminal.echo(value)` and `terminal.print(value)`: bounded structured log
  output; neither starts a process or writes an arbitrary file.
- `async.sleep(seconds)`: awaitable delay in seconds, subject to the active
  host deadline; unit constants and hour/minute conversion are deferred.
- `agent.prompt.select(preset_id)`: available only while an authorized Agent
  Tool is executing; requests a registered preset through the current Broker
  delivery and never accepts raw prompt content.

Additional core exports require an explicit contract and tests. `terminal.exec`,
shell commands, adapter APIs and Python evaluation are not core exports.

## Provider resolution

`use namespace@provider` selects one installed Provider. `use namespace` is
accepted only when resolution finds exactly one Provider. A missing Provider,
ambiguous Provider or incompatible version is a startup diagnostic.

The runtime never downloads packages, imports a user-selected dotted path or
falls back to an older Provider version.
