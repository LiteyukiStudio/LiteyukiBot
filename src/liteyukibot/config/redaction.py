"""Secret-safe rendering helpers for configuration diagnostics."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_SENSITIVE_MARKERS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "credential",
)


def redact_config(value: Any) -> Any:
    """Copy JSON-compatible configuration while replacing sensitive values.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `Any` result produced by the operation.
    """

    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, child in value.items():
            rendered_key = str(key)
            result[rendered_key] = "<redacted>" if _is_sensitive(rendered_key) else redact_config(child)
        return result
    if isinstance(value, (tuple, list)):
        return [redact_config(item) for item in value]
    return value


def toml_compatible_config(value: Any) -> Any:
    """Drop optional null object fields before rendering TOML diagnostics.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `Any` result produced by the operation.
    """

    if isinstance(value, Mapping):
        return {
            str(key): toml_compatible_config(child)
            for key, child in value.items()
            if child is not None
        }
    if isinstance(value, (tuple, list)):
        if any(item is None for item in value):
            raise ValueError("TOML output cannot represent null array values")
        return [toml_compatible_config(item) for item in value]
    return value


def _is_sensitive(key: str) -> bool:
    """Implement the is sensitive operation for the component.

    Args:
        key: Stable FIFO ordering key for the queued work.

    Returns:
        Whether the requested condition is satisfied.

    Notes:
        Internal implementation detail for `_is_sensitive`. It delegates to `replace`, `lower`, `any`
        while keeping intermediate state local to the owning operation.
    """
    normalized = key.lower().replace("-", "_")
    return any(marker in normalized for marker in _SENSITIVE_MARKERS)


__all__ = ["redact_config", "toml_compatible_config"]
