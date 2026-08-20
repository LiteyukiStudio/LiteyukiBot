# Liteyuki Function Language

> Alpha 7 implementation contract. The runtime is under validation and is not
> released as a stable compatibility promise yet.

Liteyuki Function Language (LYF) is a small resource-pack language for short
glue code. A LYF file belongs to the Native or Cordis extension that owns its
resource pack. It inherits that extension's identity, permissions and
lifecycle; it is not a PluginDefinition and it is not an independent bridge.

Use LYF for small event handlers, data shaping, prompt presets and declared
Agent Tools. Keep stateful business logic, platform SDKs, complex algorithms
and privileged operations in Python. LYF can call only installed,
configuration-declared Function Libraries.

## Minimal shape

```lyf
@version 1.0

use terminal@core

const greeting = "hello"

fn greet(name) {
    terminal.echo("{greeting}, {name}")
    return {"message": "{greeting}, {name}"}
}
```

The canonical file extension is `.lyf`. `.liteyukifunction` and
`.liteyukifunctions` are equivalent aliases. Historical `.lyfunction` and
`.mcfunction` files are rejected with a migration diagnostic.

## Document map

- [Lexical structure](lexical.md): file header, comments, identifiers and
  literals.
- [Modules and Libraries](modules.md): `use`, Provider resolution and resource
  pack ownership.
- [Bindings and values](bindings.md): `let`, `val`, `const`, assignment and
  destructuring.
- [Functions and calls](functions.md): `fn`, `async fn`, calls, returns and
  `await`.
- [Decorators](decorators.md): Agent Tools, prompt presets and event handlers.
- [Library contract](libraries.md): Python-provided namespaces and core APIs.
- [Host and runtime](runtime.md): Native/Cordis lifecycle and Broker boundary.
- [Diagnostics](diagnostics.md): source spans, stable codes and editor data.
- [v6 migration](migration-v6.md): removed extensions and instructions.

## Alpha 7 execution status

The following are executable in Alpha 7: `use`, JSON-safe values, strict
bindings, function declarations, calls, returns, tuple destructuring, `await`,
`@agent` and `@events`.

Loops, `terminal.exec`, `sync fn`, C-style `for`, implicit shell access,
`api`, `cmd`, `nohup`, `eval`, arbitrary imports and unsupported control flow
may be recognized for diagnostics but are not executed.
