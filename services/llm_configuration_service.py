"""Durable language-model configuration backed by the application database."""

from __future__ import annotations

from typing import Any

from core.database import Database, utc_now


class LLMConfigurationService:
    """Store the singleton LLM configuration in SQLite or Turso."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def load(self) -> dict[str, Any] | None:
        with self.db.connect() as connection:
            row = connection.execute(
                """
                SELECT enabled, service, provider, model, api_key, base_url, source, updated_at
                FROM llm_configuration
                WHERE id = 1
                """
            ).fetchone()
        if row is None:
            return None
        return {
            "enabled": bool(row[0]),
            "service": str(row[1]),
            "provider": str(row[2]),
            "model": str(row[3]),
            "api_key": str(row[4]),
            "base_url": str(row[5]),
            "source": str(row[6]),
            "updated_at": str(row[7]),
        }

    def save(self, configuration: dict[str, str], *, enabled: bool = True, source: str = "admin") -> dict[str, Any]:
        values = (
            1 if enabled else 0,
            configuration["service"],
            configuration["provider"],
            configuration["model"],
            configuration["api_key"],
            configuration["base_url"],
            source,
            utc_now(),
        )
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT INTO llm_configuration
                    (id, enabled, service, provider, model, api_key, base_url, source, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    enabled = excluded.enabled,
                    service = excluded.service,
                    provider = excluded.provider,
                    model = excluded.model,
                    api_key = excluded.api_key,
                    base_url = excluded.base_url,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                values,
            )
        saved = self.load()
        assert saved is not None
        return saved

    def set_enabled(self, enabled: bool) -> dict[str, Any] | None:
        if self.load() is None:
            return None
        with self.db.connect() as connection:
            connection.execute(
                "UPDATE llm_configuration SET enabled = ?, updated_at = ? WHERE id = 1",
                (1 if enabled else 0, utc_now()),
            )
        return self.load()
