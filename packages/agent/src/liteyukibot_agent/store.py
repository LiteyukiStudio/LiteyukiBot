"""Small SQLite conversation history store owned by the native agent runtime."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class ConversationStore:
    def __init__(self, path: Path) -> None:
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
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO messages (runtime_id, bot_id, conversation_id, role, content)
            VALUES (?, ?, ?, ?, ?)
            """,
            (runtime_id, bot_id, conversation_id, role, json.dumps(content, ensure_ascii=True)),
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()
