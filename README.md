# LiteyukiBot v7

LiteyukiBot v7 is a protocol-neutral chatbot kernel for CPython 3.14. Native
plugins run in the core process; NoneBot2 and LiteyukiBot v6 plugins run in
supervised child runtimes.

The `v7` branch is a clean rewrite. The `main` branch remains the maintenance
line for v6 and is not merged wholesale into v7.

The current pre-release is `liteyukibot-v7==7.0.0a3`. Kernel stabilization,
the first bounded compatibility phase, and the first-party plugin foundation
are complete. Runtime protocol v3 remains an alpha contract and may change
under ADR 0011 before the first stable release.

## Current Foundation

- immutable TOML/JSON configuration with ordered includes, environment
  overrides, and CLI overrides;
- Yukilog 1.x facade backed by Loguru, including structured child logs;
- native plugin entry points, async lifecycle hooks, private storage, managed
  tasks, and versioned services;
- bounded protocol-neutral event/action dispatch with per-conversation order;
- authenticated framed JSON IPC and supervised subprocess runtimes;
- NoneBot2 plugin hosting and a deliberately bounded v6 compatibility shim;
- local authenticated CLI control and an optional loopback-only HTTP status API.
- read-only kernel status plus separately distributable capability, command,
  help, and protected-status plugins.

## Requirements

- CPython 3.14+
- [uv](https://docs.astral.sh/uv/)
- network access for uv to resolve PyPI dependencies

Yukilog 1.x is installed from PyPI; no sibling checkout is required.
The v7 distribution on PyPI is named `liteyukibot-v7`; Python imports remain
`liteyukibot` and `liteyuki` for the native and v6 compatibility namespaces.

```bash
uv sync --locked
uv run liteyuki check
uv run liteyuki run
```

Optional integrations are installed explicitly:

```bash
uv sync --extra yaml
uv sync --extra http
uv sync --extra nonebot --extra onebot
uv sync --extra nonebot --extra satori
```

Install the complete first-party plugin chain with:

```bash
uv add "liteyukibot-v7-essentials==0.1.0a1"
```

This resolves `liteyukibot-v7-commands` and
`liteyukibot-v7-permissions`; enable all three plugin IDs in configuration.

Use `liteyuki.example.toml` as a configuration reference. CLI overrides must
precede the subcommand, for example:

```bash
uv run liteyuki --config local.toml --set logging.level=DEBUG check
```

## Docker

The v7 image can be built locally with the optional YAML, HTTP, NoneBot2,
OneBot, and Satori integrations. It runs as a non-root user. GHCR publication
is currently paused; the Docker workflow validates builds without pushing.

```bash
docker build -t liteyukibot:v7-local .
docker run --rm liteyukibot:v7-local version
```

Mount a `liteyuki.toml` at `/app/liteyuki.toml` and persistent volumes at
`/app/data`, `/app/cache`, and `/app/plugins` for a configured deployment.

## Development

```bash
uv sync --locked --all-packages
uv run ruff check src tests scripts examples packages
uv run mypy
uv run pytest
uv build
uv build --all-packages --out-dir dist/workspace --clear
uv build --project examples/native-plugin --out-dir dist/examples
uv build --project examples/custom-runtime --out-dir dist/examples
uv run python scripts/run_developer_kit_install.py
uv run python scripts/run_permissions_install.py
uv run python scripts/run_commands_install.py
uv run python scripts/run_essentials_install.py
```

The architecture overview is documented in `docs/architecture/v7.md`; accepted
architecture contracts are indexed in `docs/adr/README.md`; the v6 compatibility
boundary is documented in `docs/migration-v6.md`.

Release maintainers should follow `docs/development/releasing.md`.

Plugin and runtime authors should start with the installable examples and their
focused guides:

- `examples/native-plugin` and `docs/development/native-plugins.md`;
- `examples/custom-runtime` and `docs/development/custom-runtimes.md`.
