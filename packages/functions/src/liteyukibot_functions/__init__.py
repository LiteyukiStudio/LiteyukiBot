"""V6 Liteyuki resource-function execution for LiteyukiBot v7."""

from importlib.metadata import PackageNotFoundError, version

from .executor import (
    V6FunctionCapabilityError,
    V6FunctionExecutor,
    V6FunctionRuntimeError,
    V6FunctionSyntaxError,
)

try:
    __version__ = version("liteyukibot-v7-functions")
except PackageNotFoundError:
    __version__ = "0.1.0a3"

__all__ = [
    "V6FunctionCapabilityError",
    "V6FunctionExecutor",
    "V6FunctionRuntimeError",
    "V6FunctionSyntaxError",
    "__version__",
]
