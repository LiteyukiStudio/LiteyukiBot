# Liteyuki Cordis Runtime

`liteyukibot-v7-runtime-cordis` is the optional first-party Cordis processor
runtime for LiteyukiBot v7. Cordis deliberately has a small, closed extension
surface: it owns an immutable built-in catcher manifest and produces bounded
`SendMessage` action plans from exact plain-text matches.

The manifest is compiled into Rust. Configuration selects built-in catcher IDs
and can override only a selected catcher's non-empty `match_text` and
`reply_text`; it cannot load manifests, third-party catchers, services, markets,
or live-reload code. Dependencies are validated and action planning is capped at
eight actions per delivery.

## Current boundary

This package-core slice exposes the manifest, configuration normalization, and
deterministic action planning through a narrow PyO3 JSON interface. The Rust
`liteyuki-cordis` binary implements `--version` and deliberately fails all
bootstrap attempts because the LYIP v2 child loop has not yet been implemented.
It does not claim to provide a ZMQ runtime transport.

The runtime discovery entry point resolves the installed Rust child binary from
the wheel distribution record; it never substitutes a Python host. Maturin's
normal PyO3 wheel mode does not automatically install a sibling Cargo binary,
so the transport/packaging follow-up must add the release-wheel binary artifact
before Cordis can be enabled. Until then discovery fails explicitly instead of
starting an incorrect process.

## Native JSON interface

```python
from liteyukibot_runtime_cordis import builtin_catchers_json, plan_actions_json

manifest = builtin_catchers_json()
plan = plan_actions_json(
    "kernel-event:delivery-1",
    "/cordis status",
    '{"enabled":["core.greeting", "core.help", "core.status"]}',
)
```

`plan` contains only JSON-safe values. Each action's correlation ID is a stable
SHA-256 derivation of its delivery ID and built-in catcher ID.
