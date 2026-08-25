"""Independent LiteyukiBot v7 developer CLI."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("liteyukibot-v7-devcli")
except PackageNotFoundError:
    __version__ = "0+unknown"

__all__ = ["__version__"]
