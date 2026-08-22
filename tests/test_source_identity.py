from __future__ import annotations

import pytest

from liteyukibot.events import canonical_source_event_id


def test_canonical_source_event_id_encodes_each_identity_part() -> None:
    assert canonical_source_event_id("bridge:prod", "onebot/42", "message:7") == (
        "v1:bridge%3Aprod:onebot%2F42:message%3A7"
    )


def test_canonical_source_event_id_is_deterministic_and_tuple_scoped() -> None:
    source = canonical_source_event_id("bridge", "adapter:bot", "event")

    assert source == canonical_source_event_id("bridge", "adapter:bot", "event")
    assert len(
        {
            source,
            canonical_source_event_id("other-bridge", "adapter:bot", "event"),
            canonical_source_event_id("bridge", "other:bot", "event"),
            canonical_source_event_id("bridge", "adapter:bot", "other-event"),
        }
    ) == 4


@pytest.mark.parametrize("parts", [("", "adapter", "event"), ("bridge", " ", "event"), ("bridge", "adapter", "")])
def test_canonical_source_event_id_rejects_blank_parts(parts: tuple[str, str, str]) -> None:
    with pytest.raises(ValueError, match="non-empty trimmed"):
        canonical_source_event_id(*parts)


def test_canonical_source_event_id_rejects_untrimmed_parts() -> None:
    with pytest.raises(ValueError, match="non-empty trimmed"):
        canonical_source_event_id("bridge ", "adapter", "event")
