"""Local SQLite or remote Turso persistence with ordered schema migrations."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

try:
    import turso_serverless
except ImportError:  # Local-only installs can still use the built-in SQLite driver.
    turso_serverless = None

IntegrityError = (
    (sqlite3.IntegrityError, turso_serverless.IntegrityError)
    if turso_serverless is not None
    else (sqlite3.IntegrityError,)
)
DatabaseError = (
    (sqlite3.Error, turso_serverless.Error)
    if turso_serverless is not None
    else (sqlite3.Error,)
)

MIGRATIONS: list[str] = [
    """
    CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        email TEXT NOT NULL UNIQUE COLLATE NOCASE,
        name TEXT NOT NULL DEFAULT '',
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('customer', 'admin')),
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        last_login_at TEXT
    );

    CREATE TABLE sessions (
        token_hash TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        csrf_token TEXT NOT NULL,
        created_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    );
    CREATE INDEX idx_sessions_user ON sessions(user_id);

    CREATE TABLE conversations (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX idx_conversations_user ON conversations(user_id, updated_at DESC);

    CREATE TABLE messages (
        id INTEGER PRIMARY KEY,
        conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
        content TEXT NOT NULL,
        sources TEXT NOT NULL DEFAULT '[]',
        status TEXT NOT NULL DEFAULT 'complete' CHECK (status IN ('complete', 'stopped')),
        created_at TEXT NOT NULL
    );
    CREATE INDEX idx_messages_conversation ON messages(conversation_id, id);

    CREATE TABLE documents (
        id TEXT PRIMARY KEY,
        filename TEXT NOT NULL,
        stored_name TEXT,
        content_type TEXT,
        size_bytes INTEGER,
        sha256 TEXT,
        status TEXT NOT NULL CHECK (status IN ('queued', 'processing', 'indexed', 'failed')),
        error TEXT,
        chunk_count INTEGER NOT NULL DEFAULT 0,
        embedding_backend TEXT,
        uploaded_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        indexed_at TEXT
    );
    CREATE UNIQUE INDEX idx_documents_sha256 ON documents(sha256) WHERE sha256 IS NOT NULL;
    CREATE UNIQUE INDEX idx_documents_filename ON documents(filename COLLATE NOCASE);

    CREATE TABLE ingestion_events (
        id INTEGER PRIMARY KEY,
        document_id TEXT,
        document_name TEXT NOT NULL,
        level TEXT NOT NULL CHECK (level IN ('info', 'warning', 'error')),
        message TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE INDEX idx_events_created ON ingestion_events(created_at DESC);
    CREATE INDEX idx_events_document ON ingestion_events(document_id);
    """,
    """
    ALTER TABLE documents ADD COLUMN department TEXT NOT NULL DEFAULT 'all';
    ALTER TABLE documents ADD COLUMN allowed_employees TEXT NOT NULL DEFAULT '[]';
    CREATE INDEX idx_documents_department ON documents(department);
    """,
    """
    CREATE TABLE departments (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL UNIQUE COLLATE NOCASE,
        is_system INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );

    INSERT INTO departments (id, name, is_system, created_at) VALUES
        ('hr', 'Human Resources', 1, CURRENT_TIMESTAMP),
        ('finance', 'Finance', 1, CURRENT_TIMESTAMP),
        ('it', 'Information Technology', 1, CURRENT_TIMESTAMP),
        ('operations', 'Operations', 1, CURRENT_TIMESTAMP),
        ('sales', 'Sales', 1, CURRENT_TIMESTAMP),
        ('marketing', 'Marketing', 1, CURRENT_TIMESTAMP),
        ('legal', 'Legal', 1, CURRENT_TIMESTAMP),
        ('executive', 'Executive', 1, CURRENT_TIMESTAMP),
        ('other', 'Other', 1, CURRENT_TIMESTAMP);

    CREATE TABLE employees (
        id INTEGER PRIMARY KEY,
        employee_id TEXT NOT NULL UNIQUE COLLATE NOCASE,
        name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        department_id TEXT NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX idx_employees_department ON employees(department_id);
    CREATE INDEX idx_employees_status ON employees(status);
    """,
    """
    ALTER TABLE employees ADD COLUMN email TEXT COLLATE NOCASE;
    CREATE UNIQUE INDEX idx_employees_email ON employees(email) WHERE email IS NOT NULL;
    """,
    """
    ALTER TABLE employees ADD COLUMN role TEXT NOT NULL DEFAULT 'employee'
        CHECK (role IN ('employee', 'admin'));

    CREATE TABLE auth_sessions (
        token_hash TEXT PRIMARY KEY,
        employee INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    );
    CREATE INDEX idx_auth_sessions_employee ON auth_sessions(employee);
    CREATE INDEX idx_auth_sessions_expiry ON auth_sessions(expires_at);
    """,
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def utc_after(hours: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat(timespec="seconds")


class Database:
    """Open short-lived local or remote connections so threads never share one."""

    def __init__(self, path: Path | str, *, turso_url: str = "", turso_auth_token: str = "") -> None:
        self.path = Path(path)
        self.turso_url = turso_url.strip()
        self.turso_auth_token = turso_auth_token.strip()
        if bool(self.turso_url) != bool(self.turso_auth_token):
            raise RuntimeError("TURSO_DATABASE_URL and TURSO_AUTH_TOKEN must be configured together.")
        if self.turso_url and turso_serverless is None:
            raise RuntimeError("Install turso_serverless to use TURSO_DATABASE_URL.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    @contextmanager
    def connect(self) -> Iterator[Any]:
        if self.turso_url:
            connection = turso_serverless.connect(self.turso_url, auth_token=self.turso_auth_token)
            connection.row_factory = turso_serverless.Row
        else:
            connection = sqlite3.connect(self.path, timeout=10)
            connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:  # commits on success, rolls back on error
                yield connection
        finally:
            connection.close()

    @property
    def schema_version(self) -> int:
        with self.connect() as connection:
            return int(connection.execute("PRAGMA user_version").fetchone()[0])

    def migrate(self) -> None:
        with self.connect() as connection:
            if not self.turso_url:
                connection.execute("PRAGMA journal_mode = WAL")
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
                connection.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;")

    def ping(self) -> bool:
        try:
            with self.connect() as connection:
                connection.execute("SELECT 1").fetchone()
            return True
        except DatabaseError:
            return False

    def backup_to(self, target: Path) -> None:
        if self.turso_url:
            raise RuntimeError("Use the Turso dashboard to back up a remote database.")
        target.parent.mkdir(parents=True, exist_ok=True)
        source = sqlite3.connect(self.path)
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
