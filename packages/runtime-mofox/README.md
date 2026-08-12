# LiteyukiBot Neo-MoFox Runtime

This AGPL-3.0-or-later package runs Neo-MoFox as an agent-only headless
runtime. It owns a Neo-MoFox workspace below its assigned runtime state
directory and does not load a Liteyuki platform adapter.

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
