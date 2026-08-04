# LiteyukiBot v7

LiteyukiBot v7 is a protocol-neutral chatbot kernel for CPython 3.14. Native
plugins run in the core process; NoneBot2 and LiteyukiBot v6 plugins run in
supervised child runtimes.

The `v7` branch is a clean rewrite. The `main` branch remains the maintenance
line for v6 and is not merged wholesale into v7.

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

## Requirements

- CPython 3.14+
- [uv](https://docs.astral.sh/uv/)
- network access for uv to resolve PyPI dependencies

Yukilog 1.x is installed from PyPI; no sibling checkout is required.

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
```

Use `liteyuki.example.toml` as a configuration reference. CLI overrides must
precede the subcommand, for example:

```bash
uv run liteyuki --config local.toml --set logging.level=DEBUG check
```

## Development

```bash
uv run ruff check src tests scripts
uv run mypy
uv run pytest
uv build
```

The architecture contract is documented in `docs/architecture/v7.md`; the v6
compatibility boundary is documented in `docs/migration-v6.md`.
