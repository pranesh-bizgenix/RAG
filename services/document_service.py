"""Knowledge-base documents: storage, background indexing, status tracking, and deletion."""

from __future__ import annotations

import hashlib
import logging
import os
import queue
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from core.config import Settings
from core.database import Database, utc_now
from core.logging_setup import log_fields
from parsers import load_documents
from rag.embedder import APIEmbeddingClient, embed_texts
from rag.query import describe_location
from services.upload_validation import UploadError, safe_filename, validate_upload
from ui.admin import chunk_documents
from vectorstore import LocalVectorStore
from vectorstore.stats import document_name

logger = logging.getLogger(__name__)

STATUSES = ("queued", "processing", "indexed", "failed")
_EMBED_BATCH = 64
# How long a deleted document stays restorable (kept in memory, so a restart also ends the window).
UNDO_SECONDS = 60


class DocumentError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _size_label(size: int) -> str:
    for unit in ("bytes", "KB", "MB"):
        if size < 1024 or unit == "MB":
            return f"{size:.0f} {unit}" if unit == "bytes" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} MB"


def _describe(exc: BaseException) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message if len(message) <= 500 else f"{message[:497]}..."


class DocumentService:
    def __init__(
        self,
        db: Database,
        store: LocalVectorStore,
        settings: Settings,
        embedding_client: APIEmbeddingClient | None = None,
    ) -> None:
        self.db = db
        self.store = store
        self.settings = settings
        self.embedding_client = embedding_client or APIEmbeddingClient()
        self.documents_dir = settings.documents_dir
        self.documents_dir.mkdir(parents=True, exist_ok=True)
        self._queue: queue.Queue[tuple[str, Any] | None] = queue.Queue()
        # Guards job bookkeeping and every store mutation, so deletes never race indexing.
        self._lock = threading.RLock()
        self._pending: set[str] = set()
        self._processing: str | None = None
        self._reindex_all_pending = False
        self._worker: threading.Thread | None = None
        # Recently deleted documents, by id: database row, chunks, file bytes and expiry.
        self._trash: dict[str, dict[str, Any]] = {}

    # Lifecycle.

    def start(self) -> None:
        self.reconcile()
        if self.settings.inline_ingestion:
            return
        self._worker = threading.Thread(target=self._run, name="ingestion-worker", daemon=True)
        self._worker.start()

    def stop(self) -> None:
        if self._worker and self._worker.is_alive():
            self._queue.put(None)
            self._worker.join(timeout=10)

    @property
    def worker_alive(self) -> bool:
        return self.settings.inline_ingestion or bool(self._worker and self._worker.is_alive())

    def wait_idle(self, timeout: float = 30) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._queue.unfinished_tasks == 0:
                return True
            time.sleep(0.05)
        return False

    # Embedding configuration.

    def configured_embedding(self) -> tuple[str, str]:
        if self.embedding_client.is_configured:
            return "api", self.embedding_client.model
        return "local-hash", ""

    def index_embedding(self) -> tuple[str, str]:
        backend = "api" if self.store.embedding_backend in {"api", "openai"} else self.store.embedding_backend
        return backend, self.store.embedding_model

    def needs_reindex(self) -> bool:
        if not self.store.chunks:
            return False
        backend, model = self.index_embedding()
        configured_backend, configured_model = self.configured_embedding()
        # Indexes built before model names were recorded only tell us the backend.
        return backend != configured_backend or (bool(model) and model != configured_model)

    def _target_embedding(self) -> tuple[str, str]:
        """New chunks must share the existing index's embedding space."""
        if not self.store.chunks:
            return self.configured_embedding()
        backend, model = self.index_embedding()
        if backend == "local-hash":
            return backend, model
        if not self.embedding_client.is_configured or (model and model != self.embedding_client.model):
            raise RuntimeError(
                "The index was built with a different embedding model than the current configuration. "
                "Reindex all documents from the Knowledge base page first."
            )
        return backend, model or self.embedding_client.model

    def _embed(self, texts: list[str], backend: str) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _EMBED_BATCH):
            vectors.extend(embed_texts(texts[start : start + _EMBED_BATCH], backend, self.embedding_client))
        if len(vectors) != len(texts):
            raise RuntimeError("The embedding service returned an unexpected number of vectors.")
        return vectors

    # Store commits: persist or roll back the in-memory index, never leave them diverged.

    def _commit_store(self, mutate: Callable[[], Any]) -> Any:
        with self._lock:
            previous = (
                self.store.chunks,
                self.store.embedding_backend,
                self.store.dimension,
                self.store.embedding_model,
            )
            try:
                result = mutate()
                self.store.save()
                return result
            except Exception:
                self.store.chunks = previous[0]
                self.store.set_metadata(previous[1], previous[2], previous[3])
                raise

    # Database helpers.

    def _row(self, document_id: str) -> sqlite3.Row | None:
        with self.db.connect() as connection:
            return connection.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()

    def _update(self, document_id: str, **fields: Any) -> None:
        fields["updated_at"] = utc_now()
        assignments = ", ".join(f"{name} = ?" for name in fields)
        with self.db.connect() as connection:
            connection.execute(f"UPDATE documents SET {assignments} WHERE id = ?", (*fields.values(), document_id))

    def _event(self, document_id: str | None, document_name_: str, level: str, message: str) -> None:
        with self.db.connect() as connection:
            connection.execute(
                "INSERT INTO ingestion_events (document_id, document_name, level, message, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (document_id, document_name_, level, message, utc_now()),
            )
        log = logger.error if level == "error" else logger.warning if level == "warning" else logger.info
        log(message, extra=log_fields(document=document_name_, document_id=document_id))

    def _file_path(self, row: sqlite3.Row) -> Path | None:
        if not row["stored_name"]:
            return None
        path = (self.documents_dir / row["stored_name"]).resolve()
        return path if path.parent == self.documents_dir.resolve() else None

    # Startup reconciliation.

    def reconcile(self) -> None:
        """Repair the index/database after upgrades or an unclean shutdown."""
        self._import_legacy_chunks()
        with self.db.connect() as connection:
            rows = connection.execute("SELECT id, filename, status FROM documents").fetchall()
        known = {row["id"] for row in rows}

        orphaned = self.store.document_ids() - known
        if orphaned:
            removed = self._commit_store(lambda: sum(self.store.remove_document(item) for item in orphaned))
            self._event(None, "index", "warning", f"Removed {removed} orphaned chunks left by deleted documents.")

        counts: dict[str, int] = {}
        for chunk in self.store.chunks:
            counts[str(chunk.get("document_id"))] = counts.get(str(chunk.get("document_id")), 0) + 1
        resume_inline: list[str] = []
        for row in rows:
            if row["status"] in {"queued", "processing"}:
                self._update(row["id"], status="queued")
                self._pending.add(row["id"])
                if self.settings.inline_ingestion:
                    resume_inline.append(row["id"])
                else:
                    self._queue.put(("document", row["id"]))
                self._event(row["id"], row["filename"], "info", "Re-queued after restart.")
            elif row["status"] == "indexed" and not counts.get(row["id"]):
                self._update(row["id"], status="failed", chunk_count=0, error="Index entries are missing. Reindex this document.")
                self._event(row["id"], row["filename"], "warning", "Index entries were missing; marked as failed.")
            elif row["status"] == "indexed":
                self._update(row["id"], chunk_count=counts[row["id"]])
        for document_id in resume_inline:
            self._process_document(document_id)

    def _import_legacy_chunks(self) -> None:
        """Adopt chunks indexed before document tracking existed, grouped by filename."""
        legacy = [chunk for chunk in self.store.chunks if not chunk.get("document_id")]
        if not legacy:
            return
        names: dict[str, str] = {}
        now = utc_now()
        backend, _ = self.index_embedding()
        with self.db.connect() as connection:
            for chunk in legacy:
                name = document_name(str(chunk.get("source", ""))).strip() or "unknown"
                if name in names:
                    continue
                existing = connection.execute("SELECT id FROM documents WHERE filename = ?", (name,)).fetchone()
                if existing:
                    names[name] = existing["id"]
                    continue
                names[name] = uuid.uuid4().hex
                connection.execute(
                    "INSERT INTO documents (id, filename, status, chunk_count, embedding_backend, created_at,"
                    " updated_at, indexed_at) VALUES (?, ?, 'indexed', 0, ?, ?, ?, ?)",
                    (names[name], name, backend, now, now, now),
                )
        self._commit_store(
            lambda: setattr(
                self.store,
                "chunks",
                [
                    chunk
                    if chunk.get("document_id")
                    else {**chunk, "document_id": names[document_name(str(chunk.get("source", ""))).strip() or "unknown"]}
                    for chunk in self.store.chunks
                ],
            )
        )
        for name, document_id in names.items():
            self._event(document_id, name, "info", "Imported from the existing vector store (original file not retained).")

    # Uploads.

    def upload(self, files: list[tuple[str, bytes]], user_id: int | None) -> list[dict[str, Any]]:
        if not files:
            raise DocumentError("Select at least one file to upload.")
        if len(files) > self.settings.max_files_per_upload:
            raise DocumentError(f"Upload at most {self.settings.max_files_per_upload} files at a time.")
        results = []
        for raw_name, data in files:
            try:
                results.append({"filename": raw_name, "ok": True, "document": self._store_upload(raw_name, data, user_id)})
            except UploadError as exc:
                try:
                    display = safe_filename(raw_name)
                except UploadError:
                    display = "file"
                results.append({"filename": display, "ok": False, "error": str(exc)})
        return results

    def _store_upload(self, raw_name: str, data: bytes, user_id: int | None) -> dict[str, Any]:
        filename, extension, content_type = validate_upload(raw_name, data, self.settings.max_upload_bytes)
        digest = hashlib.sha256(data).hexdigest()
        document_id = uuid.uuid4().hex
        stored_name = f"{document_id}{extension}"
        now = utc_now()
        with self._lock:
            with self.db.connect() as connection:
                duplicate = connection.execute(
                    "SELECT filename, sha256 FROM documents WHERE sha256 = ? OR filename = ?", (digest, filename)
                ).fetchone()
            if duplicate and duplicate["sha256"] == digest:
                raise UploadError(f"This file is already in the knowledge base as \"{duplicate['filename']}\".")
            if duplicate:
                raise UploadError(f"A document named \"{filename}\" already exists. Delete it first or rename the file.")

            temporary = self.documents_dir / f"{stored_name}.part"
            temporary.write_bytes(data)
            os.replace(temporary, self.documents_dir / stored_name)
            try:
                with self.db.connect() as connection:
                    connection.execute(
                        "INSERT INTO documents (id, filename, stored_name, content_type, size_bytes, sha256, status,"
                        " uploaded_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?)",
                        (document_id, filename, stored_name, content_type, len(data), digest, user_id, now, now),
                    )
            except sqlite3.IntegrityError as exc:
                (self.documents_dir / stored_name).unlink(missing_ok=True)
                raise UploadError("This document was uploaded at the same time by another request.") from exc
            self._pending.add(document_id)
        self._event(document_id, filename, "info", f"Uploaded ({_size_label(len(data))}); queued for indexing.")
        if self.settings.inline_ingestion:
            self._process_document(document_id)
        else:
            self._queue.put(("document", document_id))
        return self.get_summary(document_id)  # type: ignore[return-value]

    # Worker.

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                kind, payload = item
                if kind == "document":
                    self._process_document(payload)
                elif kind == "all":
                    self._process_reindex_all(payload)
            except Exception:  # keep the worker alive whatever happens to one job
                logger.exception("Ingestion job crashed")
            finally:
                self._queue.task_done()

    def _build_chunks(self, row: sqlite3.Row) -> list[dict[str, str]]:
        path = self._file_path(row)
        if path is not None and path.is_file():
            prefix = path.name
            documents = [
                {
                    "source": row["filename"] + doc["source"][len(prefix) :]
                    if doc["source"].startswith(prefix)
                    else f"{row['filename']}:{doc['source']}",
                    "text": doc["text"],
                }
                for doc in load_documents(path)
            ]
            chunks = chunk_documents(documents, self.settings.chunk_size, self.settings.chunk_overlap)
        else:
            chunks = [{"source": item["source"], "text": item["text"]} for item in self.store.document_chunks(row["id"])]
            if not chunks:
                raise ValueError("The original file is not available. Upload the document again.")
        if not chunks:
            raise ValueError("No readable text was found in this document.")
        return chunks

    def _process_document(self, document_id: str) -> None:
        with self._lock:
            row = self._row(document_id)
            if row is None or document_id not in self._pending:
                self._pending.discard(document_id)
                return
            self._processing = document_id
            self._update(document_id, status="processing", error=None)
        name = row["filename"]
        self._event(document_id, name, "info", "Processing started.")
        started = time.perf_counter()
        try:
            chunks = self._build_chunks(row)
            backend, model = self._target_embedding()
            vectors = self._embed([chunk["text"] for chunk in chunks], backend)
            with self._lock:
                if self._row(document_id) is None:
                    return  # deleted while embedding
                self._commit_store(lambda: self.store.replace_document(document_id, chunks, vectors, backend, model))
                self._update(
                    document_id,
                    status="indexed",
                    chunk_count=len(chunks),
                    embedding_backend=backend,
                    indexed_at=utc_now(),
                    error=None,
                )
        except Exception as exc:
            message = _describe(exc)
            if self._row(document_id) is not None:
                # A failed reindex keeps serving the previous chunks, so record what is actually searchable.
                self._update(document_id, status="failed", error=message, chunk_count=len(self.store.document_chunks(document_id)))
            self._event(document_id, name, "error", f"Indexing failed: {message}")
        else:
            self._event(
                document_id, name, "info", f"Indexed {len(chunks)} chunks in {time.perf_counter() - started:.1f}s."
            )
        finally:
            with self._lock:
                self._pending.discard(document_id)
                self._processing = None

    def _process_reindex_all(self, document_ids: tuple[str, ...]) -> None:
        backend, model = self.configured_embedding()
        self._event(None, "index", "info", f"Full reindex started for {len(document_ids)} documents ({backend}).")
        previous: dict[str, str] = {}
        built: list[dict[str, Any]] = []
        failures: dict[str, str] = {}
        try:
            for document_id in document_ids:
                row = self._row(document_id)
                if row is None:
                    continue
                previous[document_id] = row["status"]
                self._update(document_id, status="processing")
                try:
                    built.extend({**chunk, "document_id": document_id} for chunk in self._build_chunks(row))
                except Exception as exc:
                    failures[document_id] = _describe(exc)
            vectors = self._embed([chunk["text"] for chunk in built], backend)
            with self._lock:
                self._commit_store(lambda: self.store.replace_all(built, vectors, backend, model))
        except Exception as exc:
            for document_id, status in previous.items():
                self._update(document_id, status=status)
            self._event(None, "index", "error", f"Full reindex failed; the previous index is unchanged. {_describe(exc)}")
            return
        finally:
            with self._lock:
                self._reindex_all_pending = False
                self._pending.difference_update(document_ids)

        counts: dict[str, int] = {}
        for chunk in built:
            counts[chunk["document_id"]] = counts.get(chunk["document_id"], 0) + 1
        now = utc_now()
        for document_id in previous:
            if document_id in failures:
                self._update(document_id, status="failed", chunk_count=0, error=failures[document_id])
            else:
                self._update(
                    document_id, status="indexed", chunk_count=counts.get(document_id, 0),
                    embedding_backend=backend, indexed_at=now, error=None,
                )
        summary = f"Full reindex finished: {len(previous) - len(failures)} indexed, {len(failures)} failed."
        self._event(None, "index", "warning" if failures else "info", summary)

    # Admin operations.

    def reindex(self, document_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._row(document_id)
            if row is None:
                raise DocumentError("Document not found.", 404)
            if document_id in self._pending or self._reindex_all_pending:
                raise DocumentError("This document is already queued or being processed.", 409)
            path = self._file_path(row)
            if not (path and path.is_file()) and not self.store.document_chunks(document_id):
                raise DocumentError("The original file is not available. Upload the document again.", 409)
            self._update(document_id, status="queued", error=None)
            self._pending.add(document_id)
        self._event(document_id, row["filename"], "info", "Queued for reindexing.")
        if self.settings.inline_ingestion:
            self._process_document(document_id)
        else:
            self._queue.put(("document", document_id))
        return self.get_summary(document_id)  # type: ignore[return-value]

    def reindex_all(self) -> int:
        with self._lock:
            if self._pending or self._reindex_all_pending:
                raise DocumentError("Wait for queued documents to finish before reindexing everything.", 409)
            with self.db.connect() as connection:
                ids = {row["id"] for row in connection.execute("SELECT id FROM documents").fetchall()}
            ids |= self.store.document_ids()
            if not ids:
                raise DocumentError("There are no documents to reindex.", 409)
            for document_id in ids:
                self._update(document_id, status="queued")
            self._reindex_all_pending = True
            self._pending.update(ids)
        ordered_ids = tuple(sorted(ids))
        if self.settings.inline_ingestion:
            self._process_reindex_all(ordered_ids)
        else:
            self._queue.put(("all", ordered_ids))
        return len(ids)

    def delete(self, document_id: str, actor: str) -> int:
        with self._lock:
            row = self._row(document_id)
            if row is None:
                raise DocumentError("Document not found.", 404)
            if self._processing == document_id or self._reindex_all_pending:
                raise DocumentError("This document is being processed. Try again when it finishes.", 409)
            path = self._file_path(row)
            self._purge_trash()
            self._trash[document_id] = {
                "row": dict(row),
                "chunks": self.store.document_chunks(document_id),
                "data": path.read_bytes() if path is not None and path.is_file() else None,
                "embedding": (self.store.embedding_backend, self.store.embedding_model),
                "expires": time.monotonic() + UNDO_SECONDS,
            }
            # Vectors go first: once this returns, no retrieval can surface the document.
            removed = self._commit_store(lambda: self.store.remove_document(document_id))
            with self.db.connect() as connection:
                connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            self._pending.discard(document_id)
        if path is not None:
            path.unlink(missing_ok=True)
        self._event(document_id, row["filename"], "info", f"Deleted (from {actor}); removed {removed} chunks.")
        return removed

    def _purge_trash(self) -> None:
        now = time.monotonic()
        for document_id in [key for key, entry in self._trash.items() if entry["expires"] <= now]:
            del self._trash[document_id]

    def restore(self, document_id: str, actor: str) -> dict[str, Any]:
        """Undo a recent delete: put back the database row, original file and indexed chunks."""
        with self._lock:
            self._purge_trash()
            entry = self._trash.get(document_id)
            if entry is None:
                raise DocumentError("This document can no longer be restored.", 410)
            if self._reindex_all_pending:
                raise DocumentError("Wait for the full reindex to finish before restoring.", 409)
            row = dict(entry["row"])
            with self.db.connect() as connection:
                conflict = connection.execute(
                    "SELECT filename FROM documents WHERE id = ? OR filename = ? OR (sha256 IS NOT NULL AND sha256 = ?)",
                    (document_id, row["filename"], row["sha256"]),
                ).fetchone()
            if conflict:
                raise DocumentError(f"Can't restore: \"{conflict['filename']}\" is already in the knowledge base.", 409)

            path = self._file_path(row)
            if path is not None and entry["data"] is not None:
                temporary = path.with_name(f"{path.name}.part")
                temporary.write_bytes(entry["data"])
                os.replace(temporary, path)
            chunks = entry["chunks"]
            requeue = row["status"] in {"queued", "processing"}
            if chunks and not requeue:
                try:
                    self._commit_store(
                        lambda: self.store.replace_document(
                            document_id, chunks, [chunk["vector"] for chunk in chunks], *entry["embedding"]
                        )
                    )
                except ValueError:
                    # The index moved to another embedding model since the delete; rebuild from the file.
                    requeue = path is not None and entry["data"] is not None
                    if not requeue:
                        row.update(status="failed", chunk_count=0, error="Index entries are missing. Reindex this document.")
            if requeue:
                row.update(status="queued", error=None)
            row["updated_at"] = utc_now()
            try:
                with self.db.connect() as connection:
                    connection.execute(
                        f"INSERT INTO documents ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})",
                        tuple(row.values()),
                    )
            except Exception:
                self._commit_store(lambda: self.store.remove_document(document_id))
                raise
            del self._trash[document_id]
            if requeue:
                self._pending.add(document_id)
        self._event(document_id, row["filename"], "info", f"Restored (from {actor}).")
        if requeue:
            self._queue.put(("document", document_id))
        return self.get_summary(document_id)  # type: ignore[return-value]

    # Queries.

    _SELECT = (
        "SELECT d.id, d.filename, d.content_type, d.size_bytes, d.sha256, d.status, d.error, d.chunk_count,"
        " d.embedding_backend, d.created_at, d.updated_at, d.indexed_at, d.stored_name IS NOT NULL AS has_original,"
        " u.email AS uploaded_by FROM documents d LEFT JOIN users u ON u.id = d.uploaded_by"
    )

    @staticmethod
    def _summary(row: sqlite3.Row) -> dict[str, Any]:
        return {**dict(row), "has_original": bool(row["has_original"])}

    def get_summary(self, document_id: str) -> dict[str, Any] | None:
        with self.db.connect() as connection:
            row = connection.execute(f"{self._SELECT} WHERE d.id = ?", (document_id,)).fetchone()
        return self._summary(row) if row else None

    def list(self, search: str = "", status: str = "", limit: int = 500) -> list[dict[str, Any]]:
        clauses, params = [], []
        if search.strip():
            clauses.append("d.filename LIKE ? ESCAPE '\\'")
            escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params.append(f"%{escaped}%")
        if status in STATUSES:
            clauses.append("d.status = ?")
            params.append(status)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.db.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT}{where} ORDER BY d.created_at DESC LIMIT ?",
                (*params, max(1, min(limit, 500))),
            ).fetchall()
        return [self._summary(row) for row in rows]

    def original(self, document_id: str) -> tuple[Path, str, str]:
        """Path, filename and content type of the uploaded file, for viewing or download."""
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT filename, stored_name, content_type FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
        if row is None:
            raise DocumentError("Document not found.", 404)
        path = self._file_path(row)
        if path is None or not path.is_file():
            raise DocumentError("The original file is not available for this document.", 404)
        return path, row["filename"], row["content_type"] or "application/octet-stream"

    def get(self, document_id: str) -> dict[str, Any]:
        summary = self.get_summary(document_id)
        if summary is None:
            raise DocumentError("Document not found.", 404)
        chunks = self.store.document_chunks(document_id)
        return {
            **summary,
            "chunks": [
                {"location": describe_location(chunk["source"]), "text": chunk["text"][:400]} for chunk in chunks[:25]
            ],
            "events": self.events(limit=50, document_id=document_id),
        }

    def events(self, limit: int = 100, document_id: str | None = None, level: str = "") -> list[dict[str, Any]]:
        clauses, params = [], []
        if document_id:
            clauses.append("document_id = ?")
            params.append(document_id)
        if level in {"info", "warning", "error"}:
            clauses.append("level = ?")
            params.append(level)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.db.connect() as connection:
            rows = connection.execute(
                f"SELECT id, document_id, document_name, level, message, created_at FROM ingestion_events{where}"
                " ORDER BY id DESC LIMIT ?",
                (*params, max(1, min(limit, 500))),
            ).fetchall()
        return [dict(row) for row in rows]

    def index_info(self) -> dict[str, Any]:
        backend, model = self.index_embedding()
        configured_backend, configured_model = self.configured_embedding()
        return {
            "embedding_backend": backend if self.store.chunks else None,
            "embedding_model": model or None,
            "dimension": self.store.dimension if self.store.chunks else None,
            "configured_backend": configured_backend,
            "configured_model": configured_model or None,
            "needs_reindex": self.needs_reindex(),
            "chunk_size": self.settings.chunk_size,
            "chunk_overlap": self.settings.chunk_overlap,
            "chunks": len(self.store.chunks),
        }

    def overview(self) -> dict[str, Any]:
        with self.db.connect() as connection:
            counts = {
                row["status"]: row["total"]
                for row in connection.execute("SELECT status, COUNT(*) AS total FROM documents GROUP BY status")
            }
            file_types = {
                Path(row["filename"]).suffix.lower()
                for row in connection.execute("SELECT filename FROM documents WHERE status = 'indexed'")
                if Path(row["filename"]).suffix
            }
            last = connection.execute("SELECT MAX(created_at) FROM ingestion_events").fetchone()[0]
        return {
            "documents": {
                "total": sum(counts.values()),
                "indexed": counts.get("indexed", 0),
                "processing": counts.get("queued", 0) + counts.get("processing", 0),
                "failed": counts.get("failed", 0),
            },
            "chunks": len(self.store.chunks),
            "file_types": len(file_types),
            "last_activity": last,
            "worker": {"alive": self.worker_alive, "queued_jobs": self._queue.qsize(), "reindexing_all": self._reindex_all_pending},
            "index": self.index_info(),
        }

    def document_names(self, limit: int = 3) -> list[str]:
        with self.db.connect() as connection:
            rows = connection.execute(
                "SELECT filename FROM documents WHERE status = 'indexed' ORDER BY indexed_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [row["filename"] for row in rows]
