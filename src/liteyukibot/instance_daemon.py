"""Native-plugin access to the local instance daemon's narrow lifecycle API."""

from __future__ import annotations

import os
from pathlib import Path
from time import monotonic
from typing import Any

from .control import request_control
from .services import ServiceKey

INSTANCE_DAEMON_SERVICE = ServiceKey("liteyukibot.instance_daemon", 1)


class InstanceDaemonService:
    """Expose JSON-safe daemon snapshots and rate-limited restart requests."""

    def __init__(self, descriptor_path: Path, *, minimum_restart_interval_seconds: float = 5.0) -> None:
        self.descriptor_path = descriptor_path
        self.minimum_restart_interval_seconds = minimum_restart_interval_seconds
        self._last_restart = float("-inf")

    @classmethod
    def from_environment(cls) -> InstanceDaemonService | None:
        raw_path = os.environ.get("LITEYUKI_DAEMON_DESCRIPTOR")
        return cls(Path(raw_path)) if raw_path else None

    async def snapshot(self) -> dict[str, Any]:
        result = await request_control(self.descriptor_path, "status")
        if not isinstance(result, dict):
            raise RuntimeError("daemon returned an invalid status snapshot")
        return result

    async def request_restart(self, reason: str) -> bool:
        if not reason.strip():
            raise ValueError("restart reason must not be empty")
        now = monotonic()
        if now - self._last_restart < self.minimum_restart_interval_seconds:
            return False
        await request_control(self.descriptor_path, "restart", reason=reason.strip())
        self._last_restart = now
        return True


__all__ = ["INSTANCE_DAEMON_SERVICE", "InstanceDaemonService"]
