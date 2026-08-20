# Diagnostics

Every parse, preflight and runtime failure has a stable code and a source span.
The public diagnostic shape is:

```json
{
  "code": "LYF_PARSE_UNEXPECTED_TOKEN",
  "severity": "error",
  "message": "expected a function name",
  "source": "example:functions/main.lyf",
  "span": {
    "start": {"offset": 12, "line": 3, "column": 4},
    "end": {"offset": 17, "line": 3, "column": 9}
  }
}
```

Offsets are zero-based source character offsets using the host parser's Unicode
string indexing. Lines and columns are one-based. An editor adapter may convert
the span to its own UTF-16 or byte indexing convention.
Messages are bounded and must not contain absolute paths, credentials,
exception tracebacks or raw prompt contents.

## Code families

- `LYF_VERSION_UNSUPPORTED`: missing or unsupported `@version`.
- `LYF_PARSE_*`: lexical or grammar failure.
- `LYF_UNSUPPORTED_SYNTAX`: recognized future syntax that is not executable.
- `LYF_BINDING_*`: duplicate, missing or immutable binding errors.
- `LYF_PROVIDER_*`: missing, ambiguous or mismatched Library Provider.
- `LYF_LIBRARY_*`: invalid export, capability or callback contract.
- `LYF_TOOL_*`: invalid decorator, ID collision or schema mismatch.
- `LYF_EVENT_*`: invalid topic, filter or handler signature.
- `LYF_PROMPT_*`: non-static, oversized or malformed preset.
- `LYF_RESOURCE_*`: unowned, disabled or conflicting resource pack.
- `LYF_RUNTIME_*`: timeout, cancellation, depth, JSON or host execution error.
- `migration_required`: historical v6 syntax or Function Dispatcher usage.

Editors may treat unsupported syntax as an error for execution and as a
structured feature marker for highlighting. Hosts must not silently downgrade
an error to a warning.
