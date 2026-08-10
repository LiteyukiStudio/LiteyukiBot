# LiteyukiBot Neo-MoFox Runtime

This AGPL-3.0-or-later package runs Neo-MoFox as an agent-only headless
runtime. It owns a Neo-MoFox workspace below its assigned runtime state
directory and does not load a Liteyuki platform adapter.

Neo-MoFox is not published on PyPI, so install the pinned upstream runtime
before this package:

```shell
pip install "neo-mofox @ git+https://github.com/MoFox-Studio/Neo-MoFox.git@e2ee2ff73b494428bbdfd983c7569c6f074a9c76"
pip install liteyukibot-v7-runtime-mofox
```
