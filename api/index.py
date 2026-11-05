"""Vercel Python entry point for the Knowledge Assistant.

Vercel imports ``handler`` and creates one instance for every request.  The
application itself is kept at module scope so warm function instances can
reuse the database, vector index, and ingestion worker.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from api.application import Application
from core.config import PROJECT_ROOT, Settings
from core.logging_setup import configure_logging

_RUNTIME_ROOT = Path(tempfile.gettempdir()) / "knowledge-assistant"
_APP: Application | None = None
_APP_LOCK = threading.Lock()


def _runtime_settings() -> Settings:
    """Use Vercel's writable temporary directory for runtime state."""
    _RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    documents_dir = _RUNTIME_ROOT / "documents"
    documents_dir.mkdir(parents=True, exist_ok=True)

    store_path = _RUNTIME_ROOT / "vectors.json"
    bundled_store = PROJECT_ROOT / "storage" / "vectors.json"
    if not store_path.exists() and bundled_store.is_file():
        shutil.copyfile(bundled_store, store_path)
        # The bundled index does not include its ignored SQLite database. Mark
        # its chunks as legacy so startup can reconstruct the document rows.
        payload = json.loads(store_path.read_text(encoding="utf-8"))
        for chunk in payload.get("chunks", []):
            chunk.pop("document_id", None)
        store_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

    return Settings.from_env(
        env="production",
        host="0.0.0.0",
        trust_proxy=True,
        db_path=_RUNTIME_ROOT / "app.db",
        store_path=store_path,
        documents_dir=documents_dir,
    )


def _application() -> Application:
    global _APP
    if _APP is None:
        with _APP_LOCK:
            if _APP is None:
                settings = _runtime_settings()
                configure_logging(settings.log_level, settings.log_format)
                application = Application(settings)
                application.start()
                _APP = application
    return _APP


class handler(BaseHTTPRequestHandler):
    """Forward every Vercel request through the application's guarded router."""

    server_version = "KnowledgeAssistant"
    sys_version = ""

    def do_GET(self) -> None:  # noqa: N802
        _application().dispatch(self)

    do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_GET

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return
