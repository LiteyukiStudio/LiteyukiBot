# LiteyukiBot v7 Functions

This package contains the Alpha 7 Liteyuki Function Language (LYF) parser,
immutable AST, diagnostics, static preflight and bounded evaluator. It is a
host-neutral library: Native and Cordis hosts may create a
`FunctionRuntime` without importing the old Kernel Function Dispatcher.

The new `.lyf` language is deliberately small. It supports `@version`,
`use`, JSON-safe values, strict bindings, function calls, `return`, `await`,
and static `@agent`/`@events` contributions. Loops, `terminal.exec`, `sync
fn`, v6 line instructions and arbitrary Python or shell access are represented
as diagnostics and never executed.

The previous v6 executor remains in `executor.py` as a separately maintained
compatibility asset. New code uses:

```python
from liteyukibot_functions import FunctionRuntime, parse, preflight

parsed = parse(source, source_id="pack:functions/main.lyf")
checked = preflight(parsed, extension_id="example")
runtime = FunctionRuntime(checked)
result = await runtime.invoke("greet", {"name": "Liteyuki"})
```

Function Libraries are explicit `LibraryDefinition` values selected by
`use namespace@provider`; they never expose arbitrary Python modules. Tool,
prompt and event metadata is collected by preflight before a host accepts
events.

## Development

Preserve the explicit Library capability boundary; function files must not
gain implicit shell or adapter access. Run
`uv run pytest packages/functions/tests` and
`uv run ruff check packages/functions` after changes. The old installation
verifier remains useful for the compatibility executor, but Alpha 7 parser
tests are intentionally independent of Kernel integration.
