"""Exceptions owned by the protocol-neutral kernel contract."""


class LiteyukiError(Exception):
    """Base class for LiteyukiBot errors."""


class ServiceError(LiteyukiError):
    """Raised when a service contract cannot be satisfied."""


__all__ = ["LiteyukiError", "ServiceError"]
