"""Knowledge-base administration endpoints."""

from __future__ import annotations

import shutil
import time
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from io import BytesIO
from typing import TYPE_CHECKING
from urllib.parse import quote

from api.http import HTTPError, Request, Response, Router
from services.document_preview import office_preview

TEXT_EXTENSIONS = {".txt", ".md", ".json"}

if TYPE_CHECKING:
    from api.application import Application


def _multipart_files(request: Request, limit: int) -> list[tuple[str, bytes]]:
    content_type = request.header("Content-Type")
    if not content_type.lower().startswith("multipart/form-data"):
        raise HTTPError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Upload must use multipart/form-data.")
    envelope = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + request.body(limit)
    message = BytesParser(policy=policy.default).parsebytes(envelope)
    if not message.is_multipart():
        raise HTTPError(HTTPStatus.BAD_REQUEST, "Malformed upload.")
    return [
        (part.get_filename() or "", part.get_payload(decode=True) or b"")
        for part in message.iter_parts()
        if part.get_param("name", header="content-disposition") in {"files", "file"} and part.get_filename()
    ]


def register(router: Router, app: "Application") -> None:
    settings = app.settings

    @router.add("GET", "/api/admin/overview")
    def overview(request: Request) -> dict:
        return {**app.documents.overview(), "recent_events": app.documents.events(limit=8)}

    @router.add("GET", "/api/admin/health")
    def health(request: Request) -> dict:
        llm = app.chatbot.llm
        storage_ok = settings.store_path.parent.exists() and settings.documents_dir.exists()
        checks = [
            {"name": "Database", "ok": app.db.ping(), "detail": f"Schema version {app.db.schema_version}"},
            {"name": "Ingestion worker", "ok": app.documents.worker_alive, "detail": "Running" if app.documents.worker_alive else "Stopped"},
            {"name": "Storage", "ok": storage_ok, "detail": "Vector index and document storage available" if storage_ok else "Storage directory missing"},
            {
                "name": "Language model",
                "ok": llm is not None and app.chatbot.last_llm_error is None,
                "detail": (
                    "Not configured (retrieval-only answers)"
                    if llm is None
                    else f"{llm.provider} · {llm.model} · last request failed: {app.chatbot.last_llm_error[1]}"
                    if app.chatbot.last_llm_error
                    else f"{llm.provider} · {llm.model}"
                ),
            },
            {
                "name": "Embeddings",
                "ok": not app.documents.needs_reindex(),
                "detail": "Reindex required after configuration change" if app.documents.needs_reindex() else "Index matches configuration",
            },
            {
                "name": "OCR (images)",
                "ok": shutil.which("tesseract") is not None,
                "detail": "Tesseract available" if shutil.which("tesseract") else "Tesseract not on PATH; image uploads will fail",
            },
        ]
        return {"checks": checks, "uptime_seconds": int(time.time() - app.started_at), "environment": settings.env}

    @router.add("GET", "/api/admin/documents")
    def list_documents(request: Request) -> dict:
        return {"documents": app.documents.list(request.query.get("q", ""), request.query.get("status", ""))}

    @router.add("POST", "/api/admin/documents")
    def upload_documents(request: Request) -> Response:
        limit = settings.max_upload_bytes * settings.max_files_per_upload + 1024 * 1024
        files = _multipart_files(request, limit)
        results = app.documents.upload(files, None)
        return Response({"results": results}, 202 if any(item["ok"] for item in results) else 400)

    @router.add("GET", "/api/admin/documents/<document_id>")
    def get_document(request: Request) -> dict:
        return app.documents.get(request.params["document_id"])

    @router.add("GET", "/api/admin/documents/<document_id>/file")
    def document_file(request: Request) -> Response:
        path, filename, content_type = app.documents.original(request.params["document_id"])
        body = path.read_bytes()
        extension = path.suffix.lower()
        if request.query.get("download") == "1":
            disposition = "attachment"
        else:
            disposition = "inline"
            if extension in TEXT_EXTENSIONS:
                # Never let an uploaded file render as HTML/script in the admin origin.
                content_type = "text/plain; charset=utf-8"
            elif extension in {".tif", ".tiff"}:
                # Browsers can't display TIFF, so convert the first page to PNG for viewing.
                from PIL import Image

                with Image.open(BytesIO(body)) as image:
                    buffer = BytesIO()
                    image.convert("RGB").save(buffer, "PNG")
                body, content_type = buffer.getvalue(), "image/png"
        return Response(
            body=body,
            content_type=content_type,
            headers={
                "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(filename)}",
                # Allow the admin page to frame this file, but nothing in it may run scripts.
                "X-Frame-Options": "SAMEORIGIN",
                "Content-Security-Policy": (
                    "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; "
                    "object-src 'self'; frame-ancestors 'self'"
                ),
                "Cache-Control": "private, no-store",
            },
        )

    @router.add("GET", "/api/admin/documents/<document_id>/preview")
    def document_preview(request: Request) -> dict:
        path, filename, _ = app.documents.original(request.params["document_id"])
        try:
            preview = office_preview(path)
        except Exception as exc:  # A corrupt file shouldn't break the viewer; it can still be downloaded.
            raise HTTPError(HTTPStatus.UNPROCESSABLE_ENTITY, f"Couldn't build a preview: {exc}") from exc
        if preview is None:
            raise HTTPError(HTTPStatus.NOT_FOUND, "No structured preview for this file type.")
        return {"filename": filename, **preview}

    @router.add("DELETE", "/api/admin/documents/<document_id>")
    def delete_document(request: Request) -> dict:
        removed = app.documents.delete(request.params["document_id"], request.client_ip)
        return {"ok": True, "removed_chunks": removed}

    @router.add("POST", "/api/admin/documents/<document_id>/reindex")
    def reindex_document(request: Request) -> Response:
        return Response(app.documents.reindex(request.params["document_id"]), 202)

    @router.add("POST", "/api/admin/reindex")
    def reindex_all(request: Request) -> Response:
        return Response({"queued": app.documents.reindex_all()}, 202)

    @router.add("GET", "/api/admin/knowledge-base")
    def knowledge_base(request: Request) -> dict:
        llm = app.chatbot.llm
        return {
            "index": app.documents.index_info(),
            "retrieval": {"top_k": settings.top_k, "min_vector_score": settings.min_vector_score},
            "llm": {"provider": llm.provider, "model": llm.model} if llm else None,
            "limits": {"max_upload_mb": settings.max_upload_mb, "max_files_per_upload": settings.max_files_per_upload},
        }

    @router.add("GET", "/api/admin/events")
    def events(request: Request) -> dict:
        try:
            limit = int(request.query.get("limit", "200"))
        except ValueError:
            limit = 200
        return {"events": app.documents.events(limit=limit, level=request.query.get("level", ""))}
