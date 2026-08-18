"""Minimal, JSON-safe authorization inputs shared by extension hosts."""

from __future__ import annotations

from dataclasses import dataclass


def _required(value: str, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"authorization {field} must be a non-empty trimmed string")
    return value


@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    """The only event-derived data allowed at a v2 authorization boundary."""

    event_id: str
    runtime_id: str
    bot_id: str
    actor_id: str | None = None

    def __post_init__(self) -> None:
        for field in ("event_id", "runtime_id", "bot_id"):
            object.__setattr__(self, field, _required(getattr(self, field), field))
        if self.actor_id is not None:
            object.__setattr__(self, "actor_id", _required(self.actor_id, "actor_id"))


__all__ = ["AuthorizationContext"]
