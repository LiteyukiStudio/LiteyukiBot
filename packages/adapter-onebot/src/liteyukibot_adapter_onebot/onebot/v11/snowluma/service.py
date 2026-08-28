"""Multi-account SnowLuma service for the kernel action backend."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Mapping
from typing import Any

from liteyukibot_kernel import ActionEnvelope, ActionResult, EventBus, EventEnvelope, SendMessage

from .client import CLOSE_TIMEOUT_SECONDS, SnowLumaClient
from .settings import SnowLumaAccountSettings


class OneBotService:
    """Own SnowLuma accounts and expose source-bound ``message.send``."""

    def __init__(
        self,
        accounts: Mapping[str, SnowLumaAccountSettings | Mapping[str, Any]],
        event_bus: EventBus | None = None,
        logger: Any | None = None,
        close_timeout: float = CLOSE_TIMEOUT_SECONDS,
    ) -> None:
        if not math.isfinite(close_timeout) or close_timeout <= 0:
            raise ValueError("close_timeout must be finite and positive")
        self.events = event_bus
        self.event_bus = event_bus
        self.logger = logger
        self._close_timeout = close_timeout
        settings = _normalize_accounts(accounts)
        self.accounts: dict[str, SnowLumaClient] = {
            account_id: SnowLumaClient(
                item,
                runtime_id=account_id,
                on_event=self._publish,
                logger=logger,
            )
            for account_id, item in settings.items()
        }
        self.clients = self.accounts
        self._started = False

    async def start(self) -> None:
        """Start all accounts, isolating each account's startup failure."""

        if self._started:
            return
        self._started = True
        results = await asyncio.gather(*(client.start() for client in self.accounts.values()), return_exceptions=True)
        for client, result in zip(self.accounts.values(), results, strict=True):
            if isinstance(result, BaseException):
                self._log("error", "account {} failed to start: {}", client.self_id, type(result).__name__)

    async def close(self) -> None:
        """Stop every account without allowing one failure to orphan others."""

        self._started = False
        results = await asyncio.gather(
            *(client.close(timeout_seconds=self._close_timeout) for client in self.accounts.values()),
            return_exceptions=True,
        )
        failures: list[BaseException] = []
        for client, result in zip(self.accounts.values(), results, strict=True):
            if isinstance(result, BaseException):
                self._log("error", "account {} failed to close: {}", client.self_id, type(result).__name__)
                failures.append(result)
            else:
                status = client.status()
                background_tasks = _background_task_count(status)
                cleanup_error = status.get("cleanup_error")
                state = status.get("state")
                if (
                    background_tasks > 0
                    or cleanup_error is not None
                    or state in {"stopping", "cleanup_pending", "failed"}
                ):
                    error = TimeoutError(f"account {client.self_id} cleanup is incomplete")
                    self._log("error", "account {} cleanup is incomplete", client.self_id)
                    failures.append(error)
        if failures:
            raise BaseExceptionGroup("OneBot account cleanup failed", failures)

    async def aclose(self) -> None:
        """Alias for :meth:`close` used by kernel lifecycle hosts."""

        await self.close()

    def status(self) -> dict[str, object]:
        """Return JSON-safe account health without exposing credentials."""

        account_status = {account_id: client.status() for account_id, client in self.accounts.items()}
        connected = sum(1 for item in account_status.values() if item["connected"] is True)
        background_tasks = sum(_background_task_count(item) for item in account_status.values())
        if self._started:
            state = "ready" if connected == len(account_status) else "degraded"
        elif any(
            item.get("state") == "failed" or item.get("cleanup_error") is not None
            for item in account_status.values()
        ):
            state = "failed"
        elif background_tasks > 0 or any(
            item.get("state") in {"stopping", "cleanup_pending"} for item in account_status.values()
        ):
            state = "cleanup_pending"
        else:
            state = "stopped"
        return {
            "state": state,
            "started": self._started,
            "connected_accounts": connected,
            "total_accounts": len(account_status),
            "background_tasks": background_tasks,
            "accounts": account_status,
        }

    async def execute(self, event: EventEnvelope | None, action: ActionEnvelope) -> ActionResult:
        """Execute one kernel action as an ``ActionBackend`` callback."""

        if event is None:
            return _failure(action, "SOURCE_EVENT_REQUIRED", "OneBot actions require a source event")
        if action.event_id != event.id or action.runtime_id != event.runtime_id or action.bot_id != event.bot_id:
            return _failure(action, "SOURCE_EVENT_MISMATCH", "OneBot action does not match its source event")
        if not isinstance(action.action, SendMessage):
            return _failure(action, "UNSUPPORTED_ACTION", "OneBot v11 exposes only message.send")
        client = self.accounts.get(action.runtime_id)
        if client is None or client.self_id != action.bot_id:
            return _failure(action, "ACCOUNT_NOT_CONFIGURED", "the source OneBot account is not configured")
        try:
            data = await client.send_message(action.action)
        except Exception as error:
            self._log("error", "account {} action failed: {}", action.runtime_id, type(error).__name__)
            return _failure(action, "ONEBOT_ACTION_FAILED", "OneBot action failed")
        return ActionResult(action_id=action.action_id, success=True, data=data)

    async def execute_action(self, action: ActionEnvelope, *, event: EventEnvelope | None = None) -> ActionResult:
        """Convenience form matching ``ActionService.execute`` argument order."""

        return await self.execute(event, action)

    async def __call__(self, event: EventEnvelope | None, action: ActionEnvelope) -> ActionResult:
        """Allow the service instance to be passed directly as ``ActionBackend``."""

        return await self.execute(event, action)

    async def _publish(self, event: EventEnvelope) -> None:
        if self.events is None:
            return
        try:
            result = await self.events.publish(event)
            if result.status != "processed":
                self._log(
                    "warning",
                    "account {} event {} was not accepted by EventBus: {}",
                    event.runtime_id,
                    event.id,
                    result.status,
                )
        except Exception as error:
            self._log("error", "event {} could not be published: {}", event.id, type(error).__name__)

    def _log(self, level: str, template: str, *args: object) -> None:
        logger = self.logger
        if logger is None:
            return
        try:
            method = getattr(logger, level, None)
            if callable(method):
                method(template, *args)
        except Exception:
            return


def _normalize_accounts(
    accounts: Mapping[str, SnowLumaAccountSettings | Mapping[str, Any]],
) -> dict[str, SnowLumaAccountSettings]:
    if not isinstance(accounts, Mapping):
        raise ValueError("OneBot accounts must be a mapping")
    normalized: dict[str, SnowLumaAccountSettings] = {}
    self_ids: set[str] = set()
    for account_id, raw in accounts.items():
        if not isinstance(account_id, str) or not account_id or account_id != account_id.strip():
            raise ValueError("OneBot account IDs must be non-empty trimmed strings")
        item = raw if isinstance(raw, SnowLumaAccountSettings) else SnowLumaAccountSettings.from_mapping(raw)
        if item.self_id in self_ids:
            raise ValueError(f"duplicate OneBot account self_id {item.self_id!r}")
        self_ids.add(item.self_id)
        normalized[account_id] = item
    return normalized


def _failure(action: ActionEnvelope, code: str, message: str) -> ActionResult:
    return ActionResult(action_id=action.action_id, success=False, error_code=code, error_message=message)


def _background_task_count(status: Mapping[str, object]) -> int:
    value = status.get("background_tasks")
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


OneBotV11Service = OneBotService

__all__ = ["OneBotService", "OneBotV11Service"]
