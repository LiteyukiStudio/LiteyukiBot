from __future__ import annotations

from urllib.parse import quote


def canonical_source_event_id(bridge_id: str, provider_scope: str, upstream_id: str) -> str:
    """Build a collision-safe source event ID from one provider identity tuple."""

    parts = (bridge_id, provider_scope, upstream_id)
    if any(not isinstance(part, str) or not part.strip() or part != part.strip() for part in parts):
        raise ValueError("source event identity parts must be non-empty trimmed strings")
    return "v1:" + ":".join(quote(part, safe="") for part in parts)


__all__ = ["canonical_source_event_id"]
