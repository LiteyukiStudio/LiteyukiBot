"""Read and write JSON-safe configuration documents in supported formats."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

from tomli_w import dumps as dump_toml


def read_document(path: Path) -> dict[str, Any]:
    """Read one object-valued JSON, YAML, or TOML document.

    Args:
        path: Input accepted by this callable.

    Returns:
        Result produced by this callable.
    """
    raw = path.read_bytes()
    if path.suffix.lower() == ".json":
        value = json.loads(raw.decode("utf-8-sig"))
    elif path.suffix.lower() == ".toml":
        value = tomllib.loads(raw.decode("utf-8"))
    elif path.suffix.lower() in {".yaml", ".yml"}:
        import yaml

        value = yaml.safe_load(raw.decode("utf-8-sig"))
    else:
        raise ValueError(f"unsupported configuration format: {path.suffix}")
    if not isinstance(value, dict):
        raise ValueError("configuration document root must be an object")
    return value


def write_document(path: Path, value: dict[str, Any]) -> None:
    """Atomically write one JSON-safe object-valued document.

    Args:
        path: Input accepted by this callable.
        value: Input accepted by this callable.

    Returns:
        Result produced by this callable.
    """
    if path.suffix.lower() == ".json":
        content = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    elif path.suffix.lower() == ".toml":
        content = dump_toml(value)
    elif path.suffix.lower() in {".yaml", ".yml"}:
        import yaml

        content = yaml.safe_dump(value, allow_unicode=True, sort_keys=True)
    else:
        raise ValueError(f"unsupported configuration format: {path.suffix}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
