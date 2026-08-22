from typing import NoReturn

from liteyuki._unsupported import unsupported


def __getattr__(name: str) -> NoReturn:
    """Implement the getattr operation for the component.

    Args:
        name: Stable name used to identify the value.

    Returns:
        The `NoReturn` result produced by the operation.
    """
    unsupported(__name__, name)
