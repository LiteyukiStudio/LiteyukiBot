# Examples

Examples are small installable packages that exercise public extension points.
They are not templates copied into production unchanged.

- `native-plugin/` demonstrates a native plugin entry point, EventBus cleanup,
  protocol-neutral replies, and the optional Native/Cordis runtime facade.
- `nonebot-plugin/` is the independently versioned reference artifact used by
  the managed NoneBot generation E2E.
- `broker-peer/` demonstrates a real B7 `BridgeClient` registration, event
  lease, experimental runtime API call, completion, and shutdown.

Keep examples minimal, dependency-bounded, and aligned with the public guides
in `docs/development/`. Build them from the repository root:

```bash
uv build --project examples/native-plugin --out-dir dist/examples
uv build --project examples/nonebot-plugin --out-dir dist/examples
uv build --project examples/broker-peer --out-dir dist/examples
```

When a public extension contract changes, update the relevant example and its
build coverage in CI.
