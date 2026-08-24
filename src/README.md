# Kernel Source

`src/liteyukibot/` is the v7 kernel distribution. It owns portable models,
configuration, logging integration, native-plugin lifecycle, event/action
routing, Broker integration, and the command-line interface.

Keep framework SDK imports and adapter objects out of this tree. Add a bridge
or platform integration under `packages/` and exchange only public contracts
across the Broker boundary.

## Layout

- `app.py`, `events/`, `plugins.py`, `services.py`, and `tasks.py` implement
  kernel lifecycle and plugin/event contracts.
- `config/` owns settings, workspace initialization, inspection, and the secret
  vault.
- `broker/` owns the authenticated cross-process peer contract.
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
