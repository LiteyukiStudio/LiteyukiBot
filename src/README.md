# Root Composition Source

`src/liteyukibot/` is the branded `liteyukibot-v7` CLI and composition
distribution. It owns application configuration, native-plugin lifecycle,
Broker and daemon integration, and the command-line interface. The independent
contract nucleus lives in `packages/kernel` and is published as
`liteyukibot-v7-kernel` from the `liteyukibot_kernel` namespace.

Keep framework SDK imports and adapter objects out of this tree. Add a bridge
or platform integration under `packages/` and exchange only public contracts
across the Broker boundary.

## Layout

- `app.py` and `plugins.py` currently implement root composition and native
  plugin lifecycle.
- `events/`, `services.py`, `tasks.py`, and the other contract modules are
  compatibility re-exports of `liteyukibot_kernel`.
- `config/` owns settings, workspace initialization, inspection, and the secret
  vault.
- `packages/broker/` owns the authenticated cross-process peer contract;
  root `broker/` only composes it with AppSettings, Vault, EventBus, and CLI
  lifecycle concerns.
- `runtime_api.py` owns the capability-routed provider facade used by plugins.
- `cli.py` owns the `liteyuki`, `liteyukibot`, and `ly` commands.
- `builtin_resources/` contains kernel-owned resource-pack assets.

Use the root quality commands after modifying this directory:

```bash
uv run ruff check src tests
uv run mypy
uv run pytest tests
```

Public contract changes require focused tests and the matching document under
`docs/specs/`, `docs/architecture/`, or `docs/configuration.md`.
