"""Distribution-backed version information."""

from importlib.metadata import PackageNotFoundError, version

DISTRIBUTION_NAME = "liteyukibot-v7-broker"

try:
    __version__ = version(DISTRIBUTION_NAME)
except PackageNotFoundError:
    __version__ = "0+unknown"
