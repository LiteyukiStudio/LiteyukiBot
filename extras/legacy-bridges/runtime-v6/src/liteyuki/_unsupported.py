"""Explicit failures for v6 APIs outside the hosted compatibility contract."""

from __future__ import annotations

from typing import NoReturn

from liteyukibot.exceptions import LegacyUnsupportedError


def unsupported(module: str, api: str | None = None) -> NoReturn:
    """Implement the unsupported operation for the component.

    Args:
        module: The module value used by the operation.
        api: The api value used by the operation.

    Returns:
        The `NoReturn` result produced by the operation.
    """
    if api is not None and api.startswith("__"):
        raise AttributeError(api)
    target = f"{module}.{api}" if api else module
    raise LegacyUnsupportedError(
        f"LiteyukiBot v6 API {target} is unsupported in the v7 compatibility runtime; "
        "use the protocol-neutral event/action APIs"
    )
