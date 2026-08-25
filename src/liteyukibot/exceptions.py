"""Composition-owned exceptions built on the kernel error contract."""

from liteyukibot_kernel.exceptions import LiteyukiError, ServiceError


class ConfigurationError(LiteyukiError, ValueError):
    """Raised when configuration cannot be loaded or validated."""


class PluginError(LiteyukiError):
    """Raised when a plugin cannot be discovered or initialized."""


class LegacyUnsupportedError(LiteyukiError):
    """Raised when a v6 plugin uses an API outside the compatibility contract."""


__all__ = [
    "ConfigurationError",
    "LegacyUnsupportedError",
    "LiteyukiError",
    "PluginError",
    "ServiceError",
]
