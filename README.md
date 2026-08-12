# LiteyukiBot v7

LiteyukiBot v7 is a protocol-neutral chatbot kernel for CPython 3.14. Native
plugins run in the core process; separately distributed framework hosts and
LiteyukiBot v6 plugins run in supervised child runtimes.

The `v7` branch is a clean rewrite. The `main` branch remains the maintenance
line for v6 and is not merged wholesale into v7.

The current pre-release is `liteyukibot-v7==7.0.0a13`. Kernel stabilization,
the first bounded compatibility phase, and the first-party plugin foundation
are complete. Runtime protocol v4 remains an alpha contract and may change
under ADR 0011 before the first stable release.

## Current Foundation

- immutable TOML/JSON configuration with ordered includes, environment
  overrides, and CLI overrides;
- Yukilog 1.x facade backed by Loguru, including structured child logs;
- native plugin entry points, async lifecycle hooks, private storage, managed
  tasks, and versioned services;
- bounded protocol-neutral event/action dispatch with per-conversation order;
- authenticated framed JSON IPC and supervised subprocess runtimes;
- runtime-host discovery plus a deliberately bounded v6 compatibility shim;
- local authenticated CLI control and an optional loopback-only HTTP status API.
- layered resource packs for language catalogs, functions, and future static
  assets, with workspace packs overriding built-in and enabled-plugin content;
- read-only kernel status plus separately distributable capability, command,
  resource-management, profile, help, and protected-status plugins.

## Requirements

- CPython 3.14+
- [uv](https://docs.astral.sh/uv/)
- network access for uv to resolve PyPI dependencies

Yukilog 1.x is installed from PyPI; no sibling checkout is required.
The v7 kernel distribution on PyPI is named `liteyukibot-v7` and provides the
`liteyukibot` namespace. The separately installed v6 runtime provides the
`liteyuki` compatibility namespace.

## Tool Installation

Install the v7 CLI into uv's isolated tool environment:

```bash
uv tool install --python 3.14 liteyukibot-v7
liteyuki init
liteyuki run
```

The commands operate on the current directory by default. Use
`liteyuki --workspace PATH ...` to select another project. `liteyukibot` and
`ly` are equivalent executable aliases. Upgrade only the v7 tool with:

```bash
uv tool upgrade --python 3.14 liteyukibot-v7
```

This does not replace a separately installed v6 `liteyukibot` distribution.

```bash
uv sync --locked
uv run liteyuki check
uv run liteyuki run
```

Optional kernel integrations are installed explicitly:

```bash
uv sync --extra yaml
uv sync --extra http
```

Framework hosts are independent packages. Install NoneBot2 with an adapter:

```bash
uv add "liteyukibot-v7-runtime-nonebot[onebot]"
# or: uv add "liteyukibot-v7-runtime-nonebot[satori]"
```

Install the Python platform-adapter host independently. It contains no platform
SDK; protocol and platform adapters are separately published packages:

```bash
uv add liteyukibot-v7-runtime-adapter
uv add liteyukibot-v7-adapter-onebot
```

Install bounded v6 compatibility when legacy plugins are required:

```bash
uv add "liteyukibot-v7-runtime-v6"
```

Install the v6 resource-function executor only when workspace resource packs
contain `.lyf`, `.lyfunction`, or `.mcfunction` files:

```bash
uv add "liteyukibot-v7-functions"
```

It preserves the v6 function language but does not grant resource files shell
or adapter API access by itself; callers must explicitly provide those
capabilities.

Install the Essentials command layer with:

```bash
uv add "liteyukibot-v7-essentials==0.2.0a3"
```

This resolves `liteyukibot-v7-commands` and
`liteyukibot-v7-permissions`; enable all three plugin IDs in configuration.

The optional profile layer adds persistent per-bot user nickname and language
preferences. Install `liteyukibot-v7-profile` to resolve resources, then enable
`liteyukibot.resources` and `liteyukibot.profile` before Essentials. Profile is
a business plugin: its SQLite database is private to the plugin, and resources
only supplies the declaration, command, and authorization boundary.

Create a project-local configuration with `uv run liteyuki init`; use
`liteyuki.example.toml` as a configuration reference. CLI overrides must precede
the subcommand, for example:

```bash
uv run liteyuki --config local.toml --set logging.level=DEBUG check
```

Initialization, encrypted runtime secrets, upgrade recovery, and configuration
provenance are documented in [docs/configuration.md](docs/configuration.md).
`liteyuki init` opens a full-screen setup wizard; use `--non-interactive` for
automation and `--locale auto|zh-CN|en-US` to control its language.

## Docker

The v7 image can be built locally with the optional YAML, HTTP, NoneBot,
OneBot, Satori, and v6 compatibility runtime packages. It runs as a non-root user. GHCR
publication is currently paused; the Docker workflow validates builds without
pushing.

```bash
docker build -t liteyukibot:v7-local .
docker run --rm liteyukibot:v7-local version
```

When `/app/liteyuki.toml` is absent, the container creates the versioned default
template once. Mount a configuration at that path to control a deployment, and
persist `/app/data`, `/app/cache`, and `/app/plugins`.

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
uv run python -m scripts.run_developer_kit_install
uv run python -m scripts.run_permissions_install
uv run python -m scripts.run_commands_install
uv run python -m scripts.run_resources_install
uv run python -m scripts.run_functions_install
uv run python -m scripts.run_profile_install
uv run python -m scripts.run_essentials_install
uv run python -m scripts.run_nonebot_runtime_install
uv run python -m scripts.run_adapter_runtime_install
```

The architecture overview is documented in `docs/architecture/v7.md`; accepted
architecture contracts are indexed in `docs/adr/README.md`; the v6 compatibility
boundary is documented in `docs/migration-v6.md`.

Release maintainers should follow `docs/development/releasing.md`.

Plugin and runtime authors should start with the installable examples and their
focused guides:

- `examples/native-plugin` and `docs/development/native-plugins.md`;
- `examples/custom-runtime` and `docs/development/custom-runtimes.md`.
