"""Resolve the Rust Cordis child installed by the runtime wheel."""

from __future__ import annotations

from importlib import metadata
from pathlib import Path

_DISTRIBUTION = "liteyukibot-v7-runtime-cordis"
_BINARY_NAMES = frozenset({"liteyuki-cordis", "liteyuki-cordis.exe"})


def cordis_binary_command() -> tuple[str]:
    """Return the absolute command for the wheel-provided Rust child binary.

    The wheel record, rather than ``PATH`` or a shell lookup, is authoritative.
    This prevents a system executable with the same name from being supervised.
    """

    distribution = metadata.distribution(_DISTRIBUTION)
    files = distribution.files or ()
    candidates = [
        Path(distribution.locate_file(file))
        for file in files
        if file.name in _BINARY_NAMES and Path(distribution.locate_file(file)).is_file()
    ]
    if len(candidates) == 1:
        return (str(candidates[0]),)
    if not candidates:
        raise RuntimeError(
            "Cordis runtime wheel does not contain the liteyuki-cordis Rust child binary; "
            "install a release wheel built with the Cordis binary artifact"
        )
    raise RuntimeError("Cordis runtime wheel contains multiple liteyuki-cordis child binaries")


__all__ = ["cordis_binary_command"]
