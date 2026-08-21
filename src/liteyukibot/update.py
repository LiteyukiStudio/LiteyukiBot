"""Durable state machine primitives for whole-instance updates."""

from __future__ import annotations

import json
import os
import secrets
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import cast


class UpdateError(RuntimeError):
    """Raised when an update journal cannot advance safely."""


class UpdatePhase(StrEnum):
    VERIFIED = "verified"
    STAGED = "staged"
    ADMISSION_FROZEN = "admission_frozen"
    DRAINED = "drained"
    KERNEL_FROZEN = "kernel_frozen"
    STOPPED = "stopped"
    PROFILE_SWITCHED = "profile_switched"
    STARTING = "starting"
    HEALTHY = "healthy"
    COMMITTED = "committed"
    ABORTED = "aborted"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    RECOVERED = "recovered"


_ORDER: tuple[UpdatePhase, ...] = (
    UpdatePhase.VERIFIED,
    UpdatePhase.STAGED,
    UpdatePhase.ADMISSION_FROZEN,
    UpdatePhase.DRAINED,
    UpdatePhase.KERNEL_FROZEN,
    UpdatePhase.STOPPED,
    UpdatePhase.PROFILE_SWITCHED,
    UpdatePhase.STARTING,
    UpdatePhase.HEALTHY,
    UpdatePhase.COMMITTED,
)
_TERMINAL = frozenset({UpdatePhase.COMMITTED, UpdatePhase.ABORTED, UpdatePhase.ROLLED_BACK, UpdatePhase.RECOVERED})


class UpdateJournal:
    """Atomic JSON journal whose non-terminal state is recoverable after restart."""

    schema_version = 1

    def __init__(self, path: Path, *, instance: str) -> None:
        self.path = path
        self.instance = instance

    def load(self) -> dict[str, object] | None:
        if not self.path.exists():
            return None
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise UpdateError(f"cannot read update journal {self.path}") from error
        if not isinstance(value, dict) or value.get("schema_version") != self.schema_version:
            raise UpdateError("update journal schema is unsupported")
        phase = value.get("phase")
        if not isinstance(phase, str) or phase not in {item.value for item in UpdatePhase}:
            raise UpdateError("update journal phase is invalid")
        return value

    def begin(self, *, candidate_profile: str, previous_profile: str | None) -> str:
        current = self.load()
        if current is not None and not self.is_terminal(current):
            raise UpdateError("an instance update is already in progress")
        operation_id = secrets.token_urlsafe(18)
        self._write(
            {
                "schema_version": self.schema_version,
                "instance": self.instance,
                "operation_id": operation_id,
                "candidate_profile": candidate_profile,
                "previous_profile": previous_profile,
                "phase": UpdatePhase.VERIFIED.value,
                "history": [self._history_item(UpdatePhase.VERIFIED)],
                "error": None,
                "updated_at": self._now(),
            }
        )
        return operation_id

    def transition(
        self,
        phase: UpdatePhase,
        *,
        error: str | None = None,
        detail: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        current = self.load()
        if current is None:
            raise UpdateError("update journal has not been started")
        current_phase = UpdatePhase(cast(str, current["phase"]))
        if current_phase in _TERMINAL and phase is not UpdatePhase.RECOVERED:
            raise UpdateError(f"cannot advance terminal update phase {current_phase.value!r}")
        if phase in _ORDER and current_phase in _ORDER:
            if _ORDER.index(phase) < _ORDER.index(current_phase):
                raise UpdateError(f"update phase cannot move from {current_phase.value} to {phase.value}")
        history = current.get("history", [])
        if not isinstance(history, list):
            history = []
        item = self._history_item(phase)
        if detail is not None:
            item["detail"] = dict(detail)
        history.append(item)
        current["phase"] = phase.value
        current["history"] = history
        current["error"] = error
        current["updated_at"] = self._now()
        self._write(current)
        return current

    def recover(self, *, reason: str) -> dict[str, object]:
        current = self.load()
        if current is None:
            raise UpdateError("update journal has not been started")
        if self.is_terminal(current):
            return current
        return self.transition(UpdatePhase.RECOVERED, error=reason)

    @staticmethod
    def is_terminal(document: Mapping[str, object]) -> bool:
        phase = document.get("phase")
        return isinstance(phase, str) and phase in {item.value for item in _TERMINAL}

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @classmethod
    def _history_item(cls, phase: UpdatePhase) -> dict[str, object]:
        return {"phase": phase.value, "at": cls._now()}

    def _write(self, value: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + f".{os.getpid()}.{secrets.token_hex(4)}.tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(self.path)


__all__ = ["UpdateError", "UpdateJournal", "UpdatePhase"]
