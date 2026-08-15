"""Optional shared-memory primitives for the Liteyuki IPC native backend."""

from importlib import import_module

LYIP_NATIVE_ABI = 1

try:
    _native = import_module(f"{__name__}._native")
except ImportError:
    native_available = False
else:
    native_abi = getattr(_native, "lyip_native_abi", None)
    shared_memory_probe = getattr(_native, "shared_memory_available", None)
    native_available = (
        callable(native_abi)
        and native_abi() == LYIP_NATIVE_ABI
        and callable(shared_memory_probe)
        and shared_memory_probe()
    )
    if native_available:
        SharedSpscRing = _native.SharedSpscRing

__all__ = ["LYIP_NATIVE_ABI", "SharedSpscRing", "native_available"]
