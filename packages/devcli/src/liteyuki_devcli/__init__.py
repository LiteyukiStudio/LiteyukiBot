"""Independent LiteyukiBot v7 developer CLI."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("liteyukibot-v7-devcli")
except PackageNotFoundError:
    __version__ = "7.0.0a8"

__all__ = ["__version__"]
