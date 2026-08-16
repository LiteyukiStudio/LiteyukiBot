# Examples

Examples are small installable packages that exercise public extension points.
They are not templates copied into production unchanged.

- `native-plugin/` demonstrates a native plugin entry point, EventBus cleanup,
  and protocol-neutral replies.
- `custom-runtime/` preserves a protocol-v5 child-runtime example using the
  shared `RuntimeClient` and supervisor-owned lifecycle. It is not a B5 broker
  peer example; a broker-peer integration has not been implemented yet.

Keep examples minimal, dependency-bounded, and aligned with the public guides
in `docs/development/`. Build them from the repository root:

```bash
uv build --project examples/native-plugin --out-dir dist/examples
uv build --project examples/custom-runtime --out-dir dist/examples
```

When a public extension contract changes, update the relevant example and its
build coverage in CI.
