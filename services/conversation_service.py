"""Per-user conversation history stored in SQLite."""

from __future__ import annotations

import json
import uuid
from typing import Any

from core.database import Database, utc_now

DEFAULT_TITLE = "New chat"


class ConversationService:
    """Every read and write is scoped by user id, so one customer can never load another's chats."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def list(self, user_id: int) -> list[dict[str, Any]]:
        with self.db.connect() as connection:
            rows = connection.execute(
                "SELECT id, title, created_at, updated_at FROM conversations WHERE user_id = ?"
                " ORDER BY updated_at DESC LIMIT 200",
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create(self, user_id: int, title: str = DEFAULT_TITLE) -> dict[str, Any]:
        conversation = {
            "id": uuid.uuid4().hex,
            "title": (title or DEFAULT_TITLE).strip()[:120] or DEFAULT_TITLE,
            "created_at": utc_now(),
        }
        conversation["updated_at"] = conversation["created_at"]
        with self.db.connect() as connection:
            connection.execute(
                "INSERT INTO conversations (id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (conversation["id"], user_id, conversation["title"], conversation["created_at"], conversation["updated_at"]),
            )
        return conversation

    def get(self, user_id: int, conversation_id: str) -> dict[str, Any] | None:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT id, title, created_at, updated_at FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            ).fetchone()
            if row is None:
                return None
            messages = connection.execute(
                "SELECT id, role, content, sources, status, created_at FROM messages"
                " WHERE conversation_id = ? ORDER BY id",
                (conversation_id,),
            ).fetchall()
        return {
            **dict(row),
            "messages": [{**dict(message), "sources": json.loads(message["sources"])} for message in messages],
        }

    def owns(self, user_id: int, conversation_id: str) -> bool:
        with self.db.connect() as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM conversations WHERE id = ? AND user_id = ?", (conversation_id, user_id)
                ).fetchone()
                is not None
            )

    def rename(self, user_id: int, conversation_id: str, title: str) -> bool:
        title = (title or "").strip()[:120]
        if not title:
            raise ValueError("Title cannot be empty.")
        with self.db.connect() as connection:
            cursor = connection.execute(
                "UPDATE conversations SET title = ? WHERE id = ? AND user_id = ?", (title, conversation_id, user_id)
            )
        return cursor.rowcount > 0

    def delete(self, user_id: int, conversation_id: str) -> bool:
        with self.db.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM conversations WHERE id = ? AND user_id = ?", (conversation_id, user_id)
            )
        return cursor.rowcount > 0

    def delete_all(self, user_id: int) -> int:
        """Delete every conversation (and, via cascade, its messages); return how many were removed."""
        with self.db.connect() as connection:
            cursor = connection.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
        return cursor.rowcount

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        sources: list[dict[str, Any]] | None = None,
        status: str = "complete",
    ) -> tuple[int, str]:
        """Store a message and return ``(message_id, conversation_title)``."""
        now = utc_now()
        with self.db.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO messages (conversation_id, role, content, sources, status, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (conversation_id, role, content, json.dumps(sources or []), status, now),
            )
            title = connection.execute("SELECT title FROM conversations WHERE id = ?", (conversation_id,)).fetchone()[0]
            if role == "user" and title == DEFAULT_TITLE:
                title = " ".join(content.split())[:60] or DEFAULT_TITLE
            connection.execute(
                "UPDATE conversations SET updated_at = ?, title = ? WHERE id = ?", (now, title, conversation_id)
            )
        return int(cursor.lastrowid), title

    def history(self, conversation_id: str, before_message_id: int, limit: int = 6) -> list[dict[str, str]]:
        with self.db.connect() as connection:
            rows = connection.execute(
                "SELECT role, content FROM messages WHERE conversation_id = ? AND id < ? AND content != ''"
                " ORDER BY id DESC LIMIT ?",
                (conversation_id, before_message_id, limit),
            ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]

    def prepare_regenerate(self, conversation_id: str) -> tuple[int, str] | None:
        """Drop trailing assistant replies; return the last user message to answer again."""
        with self.db.connect() as connection:
            last_user = connection.execute(
                "SELECT id, content FROM messages WHERE conversation_id = ? AND role = 'user' ORDER BY id DESC LIMIT 1",
                (conversation_id,),
            ).fetchone()
            if last_user is None:
                return None
            connection.execute(
                "DELETE FROM messages WHERE conversation_id = ? AND role = 'assistant' AND id > ?",
                (conversation_id, last_user["id"]),
            )
        return int(last_user["id"]), last_user["content"]
