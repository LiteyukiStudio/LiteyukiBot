"""Bounded SQLite conversation history owned by the Agent bridge."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class ConversationStore:
    """Represent the conversation store contract."""
    def __init__(self, path: Path) -> None:
        """Initialize the conversation store.

        Args:
            path: Filesystem or logical resource path.

        Returns:
            None.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path)
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                runtime_id TEXT NOT NULL,
                bot_id TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    def messages(
        self,
        runtime_id: str,
        bot_id: str,
        conversation_id: str,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Implement the messages operation for the conversation store.

        Args:
            runtime_id: Stable runtime identifier.
            bot_id: Stable identifier for the bot.
            conversation_id: Stable identifier for the conversation.
            limit: Maximum number of records to return.

        Returns:
            The `list[dict[str, Any]]` result produced by the operation.
        """
        if limit < 1:
            raise ValueError("conversation history limit must be at least 1")
        rows = self._connection.execute(
            """
            SELECT role, content FROM (
                SELECT role, content, sequence FROM messages
                WHERE runtime_id = ? AND bot_id = ? AND conversation_id = ?
                ORDER BY sequence DESC
                LIMIT ?
            ) ORDER BY sequence
            """,
            (runtime_id, bot_id, conversation_id, limit),
        ).fetchall()
        return [{"role": role, "content": json.loads(content)} for role, content in rows]

    def append(
        self,
        runtime_id: str,
        bot_id: str,
        conversation_id: str,
        role: str,
        content: Mapping[str, object] | str,
        *,
        retain: int,
    ) -> None:
        """Implement the append operation for the conversation store.

        Args:
            runtime_id: Stable runtime identifier.
            bot_id: Stable identifier for the bot.
            conversation_id: Stable identifier for the conversation.
            role: The role value used by the operation.
            content: The content value used by the operation.
            retain: The retain value used by the operation.

        Returns:
            None.
        """
        if retain < 1:
            raise ValueError("conversation history retention must be at least 1")
        self._connection.execute(
            """
            INSERT INTO messages (runtime_id, bot_id, conversation_id, role, content)
            VALUES (?, ?, ?, ?, ?)
            """,
            (runtime_id, bot_id, conversation_id, role, json.dumps(content, ensure_ascii=True)),
        )
        self._connection.execute(
            """
            DELETE FROM messages
            WHERE runtime_id = ? AND bot_id = ? AND conversation_id = ?
              AND sequence NOT IN (
                SELECT sequence FROM messages
                WHERE runtime_id = ? AND bot_id = ? AND conversation_id = ?
                ORDER BY sequence DESC
                LIMIT ?
            )
            """,
            (
                runtime_id,
                bot_id,
                conversation_id,
                runtime_id,
                bot_id,
                conversation_id,
                retain,
            ),
        )
        self._connection.commit()

    def clear(self, runtime_id: str, bot_id: str, conversation_id: str) -> int:
        """Delete one source-scoped conversation and return its removed message count.

        Args:
            runtime_id: Stable runtime identifier.
            bot_id: Stable identifier for the bot.
            conversation_id: Stable identifier for the conversation.

        Returns:
            The `int` result produced by the operation.
        """

        cursor = self._connection.execute(
            """
            DELETE FROM messages
            WHERE runtime_id = ? AND bot_id = ? AND conversation_id = ?
            """,
            (runtime_id, bot_id, conversation_id),
        )
        self._connection.commit()
        return cursor.rowcount

    def close(self) -> None:
        """Close the conversation store and release its owned resources.

        Returns:
            None.
        """
        self._connection.close()
