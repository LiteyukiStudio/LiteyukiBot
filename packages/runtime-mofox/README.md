# LiteyukiBot Neo-MoFox Runtime

This AGPL-3.0-or-later package runs Neo-MoFox as an experimental limited
headless Broker bridge. It owns one explicitly configured isolated Neo-MoFox
workspace and does not load a Liteyuki platform adapter.

Neo-MoFox is not published on PyPI. PyPI distributions cannot declare a VCS
dependency, so install the pinned upstream runtime into the same environment
before this package:

```shell
uv add "neo-mofox @ git+https://github.com/MoFox-Studio/Neo-MoFox.git@e2ee2ff73b494428bbdfd983c7569c6f074a9c76"
uv add liteyukibot-v7-runtime-mofox
```

For a tool environment, install both requirements in one command:

```shell
uv tool install --with "neo-mofox @ git+https://github.com/MoFox-Studio/Neo-MoFox.git@e2ee2ff73b494428bbdfd983c7569c6f074a9c76" liteyukibot-v7-runtime-mofox
```

## Development

Keep Neo-MoFox APIs and workspace plugin loading inside this bridge process.
Liteyuki managed plugin projection, copying, and symlinking are not supported.
The fixed upstream requirement is an explicit verifier prerequisite, not
published wheel metadata. Run `uv run pytest packages/runtime-mofox/tests` and
`uv run python -m scripts.run_mofox_runtime_install` after changes.
