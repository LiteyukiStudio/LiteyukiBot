from __future__ import annotations

import math
from pathlib import Path

import pytest

from liteyukibot.json_value import json_mapping, json_value


def test_json_value_normalizes_mutable_containers_and_object_keys() -> None:
    source = {1: ("value", {"nested": True})}

    normalized = json_mapping(source)  # type: ignore[arg-type]

    assert normalized == {"1": ["value", {"nested": True}]}
    assert isinstance(normalized["1"], list)


@pytest.mark.parametrize("value", [Path("not-json"), math.nan, math.inf])
def test_json_value_rejects_non_json_values(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        json_value(value)
