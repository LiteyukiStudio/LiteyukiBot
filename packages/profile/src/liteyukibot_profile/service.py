"""SQLite-backed profile storage and resource provider."""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

from liteyukibot_permissions import Principal
from liteyukibot_resources import ResourceField, ResourceProvider

from liteyukibot.services import ServiceKey

_SCHEMA_VERSION: Final = 2
_DEFAULT_LANGUAGE: Final = "zh-CN"
_VALID_LANGUAGES: Final = frozenset({"zh-CN", "en"})
PROFILE_SERVICE = ServiceKey("liteyukibot.profile", 2)


class ProfileMigrationRequiredError(RuntimeError):
    """Raised without touching a legacy Profile database."""


@dataclass(frozen=True, slots=True)
class ProfileSnapshot:
    principal: Principal
    nickname: str = ""
    language: str = _DEFAULT_LANGUAGE


class ProfileService(Protocol):
    async def get(self, principal: Principal) -> ProfileSnapshot: ...


def nickname_value(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 32:
        raise ValueError("nickname must contain 1 to 32 characters")
    return normalized


def language_value(value: str) -> str:
    if value not in _VALID_LANGUAGES:
        raise ValueError("language must be 'zh-CN' or 'en'")
    return value


class SQLiteProfileService(ProfileService, ResourceProvider):
    def __init__(self, database: Path) -> None:
        self._connection = sqlite3.connect(database)
        self._lock = asyncio.Lock()
        self._closed = False
        self._initialize()

    def _initialize(self) -> None:
        with self._connection:
            version = self._connection.execute("PRAGMA user_version").fetchone()
            if version is None:
                raise RuntimeError("profile database did not report a schema version")
            current = int(version[0])
            if current == 1:
                raise ProfileMigrationRequiredError("migration_required")
            if current > _SCHEMA_VERSION:
                raise RuntimeError(f"profile database schema {current} is newer than supported {_SCHEMA_VERSION}")
            if current == 0:
                self._connection.execute(
                    """
                    CREATE TABLE profiles (
                        runtime_id TEXT NOT NULL,
                        bot_id TEXT NOT NULL,
                        actor_id TEXT NOT NULL,
                        nickname TEXT NOT NULL DEFAULT '',
                        language TEXT NOT NULL DEFAULT 'zh-CN',
                        PRIMARY KEY (runtime_id, bot_id, actor_id)
                    )
                    """
                )
                self._connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")

    async def get(self, principal: Principal) -> ProfileSnapshot:
        async with self._lock:
            self._ensure_open()
            row = self._connection.execute(
                "SELECT nickname, language FROM profiles WHERE runtime_id = ? AND bot_id = ? AND actor_id = ?",
                (principal.runtime_id, principal.bot_id, principal.actor_id),
            ).fetchone()
        if row is None:
            return ProfileSnapshot(principal)
        return ProfileSnapshot(principal, nickname=str(row[0]), language=str(row[1]))

    async def inspect(self, principal: Principal, field: ResourceField) -> object:
        profile = await self.get(principal)
        return getattr(profile, field.name)

    async def set(self, principal: Principal, field: ResourceField, value: object) -> None:
        if field.name not in {"nickname", "language"}:
            raise ValueError(f"unsupported profile field: {field.name}")
        if not isinstance(value, str):
            raise TypeError(f"profile field {field.name} must be a string")
        async with self._lock:
            self._ensure_open()
            previous = self._row_locked(principal)
            nickname = value if field.name == "nickname" else previous.nickname
            language = value if field.name == "language" else previous.language
            with self._connection:
                self._connection.execute(
                    """
                    INSERT INTO profiles (runtime_id, bot_id, actor_id, nickname, language)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(runtime_id, bot_id, actor_id) DO UPDATE SET
                        nickname = excluded.nickname,
                        language = excluded.language
                    """,
                    (principal.runtime_id, principal.bot_id, principal.actor_id, nickname, language),
                )

    async def delete(self, principal: Principal, field: ResourceField) -> None:
        if field.name not in {"nickname", "language"}:
            raise ValueError(f"unsupported profile field: {field.name}")
        async with self._lock:
            self._ensure_open()
            previous = self._row_locked(principal)
            nickname = "" if field.name == "nickname" else previous.nickname
            language = _DEFAULT_LANGUAGE if field.name == "language" else previous.language
            if nickname == "" and language == _DEFAULT_LANGUAGE:
                with self._connection:
                    self._connection.execute(
                        "DELETE FROM profiles WHERE runtime_id = ? AND bot_id = ? AND actor_id = ?",
                        (principal.runtime_id, principal.bot_id, principal.actor_id),
                    )
                return
            with self._connection:
                self._connection.execute(
                    """
                    INSERT INTO profiles (runtime_id, bot_id, actor_id, nickname, language)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(runtime_id, bot_id, actor_id) DO UPDATE SET
                        nickname = excluded.nickname,
                        language = excluded.language
                    """,
                    (principal.runtime_id, principal.bot_id, principal.actor_id, nickname, language),
                )

    async def close(self) -> None:
        async with self._lock:
            if not self._closed:
                self._connection.close()
                self._closed = True

    def _row_locked(self, principal: Principal) -> ProfileSnapshot:
        row = self._connection.execute(
            "SELECT nickname, language FROM profiles WHERE runtime_id = ? AND bot_id = ? AND actor_id = ?",
            (principal.runtime_id, principal.bot_id, principal.actor_id),
        ).fetchone()
        return ProfileSnapshot(principal) if row is None else ProfileSnapshot(principal, str(row[0]), str(row[1]))

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("profile service is closed")


__all__ = [
    "PROFILE_SERVICE",
    "ProfileMigrationRequiredError",
    "ProfileService",
    "ProfileSnapshot",
    "SQLiteProfileService",
    "language_value",
    "nickname_value",
]
