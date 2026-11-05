"""Environment-driven application settings."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    return int(value) if value else default


def _float(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    return float(value) if value else default


def _path(name: str, default: Path) -> Path:
    value = os.getenv(name, "").strip()
    path = Path(value) if value else default
    return path if path.is_absolute() else PROJECT_ROOT / path


@dataclass(frozen=True)
class Settings:
    env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    store_path: Path = PROJECT_ROOT / "storage" / "vectors.json"
    db_path: Path = PROJECT_ROOT / "storage" / "app.db"
    documents_dir: Path = PROJECT_ROOT / "storage" / "documents"
    max_upload_mb: int = 25
    max_files_per_upload: int = 10
    trust_proxy: bool = False
    max_concurrent_generations: int = 8
    chat_messages_per_minute: int = 20
    top_k: int = 4
    min_vector_score: float = 0.2
    chunk_size: int = 180
    chunk_overlap: int = 40
    log_level: str = "INFO"
    log_format: str = "text"
    csrf_token: str = ""
    inline_ingestion: bool = False

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @classmethod
    def from_env(cls, **overrides: object) -> "Settings":
        env = os.getenv("APP_ENV", "development").strip().lower() or "development"
        settings = cls(
            env=env,
            host=os.getenv("APP_HOST", "127.0.0.1").strip() or "127.0.0.1",
            port=_int("APP_PORT", 8000),
            store_path=_path("VECTOR_STORE_PATH", cls.store_path),
            db_path=_path("DATABASE_PATH", cls.db_path),
            documents_dir=_path("DOCUMENTS_DIR", cls.documents_dir),
            max_upload_mb=_int("MAX_UPLOAD_MB", 25),
            max_files_per_upload=_int("MAX_FILES_PER_UPLOAD", 10),
            trust_proxy=_bool("TRUST_PROXY", False),
            max_concurrent_generations=_int("MAX_CONCURRENT_GENERATIONS", 8),
            chat_messages_per_minute=_int("CHAT_MESSAGES_PER_MINUTE", 20),
            top_k=_int("RAG_TOP_K", 4),
            min_vector_score=_float("RAG_MIN_VECTOR_SCORE", 0.2),
            chunk_size=_int("CHUNK_SIZE", 180),
            chunk_overlap=_int("CHUNK_OVERLAP", 40),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
            log_format=os.getenv("LOG_FORMAT", "json" if env == "production" else "text").strip().lower(),
            csrf_token=os.getenv("CSRF_TOKEN", "").strip(),
        )
        return replace(settings, **overrides) if overrides else settings
