"""Framework exception hierarchy."""


class LiteyukiError(Exception):
    """Base class for framework errors."""


class ConfigurationError(LiteyukiError, ValueError):
    """Raised when configuration cannot be loaded or validated."""


class PluginError(LiteyukiError):
    """Raised when a plugin cannot be discovered or initialized."""


class ServiceError(LiteyukiError):
    """Raised when a service contract cannot be satisfied."""


class LegacyUnsupportedError(LiteyukiError):
    """Raised when a v6 plugin uses an API outside the compatibility contract."""
