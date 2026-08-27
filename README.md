<div align="center">

[![][banner]][liteyuki-link]
<h2><a href="https://bot.liteyuki.org"><span style="color: #a2d8f4">LiteyukiBot</span> <span style="color: #d0e9ff">v7</span></a></h2>
<h4><span style="color: #a2d8f4">Liteyuki-first Python chatbot application</span></h4>

[![][Liteyuki7]][liteyuki-link]
[![][Python3.14]][python-link]
[![][Usage]][usage-link]
[![][Repo]][repo-link]
[![][Github]][github-link]

</div>

## About

LiteyukiBot v7 is a CPython 3.14 application built around a small,
protocol-neutral kernel. The root distribution owns configuration, the CLI,
application composition, native lifecycle, logging, and the built-in Cordis
features. The Alpha15 source identity is `7.0.0a15`; it is a signed GitHub
release bundle and is not a PyPI release.

Alpha15 intentionally ships four lockstep distributions:

| Distribution | Responsibility |
| --- | --- |
| `liteyukibot-v7` | Branded CLI and application composition. |
| `liteyukibot-v7-kernel` | JSON-safe events, actions, services, lifecycle, and status contracts. |
| `liteyukibot-v7-cordis` | Trusted in-process Cordis scopes and ordered event handlers. |
| `liteyukibot-v7-adapter-onebot` | OneBot v11 SnowLuma WebSocket client and kernel event/action conversion. |

Permissions, commands, resources, profile, and essentials are built-in root
features. Satori, NoneBot, the generic runtime bridge, standalone Broker,
WebUI, Agent, LYF, and native IPC packages are not Alpha15 distributions.
Historical bridge snapshots remain under `extras/legacy-bridges` only.

## Install And Run

Requirements: CPython 3.14 or later and [uv][uv-link].

```bash
uv tool install --python 3.14 liteyukibot-v7
mkdir my-bot
liteyuki --workspace my-bot init
liteyuki --workspace my-bot check
liteyuki --workspace my-bot run
```

For a checkout:

```bash
uv sync --locked --all-packages
uv run liteyuki check
uv run liteyuki run
```

The generated `liteyuki.toml` is configuration schema 7. Built-in features
are enabled by the application; configure their sections directly. OneBot is
enabled by adding accounts under `[onebot.v11.accounts]`. See
[configuration operations](docs/configuration.md).

## OneBot And SnowLuma

The OneBot package is an independently written protocol client. It does not
bundle SnowLuma source, native addons, or assets. SnowLuma is an external
project; LiteyukiBot is not affiliated with or endorsed by it. Operators are
responsible for the external service's terms, privacy requirements, and
platform risks. See the [adapter README](packages/adapter-onebot/README.md)
and the [SnowLuma project](https://github.com/SnowLuma/SnowLuma).

## Documentation

- [Configuration schema 7](docs/configuration.md)
- [v7 architecture](docs/architecture/v7.md)
- [Release procedure](docs/development/releasing.md)
- [Cordis plugin contract](docs/architecture/cordis-plugin-v1.md)
- [Contributor guide](CONTRIBUTING.md)

Report reproducible defects with installed versions, operating system, Python
version, and the smallest reproducer. Do not include credentials or message
payloads in public reports.

[Liteyuki7]: https://img.shields.io/badge/LiteyukiBot-7.0.0a15-blue?style=for-the-badge
[Python3.14]: https://img.shields.io/badge/Python-3.14+-blue?style=for-the-badge
[Usage]: https://img.shields.io/badge/Usage-CLI-blue?style=for-the-badge
[Repo]: https://img.shields.io/badge/Distribution-GitHub%20Release-blue?style=for-the-badge
[Github]: https://img.shields.io/badge/GitHub-Repository-blue?style=for-the-badge
[banner]: https://socialify.git.ci/LiteyukiStudio/LiteyukiBot/image?description=1&font=Source+Code+Pro&forks=1&issues=1&name=1&owner=1&pattern=Floating+Cogs&pulls=1&stargazers=1&theme=Auto

[python-link]: https://www.python.org/
[uv-link]: https://docs.astral.sh/uv/
[usage-link]: docs/configuration.md
[liteyuki-link]: https://github.com/LiteyukiStudio/LiteyukiBot
[repo-link]: https://github.com/LiteyukiStudio/LiteyukiBot/releases
[github-link]: https://github.com/LiteyukiStudio/LiteyukiBot
