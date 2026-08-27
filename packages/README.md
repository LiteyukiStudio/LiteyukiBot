# Alpha15 Packages

The Alpha15 workspace publishes exactly four lockstep distributions, all at
`7.0.0a15`:

- `packages/kernel` publishes `liteyukibot-v7-kernel` and owns protocol-neutral
  JSON-safe events, actions, services, lifecycle, and status contracts.
- `packages/cordis` publishes `liteyukibot-v7-cordis` and owns trusted
  in-process scopes and deterministic ordered handlers.
- `packages/adapter-onebot` publishes `liteyukibot-v7-adapter-onebot` and
  owns the independently written OneBot v11 SnowLuma protocol client.
- The repository root publishes `liteyukibot-v7` and owns the CLI, config,
  application composition, and built-in features.

Every package has its own metadata, tests, license files, and README. Package
dependencies must use exact `7.0.0a15` pins for other workspace distributions.
The workspace does not publish the retired Broker, generic runtime, Satori,
NoneBot, WebUI, Agent, LYF, or native IPC packages.

Run focused checks from the repository root:

```bash
uv sync --locked --all-packages
uv run pytest packages/kernel/tests packages/cordis/tests packages/adapter-onebot/tests
uv build --all-packages --out-dir dist/workspace --clear
uv run python -m scripts.run_kernel_install
uv run python -m scripts.run_cordis_install
uv run python -m scripts.run_onebot_adapter_install
```

The canonical package inventory and release tags are defined in
`scripts/release_registry.py`.
