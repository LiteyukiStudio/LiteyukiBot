"""Distribution wrapper for LiteyukiBot's local WebUI assets."""

from importlib.resources import files
from importlib.resources.abc import Traversable

__all__ = ["static_assets"]


def static_assets() -> Traversable:
    """Return the installed directory that will contain built WebUI assets."""
    return files("liteyukibot_webui").joinpath("static")

