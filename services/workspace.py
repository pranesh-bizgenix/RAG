"""The single shared workspace that owns all conversations (the app has no user accounts)."""

from __future__ import annotations

from core.database import Database, utc_now

WORKSPACE_EMAIL = "workspace@local"


def ensure_workspace(db: Database) -> int:
    """Return the id of the built-in workspace row, creating it on first start."""
    with db.connect() as connection:
        row = connection.execute("SELECT id FROM users WHERE email = ?", (WORKSPACE_EMAIL,)).fetchone()
        if row:
            return int(row["id"])
        cursor = connection.execute(
            # "!" is never a valid password hash, so this row can't be used to sign in anywhere.
            "INSERT INTO users (email, name, password_hash, role, created_at) VALUES (?, 'Workspace', '!', 'admin', ?)",
            (WORKSPACE_EMAIL, utc_now()),
        )
        return int(cursor.lastrowid)
