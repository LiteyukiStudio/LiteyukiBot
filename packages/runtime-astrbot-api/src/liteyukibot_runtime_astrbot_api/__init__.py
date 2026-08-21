"""Typed, AstrBot-independent Alpha8 runtime API facade."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict

from liteyukibot.events import JsonValue
from liteyukibot.runtime_api import (
    RuntimeApiBackend,
    RuntimeApiError,
    RuntimeBinding,
    RuntimeCallContext,
    RuntimeNamespaceProxy,
)


class AstrBotEventSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    platform_id: str
    platform_name: str
    bot_id: str
    session_id: str
    group_id: str | None = None
    sender_id: str | None = None
    message: str
    message_type: str


class AstrBotEventProxy(RuntimeNamespaceProxy):
    """Typed facade for the Alpha8-safe subset of AstrBot's current event."""

    async def snapshot(self) -> AstrBotEventSnapshot:
        value = await self.call("snapshot")
        if not isinstance(value, Mapping):
            raise RuntimeApiError(self.binding.runtime, self.binding.api, "snapshot", "RUNTIME_API_INVALID_RESULT")
        try:
            return AstrBotEventSnapshot.model_validate(value)
        except ValueError as error:
            raise RuntimeApiError(
                self.binding.runtime,
                self.binding.api,
                "snapshot",
                "RUNTIME_API_INVALID_RESULT",
            ) from error

    async def send(self, message: str) -> Mapping[str, JsonValue]:
        value = await self.call("send", {"message": message})
        if not isinstance(value, Mapping):
            raise RuntimeApiError(self.binding.runtime, self.binding.api, "send", "RUNTIME_API_INVALID_RESULT")
        return value


def proxy_factory(
    *,
    binding: RuntimeBinding,
    backend: RuntimeApiBackend | None,
    context: RuntimeCallContext | None,
    reason: str = "unavailable",
) -> AstrBotEventProxy:
    return AstrBotEventProxy(binding, backend, context, reason=reason)


__all__ = ["AstrBotEventProxy", "AstrBotEventSnapshot", "proxy_factory"]
