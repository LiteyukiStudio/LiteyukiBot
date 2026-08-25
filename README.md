<div align="center">

[![][banner]][liteyuki-link]
<h2><a href="https://bot.liteyuki.org"><span style="color: #a2d8f4">LiteyukiBot</span> <span style="color: #d0e9ff">v7</span></a></h2>
<h4><span style="color: #a2d8f4">Protocol-neutral, multi-runtime chatbot kernel</span></h4>

[![][Liteyuki7]][liteyuki-link]
[![][Python3.14]][python-link]
[![][Usage]][usage-link]
[![][Repo]][repo-link]
[![][Github]][github-link]

</div>

## About

LiteyukiBot v7 is a CPython 3.14 chatbot kernel. It owns configuration,
native-plugin lifecycle, routing, permissions, logging, and broker-peer IPC.
Framework integrations run as separately installed B7 broker bridges and
exchange frozen protocol-neutral models with the kernel rather than SDK
objects. Retired AstrBot, Neo-MoFox, and v6 compatibility experiments are kept
only as source snapshots under `extras/legacy-bridges`; they are not workspace,
release, CI, or support targets.

The default branch is the maintained LiteyukiBot v7 line. The prior v6 line is
preserved on the `v6` branch. The current source pre-release is the `7.0.0a14`
Alpha lockstep baseline; it is not yet a PyPI release. Alpha14 is the ownership,
release-graph, and architecture-subtraction stage defined by the
[authoritative Alpha14 route](docs/roadmap/v7-alpha-14-baseline.md). Beta
requires both a 14-day public-contract freeze and a reviewed 72-hour reference
deployment soak.

## Features

- interactive or non-interactive project initialization through `liteyuki`;
- immutable TOML/JSON configuration with includes, environment variables, CLI
  overrides, provenance inspection, encrypted runtime secrets, and recovery
  material for configuration upgrades;
- native plugins with explicit entry points, lifecycle hooks, services,
  managed tasks, private storage, resource packs, and localized text;
- authenticated B7 broker-peer IPC, per-conversation event ordering, bounded
  concurrency, lease-bound deliveries, and routed protocol-neutral actions;
- retained and verifiable runtime plugin generations with source indexes,
  rollback, disable/enable, and garbage collection commands;
- first-party command, permission, resource, profile, essential-command, and
  agent packages;
- separately packaged NoneBot2 and protocol-adapter bridges, including native
  OneBot v11 support.

## Install And Run

Requirements:

- CPython 3.14 or later;
- [uv][uv-link].

Install the command-line tool and create a workspace:

```bash
uv tool install --python 3.14 liteyukibot-v7
mkdir my-bot
liteyuki --workspace my-bot init
liteyuki --workspace my-bot check
liteyuki --workspace my-bot run
```

`liteyukibot`, `liteyuki`, and `ly` are equivalent command names. Use
`init --non-interactive --locale en-US` for automation. The generated
`liteyuki.toml` is the workspace configuration; see
[configuration operations](docs/configuration.md) for secrets, profiles,
configuration precedence, and recovery procedures.

To work from a checkout instead of a tool installation:

```bash
uv sync --locked --all-packages
uv run liteyuki init
uv run liteyuki check
uv run liteyuki run
```

## Packages

The kernel package is `liteyukibot-v7`. Optional features are separate PyPI
packages and must be installed into the same environment before they are
enabled in `liteyuki.toml`.

| Package | Current responsibility |
| --- | --- |
| `liteyukibot-v7-permissions` | Exact-principal capability policy service. |
| `liteyukibot-v7-commands` | Protocol-neutral command router and schemas. |
| `liteyukibot-v7-resources` | Declarative resource and authorization boundary. |
| `liteyukibot-v7-profile` | Persistent per-bot nickname and language profiles. |
| `liteyukibot-v7-essentials` | Help and protected status commands. |
| `liteyukibot-v7-functions` | v6 `.lyf`, `.lyfunction`, and `.mcfunction` executor. |
| `liteyukibot-v7-runtime-nonebot` | B7 NoneBot2 broker bridge. |
| `liteyukibot-v7-runtime-nonebot-api` | NoneBot-independent typed Runtime API v1.2 facade. |
| `liteyukibot-v7-runtime-adapter` | Python platform-adapter broker bridge. |
| `liteyukibot-v7-adapter-onebot` | Native OneBot v11 HTTP Post and HTTP API adapter. |
| `liteyukibot-v7-agent-resolver` | Declarative agent module and tool resolver. |
| `liteyukibot-v7-agent` | OpenAI-compatible native agent runtime. |

Read the package README in [`packages/`](packages/README.md) before enabling a
package. The kernel does not install framework integrations implicitly.

## Docker

Build the current image locally:

```bash
docker build -t liteyukibot:v7-local .
docker run --rm liteyukibot:v7-local version
```

The image runs as a non-root user. Mount `/app/data`, `/app/cache`, and
`/app/plugins` for persistent state, then provide `/app/liteyuki.toml` for a
configured deployment.

## Services And Support

Current installation, configuration, compatibility, and release boundaries are
documented in this repository. Report reproducible defects or documentation
errors through the [GitHub repository][github-link], including the installed
package versions, operating system, Python version, and the minimal command or
configuration that reproduces the result. Do not include vault passwords,
tokens, or message payloads in public reports.

## Documentation

- [Configuration operations](docs/configuration.md)
- [v7 architecture](docs/architecture/v7.md)
- [Alpha14 route](docs/roadmap/v7-alpha-14-baseline.md)
- [Historical Beta1 contract](docs/archive/2026-08-17/beta1-contract.md)
- [Native plugin development](docs/development/native-plugins.md)
- [Broker peer development](docs/development/broker-peers.md)
- [Runtime API and provider conformance](docs/development/runtime-api-conformance.md)
- [Contributor guide](CONTRIBUTING.md)
- [Release procedure](docs/development/releasing.md)

## References

- [NoneBot](https://nonebot.dev/) informs the separately packaged NoneBot
  runtime boundary.

## Other

This repository is a uv workspace containing the kernel, first-party packages,
examples, tests, developer tools, documentation, and release workflows.
Directory-level development guidance is provided by each directory's README.

[Liteyuki7]: https://img.shields.io/badge/LiteyukiBot-7.0.0a14-blue?style=for-the-badge
[Python3.14]: https://img.shields.io/badge/Python-3.14+-blue?style=for-the-badge
[Usage]: https://img.shields.io/badge/Usage-CLI-blue?style=for-the-badge
[Repo]: https://img.shields.io/badge/Distribution-PyPI-blue?style=for-the-badge
[Github]: https://img.shields.io/badge/GitHub-Repository-blue?style=for-the-badge
[banner]: https://socialify.git.ci/LiteyukiStudio/LiteyukiBot/image?description=1&font=Source+Code+Pro&forks=1&issues=1&name=1&owner=1&pattern=Floating+Cogs&pulls=1&stargazers=1&theme=Auto

[python-link]: https://www.python.org/
[uv-link]: https://docs.astral.sh/uv/
[usage-link]: docs/configuration.md
[liteyuki-link]: https://github.com/LiteyukiStudio/LiteyukiBot
[repo-link]: https://pypi.org/project/liteyukibot-v7/
[github-link]: https://github.com/LiteyukiStudio/LiteyukiBot
