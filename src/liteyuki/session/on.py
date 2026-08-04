from typing import NoReturn

from liteyuki._unsupported import unsupported


def __getattr__(name: str) -> NoReturn:
    unsupported(__name__, name)
