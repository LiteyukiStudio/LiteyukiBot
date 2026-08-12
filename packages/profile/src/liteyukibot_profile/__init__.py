"""Persistent per-bot user profiles for LiteyukiBot v7."""

from importlib.metadata import PackageNotFoundError, version

from .plugin import create_plugin
from .service import PROFILE_SERVICE, ProfileService, ProfileSnapshot

try:
    __version__ = version("liteyukibot-v7-profile")
except PackageNotFoundError:
    __version__ = "0.1.0a2"

plugin = create_plugin(__version__)

__all__ = ["PROFILE_SERVICE", "ProfileService", "ProfileSnapshot", "__version__", "plugin"]
