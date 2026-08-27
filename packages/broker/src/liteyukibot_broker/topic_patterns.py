"""Strict dot-segment topic patterns used by broker bridge manifests."""

from __future__ import annotations


def validate_topic_pattern(value: object, *, subject: str = "topic pattern") -> str:
    """Validate one literal-or-single-segment-wildcard topic pattern.

    Args:
        value: Value to validate, transform, or store.
        subject: The subject value used by the operation.

    Returns:
        The `str` result produced by the operation.
    """

    if not isinstance(value, str):
        raise TypeError(f"{subject} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{subject} must be non-empty and trimmed")
    if normalized != value:
        raise ValueError(f"{subject} must be non-empty and trimmed")
    segments = normalized.split(".")
    if any(not segment for segment in segments):
        raise ValueError(f"{subject} must use non-empty dot-separated segments")
    if any("*" in segment and segment != "*" for segment in segments):
        raise ValueError(f"{subject} may use only a complete '*' segment")
    return normalized


def topic_pattern_matches(pattern: str, topic: str) -> bool:
    """Return whether a pattern matches a topic without regex semantics.

    Args:
        pattern: The pattern value used by the operation.
        topic: The topic value used by the operation.

    Returns:
        Whether the requested condition is satisfied.
    """

    pattern_segments = validate_topic_pattern(pattern).split(".")
    topic_segments = validate_topic_pattern(topic, subject="topic").split(".")
    return len(pattern_segments) == len(topic_segments) and all(
        expected == "*" or expected == actual
        for expected, actual in zip(pattern_segments, topic_segments, strict=True)
    )


__all__ = ["topic_pattern_matches", "validate_topic_pattern"]
