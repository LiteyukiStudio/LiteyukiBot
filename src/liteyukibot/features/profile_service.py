"""SQLite-backed profile storage and resource provider."""

from __future__ import annotations

import asyncio
import contextlib
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol, TypeVar

from liteyukibot_kernel.services import ServiceKey

from .permissions import Principal
from .resources_models import ResourceField, ResourceProvider

_SCHEMA_VERSION: Final = 2
_DEFAULT_LANGUAGE: Final = "zh-CN"
_VALID_LANGUAGES: Final = frozenset({"zh-CN", "en"})
PROFILE_SERVICE = ServiceKey("liteyukibot.profile", 2)
_DatabaseResult = TypeVar("_DatabaseResult")


class ProfileMigrationRequiredError(RuntimeError):
    """Raised without touching a legacy Profile database."""


@dataclass(frozen=True, slots=True)
class ProfileSnapshot:
    """Represent the validated profile snapshot contract."""
    principal: Principal
    nickname: str = ""
    language: str = _DEFAULT_LANGUAGE


class ProfileService(Protocol):
    """Define the structural interface required from a profile service."""
    async def get(self, principal: Principal) -> ProfileSnapshot:
        """Return the profile service operation.

        Args:
            principal: Authenticated principal requesting the operation.

        Returns:
            The `ProfileSnapshot` result produced by the operation.
        """
        ...


def nickname_value(value: str) -> str:
    """Implement the nickname value operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `str` result produced by the operation.
    """
    normalized = value.strip()
    if not normalized or len(normalized) > 32:
        raise ValueError("nickname must contain 1 to 32 characters")
    return normalized


def language_value(value: str) -> str:
    """Implement the language value operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `str` result produced by the operation.
    """
    if value not in _VALID_LANGUAGES:
        raise ValueError("language must be 'zh-CN' or 'en'")
    return value


class SQLiteProfileService(ProfileService, ResourceProvider):
    """Represent the s q lite profile service contract."""
    def __init__(self, database: Path) -> None:
        """Initialize the s q lite profile service.

        Args:
            database: The database value used by the operation.

        Returns:
            None.
        """
        self._database = Path(database)
        self._lock = asyncio.Lock()
        self._closed = False
        self._initialized = False
        self._database_tasks: set[asyncio.Task[Any]] = set()

    def _initialize(self) -> None:
        """Initialize the s q lite profile service operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `SQLiteProfileService._initialize`. It delegates to
            `fetchone`, `execute`, `int` while keeping intermediate state local to the owning operation.
        """
        connection = self._connect()
        try:
            with connection:
                version = connection.execute("PRAGMA user_version").fetchone()
                if version is None:
                    raise RuntimeError("profile database did not report a schema version")
                current = int(version[0])
                if current == 1:
                    raise ProfileMigrationRequiredError("migration_required")
                if current > _SCHEMA_VERSION:
                    raise RuntimeError(f"profile database schema {current} is newer than supported {_SCHEMA_VERSION}")
                if current == 0:
                    connection.execute(
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
                    connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
        finally:
            connection.close()

    async def start(self) -> None:
        """Initialize the database without blocking the event loop."""

        async with self._lock:
            await self._ensure_started()

    async def get(self, principal: Principal) -> ProfileSnapshot:
        """Return the s q lite profile service operation.

        Args:
            principal: Authenticated principal requesting the operation.

        Returns:
            The `ProfileSnapshot` result produced by the operation.
        """
        async with self._lock:
            await self._ensure_started()
            return await self._run_database(lambda: self._row_locked(principal))

    async def inspect(self, principal: Principal, field: ResourceField) -> object:
        """Inspect the s q lite profile service operation.

        Args:
            principal: Authenticated principal requesting the operation.
            field: The field value used by the operation.

        Returns:
            The `object` result produced by the operation.
        """
        profile = await self.get(principal)
        return getattr(profile, field.name)

    async def set(self, principal: Principal, field: ResourceField, value: object) -> None:
        """Set the s q lite profile service operation.

        Args:
            principal: Authenticated principal requesting the operation.
            field: The field value used by the operation.
            value: Value to validate, transform, or store.

        Returns:
            None.
        """
        if field.name not in {"nickname", "language"}:
            raise ValueError(f"unsupported profile field: {field.name}")
        if not isinstance(value, str):
            raise TypeError(f"profile field {field.name} must be a string")
        async with self._lock:
            await self._ensure_started()
            await self._run_database(lambda: self._set_locked(principal, field.name, value))

    async def delete(self, principal: Principal, field: ResourceField) -> None:
        """Delete the s q lite profile service operation.

        Args:
            principal: Authenticated principal requesting the operation.
            field: The field value used by the operation.

        Returns:
            None.
        """
        if field.name not in {"nickname", "language"}:
            raise ValueError(f"unsupported profile field: {field.name}")
        async with self._lock:
            await self._ensure_started()
            await self._run_database(lambda: self._delete_locked(principal, field.name))

    async def close(self) -> None:
        """Close the s q lite profile service and release its owned resources.

        Returns:
            None.
        """
        async with self._lock:
            self._closed = True
        await self._wait_for_database_tasks()

    def _set_locked(self, principal: Principal, field_name: str, value: str) -> None:
        """Write one profile field from a worker thread while the async lock is held."""

        connection = self._connect()
        try:
            previous = self._row_from_connection(connection, principal)
            nickname = value if field_name == "nickname" else previous.nickname
            language = value if field_name == "language" else previous.language
            with connection:
                connection.execute(
                    """
                    INSERT INTO profiles (runtime_id, bot_id, actor_id, nickname, language)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(runtime_id, bot_id, actor_id) DO UPDATE SET
                        nickname = excluded.nickname,
                        language = excluded.language
                    """,
                    (principal.runtime_id, principal.bot_id, principal.actor_id, nickname, language),
                )
        finally:
            connection.close()

    def _delete_locked(self, principal: Principal, field_name: str) -> None:
        """Delete one profile field from a worker thread while the async lock is held."""

        connection = self._connect()
        try:
            previous = self._row_from_connection(connection, principal)
            nickname = "" if field_name == "nickname" else previous.nickname
            language = _DEFAULT_LANGUAGE if field_name == "language" else previous.language
            with connection:
                if nickname == "" and language == _DEFAULT_LANGUAGE:
                    connection.execute(
                        "DELETE FROM profiles WHERE runtime_id = ? AND bot_id = ? AND actor_id = ?",
                        (principal.runtime_id, principal.bot_id, principal.actor_id),
                    )
                    return
                connection.execute(
                    """
                    INSERT INTO profiles (runtime_id, bot_id, actor_id, nickname, language)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(runtime_id, bot_id, actor_id) DO UPDATE SET
                        nickname = excluded.nickname,
                        language = excluded.language
                    """,
                    (principal.runtime_id, principal.bot_id, principal.actor_id, nickname, language),
                )
        finally:
            connection.close()

    def _row_locked(self, principal: Principal) -> ProfileSnapshot:
        """Implement the row locked operation for the s q lite profile service.

        Args:
            principal: Authenticated principal requesting the operation.

        Returns:
            The `ProfileSnapshot` result produced by the operation.

        Notes:
            Internal implementation detail for `SQLiteProfileService._row_locked`. It delegates to
            `fetchone`, `execute` while keeping intermediate state local to the owning operation.
        """
        connection = self._connect()
        try:
            return self._row_from_connection(connection, principal)
        finally:
            connection.close()

    def _row_from_connection(self, connection: sqlite3.Connection, principal: Principal) -> ProfileSnapshot:
        """Read one profile row using a connection owned by the worker thread."""

        row = connection.execute(
            "SELECT nickname, language FROM profiles WHERE runtime_id = ? AND bot_id = ? AND actor_id = ?",
            (principal.runtime_id, principal.bot_id, principal.actor_id),
        ).fetchone()
        return ProfileSnapshot(principal) if row is None else ProfileSnapshot(principal, str(row[0]), str(row[1]))

    def _connect(self) -> sqlite3.Connection:
        """Open a short-lived connection for the current worker thread."""

        connection = sqlite3.connect(self._database, timeout=5.0)
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    async def _ensure_started(self) -> None:
        """Initialize the schema once while the service lock is held."""

        self._ensure_open()
        if not self._initialized:
            await self._run_database(self._initialize)
            self._initialized = True

    async def _run_database(self, operation: Callable[[], _DatabaseResult]) -> _DatabaseResult:
        """Run one SQLite operation and keep its worker tracked through cancellation."""

        await self._wait_for_database_tasks()
        task = asyncio.create_task(asyncio.to_thread(operation), name="liteyukibot-profile-database")
        self._database_tasks.add(task)
        task.add_done_callback(self._database_task_done)
        return await asyncio.shield(task)

    async def _wait_for_database_tasks(self) -> None:
        """Wait for worker threads that cannot be interrupted by asyncio cancellation."""

        while self._database_tasks:
            drain = asyncio.gather(*tuple(self._database_tasks), return_exceptions=True)
            await asyncio.shield(drain)

    def _database_task_done(self, task: asyncio.Task[Any]) -> None:
        """Forget a completed worker and consume an exception if its caller was cancelled."""

        self._database_tasks.discard(task)
        with contextlib.suppress(BaseException):
            task.exception()

    def _ensure_open(self) -> None:
        """Implement the ensure open operation for the s q lite profile service.

        Returns:
            None.

        Notes:
            Internal implementation detail for `SQLiteProfileService._ensure_open`. It performs the local
            state transition directly and is not a stable extension boundary.
        """
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
