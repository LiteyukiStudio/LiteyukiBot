"""JSON-safe mutable value normalization shared by kernel integrations."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, cast

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


def json_mapping(value: Mapping[str, Any]) -> dict[str, JsonValue]:
    """Validate an arbitrary mapping as a mutable JSON object.

    Args:
        value: Value to validate and normalize.

    Returns:
        A JSON-safe object with string keys.
    """
    decoded = json_value(value)
    if not isinstance(decoded, dict):
        raise TypeError("expected a JSON object")
    return decoded


def json_value(value: Any) -> JsonValue:
    """Validate an arbitrary value as mutable JSON-safe data.

    Args:
        value: Value to validate and normalize.

    Returns:
        The normalized JSON-safe value.
    """
    encoded = json.dumps(
        _mutable_json(value),
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return cast(JsonValue, json.loads(encoded))


def _mutable_json(value: Any) -> Any:
    """Convert mappings and sequences into mutable JSON containers.

    Args:
        value: Value to normalize recursively.

    Returns:
        A value containing only mutable container representations.

    Notes:
        Scalar validation is delegated to the JSON encoder so unsupported
        values and non-finite floats fail consistently.
    """
    if isinstance(value, Mapping):
        return {str(key): _mutable_json(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_mutable_json(item) for item in value]
    return value


__all__ = ["JsonScalar", "JsonValue", "json_mapping", "json_value"]
