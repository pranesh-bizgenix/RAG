"""Knowledge-base administration endpoints."""

from __future__ import annotations

import json
import shutil
import time
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from io import BytesIO
from typing import TYPE_CHECKING
from urllib.parse import quote

from api.http import HTTPError, Request, Response, Router
from core.database import DatabaseError
from core.llm_configuration import (
    configuration_from_environment,
    public_catalog,
    validate_configuration,
)
from rag.llm import create_llm_client
from services.document_preview import office_preview
from services.document_service import UNDO_SECONDS

TEXT_EXTENSIONS = {".txt", ".md", ".json"}

if TYPE_CHECKING:
    from api.application import Application


def _multipart_upload(request: Request, limit: int) -> tuple[list[tuple[str, bytes]], dict[str, str]]:
    content_type = request.header("Content-Type")
    if not content_type.lower().startswith("multipart/form-data"):
        raise HTTPError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Upload must use multipart/form-data.")
    envelope = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + request.body(limit)
    message = BytesParser(policy=policy.default).parsebytes(envelope)
    if not message.is_multipart():
        raise HTTPError(HTTPStatus.BAD_REQUEST, "Malformed upload.")
    files = [
        (part.get_filename() or "", part.get_payload(decode=True) or b"")
        for part in message.iter_parts()
        if part.get_param("name", header="content-disposition") in {"files", "file"} and part.get_filename()
    ]
    fields = {
        str(part.get_param("name", header="content-disposition")): str(part.get_content()).strip()
        for part in message.iter_parts()
        if not part.get_filename() and part.get_param("name", header="content-disposition")
    }
    return files, fields


def register(router: Router, app: "Application") -> None:
    settings = app.settings

    def overview_payload(request: Request) -> dict:
        return {
            **app.documents.overview(),
            "recent_events": app.documents.events(limit=8),
            "recent_documents": app.documents.list(status="indexed", limit=5),
            "health": health(request),
        }

    @router.add("GET", "/api/admin/overview")
    def overview(request: Request) -> dict:
        return overview_payload(request)

    @router.add("GET", "/api/admin/bootstrap")
    def bootstrap(request: Request) -> dict:
        return {"csrf_token": app.csrf_token, "user": request.user, **overview_payload(request)}

    @router.add("GET", "/api/admin/health")
    def health(request: Request) -> dict:
        llm = app.chatbot.llm
        storage_ok = settings.store_path.parent.exists() and settings.documents_dir.exists()
        checks = [
            {"name": "Database", "ok": app.db.ping(), "detail": f"Schema version {app.db.schema_version}"},
            {
                "name": "Ingestion",
                "ok": app.documents.worker_alive,
                "detail": (
                    "Inline per request (serverless)"
                    if settings.inline_ingestion
                    else "Running"
                    if app.documents.worker_alive
                    else "Stopped"
                ),
            },
            {"name": "Storage", "ok": storage_ok, "detail": "Vector index and document storage available" if storage_ok else "Storage directory missing"},
            *(
                [
                    {
                        "name": "Database persistence",
                        "ok": bool(settings.turso_database_url),
                        "detail": (
                            "Turso stores employees, departments, sessions, permissions, and history durably"
                            if settings.turso_database_url
                            else "Vercel temporary database; accounts and history are not durable"
                        ),
                    },
                    {
                        "name": "File persistence",
                        "ok": False,
                        "detail": "Uploaded originals and runtime vector-index changes remain temporary on Vercel",
                    }
                ]
                if settings.inline_ingestion
                else []
            ),
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
        return {
            "documents": app.documents.list(
                request.query.get("q", ""), request.query.get("status", ""), request.query.get("department", "")
            )
        }

    @router.add("GET", "/api/admin/departments")
    def list_departments(request: Request) -> dict:
        return {"departments": app.employees.departments()}

    @router.add("POST", "/api/admin/departments")
    def create_department(request: Request) -> Response:
        return Response(app.employees.create_department(str(request.json().get("name", ""))), 201)

    @router.add("DELETE", "/api/admin/departments/<department_id>")
    def delete_department(request: Request) -> dict:
        app.employees.delete_department(request.params["department_id"])
        return {"ok": True}

    @router.add("GET", "/api/admin/employees")
    def list_employees(request: Request) -> dict:
        return {
            "employees": app.employees.list(
                request.query.get("q", ""), request.query.get("status", ""), request.query.get("department", "")
            )
        }

    @router.add("POST", "/api/admin/employees")
    def create_employee(request: Request) -> Response:
        return Response(app.employees.create(request.json()), 201)

    @router.add("PATCH", "/api/admin/employees/<employee>")
    def update_employee(request: Request) -> dict:
        employee_id = int(request.params["employee"])
        payload = request.json()
        current = app.employees.get(employee_id)
        next_role = str(payload.get("role", current["role"])).strip().lower()
        next_status = str(payload.get("status", current["status"])).strip().lower()
        removing_admin_access = current["role"] == "admin" and (
            next_role != "admin" or next_status != "active"
        )
        if request.user and employee_id == request.user["id"] and removing_admin_access:
            raise HTTPError(HTTPStatus.CONFLICT, "You cannot suspend or remove administrator access from your own account.")
        if removing_admin_access and app.employees.active_admin_count() <= 1:
            raise HTTPError(HTTPStatus.CONFLICT, "At least one active administrator account is required.")
        return app.employees.update(employee_id, payload)

    @router.add("DELETE", "/api/admin/employees/<employee>")
    def delete_employee(request: Request) -> dict:
        employee_id = int(request.params["employee"])
        current = app.employees.get(employee_id)
        if request.user and employee_id == request.user["id"]:
            raise HTTPError(HTTPStatus.CONFLICT, "You cannot delete the account you are currently using.")
        if current["role"] == "admin" and current["status"] == "active" and app.employees.active_admin_count() <= 1:
            raise HTTPError(HTTPStatus.CONFLICT, "At least one active administrator account is required.")
        app.employees.delete(employee_id)
        return {"ok": True}

    @router.add("POST", "/api/admin/documents")
    def upload_documents(request: Request) -> Response:
        limit = settings.max_upload_bytes * settings.max_files_per_upload + 1024 * 1024
        files, fields = _multipart_upload(request, limit)
        try:
            employees = json.loads(fields.get("employees", "[]"))
        except json.JSONDecodeError as exc:
            raise HTTPError(HTTPStatus.BAD_REQUEST, "Employee access must be a valid list.") from exc
        results = app.documents.upload(files, None, fields.get("department", "all"), employees)
        return Response({"results": results}, 202 if any(item["ok"] for item in results) else 400)

    @router.add("GET", "/api/admin/documents/<document_id>")
    def get_document(request: Request) -> dict:
        return app.documents.get(request.params["document_id"])

    @router.add("PATCH", "/api/admin/documents/<document_id>/access")
    def update_document_access(request: Request) -> dict:
        payload = request.json()
        employees = payload.get("employees", [])
        if not isinstance(employees, list):
            raise HTTPError(HTTPStatus.BAD_REQUEST, "Employee access must be a list of names.")
        return app.documents.update_access(
            request.params["document_id"], str(payload.get("department", "all")), employees
        )

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
        return {"ok": True, "removed_chunks": removed, "undo_seconds": UNDO_SECONDS}

    @router.add("POST", "/api/admin/documents/<document_id>/restore")
    def restore_document(request: Request) -> dict:
        return app.documents.restore(request.params["document_id"], request.client_ip)

    @router.add("POST", "/api/admin/documents/<document_id>/reindex")
    def reindex_document(request: Request) -> Response:
        return Response(app.documents.reindex(request.params["document_id"]), 202)

    @router.add("POST", "/api/admin/reindex")
    def reindex_all(request: Request) -> Response:
        return Response({"queued": app.documents.reindex_all()}, 202)

    @router.add("GET", "/api/admin/knowledge-base")
    def knowledge_base(request: Request) -> dict:
        app.reload_llm_configuration()
        llm = app.chatbot.llm
        return {
            "index": app.documents.index_info(),
            "departments": app.employees.departments(),
            "retrieval": {"top_k": settings.top_k, "min_vector_score": settings.min_vector_score},
            "llm": {"provider": llm.provider, "model": llm.model} if llm else None,
            "limits": {"max_upload_mb": settings.max_upload_mb, "max_files_per_upload": settings.max_files_per_upload},
        }

    @router.add("GET", "/api/admin/llm")
    def llm_configuration(request: Request) -> dict:
        app.reload_llm_configuration()
        return llm_configuration_payload()

    def llm_configuration_payload() -> dict:
        saved = app.llm_configuration.load()
        llm = app.chatbot.llm
        service = (saved or {}).get("service") or getattr(llm, "service", "")
        model = (saved or {}).get("model") or getattr(llm, "model", "")
        base_url = (saved or {}).get("base_url", "")
        enabled = bool(saved["enabled"]) if saved else llm is not None
        return {
            "catalog": public_catalog(),
            "configuration": {
                "enabled": enabled,
                "configured": bool(saved or llm),
                "service": service,
                "model": model,
                "base_url": base_url,
                "has_api_key": bool(saved and saved.get("api_key")) or bool(getattr(llm, "api_key", "")),
                "source": str(saved.get("source", "admin")) if saved else "environment" if llm else "none",
            },
        }

    @router.add("PUT", "/api/admin/llm")
    def update_llm_configuration(request: Request) -> dict:
        try:
            payload = request.json()
            if not str(payload.get("api_key", "")).strip():
                saved = app.llm_configuration.load() or {}
                current_service = saved.get("service") or getattr(app.chatbot.llm, "service", "")
                if current_service == str(payload.get("service", "")).strip().lower():
                    payload["api_key"] = saved.get("api_key") or getattr(app.chatbot.llm, "api_key", "")
            configuration = validate_configuration(payload)
            if configuration is None:
                raise ValueError("Choose a supported LLM provider.")
            create_llm_client(configuration)  # Validate that a client can be constructed before saving.
            app.llm_configuration.save(configuration, enabled=True, source="admin")
            app.manage_llm_configuration()
        except ValueError as exc:
            raise HTTPError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
        except DatabaseError as exc:
            raise HTTPError(HTTPStatus.INTERNAL_SERVER_ERROR, "The LLM settings could not be saved.") from exc
        return {"ok": True, **llm_configuration_payload()}

    @router.add("PUT", "/api/admin/llm/enabled")
    def set_llm_enabled(request: Request) -> dict:
        payload = request.json()
        enabled = payload.get("enabled")
        if not isinstance(enabled, bool):
            raise HTTPError(HTTPStatus.BAD_REQUEST, "The enabled value must be true or false.")
        try:
            saved = app.llm_configuration.load()
            if saved is None:
                environment = configuration_from_environment()
                if environment is None:
                    raise ValueError("Save a provider, model, and API key before turning the language model on.")
                app.llm_configuration.save(environment, enabled=enabled, source="environment")
            else:
                app.llm_configuration.set_enabled(enabled)
            app.manage_llm_configuration()
        except ValueError as exc:
            raise HTTPError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
        except DatabaseError as exc:
            raise HTTPError(HTTPStatus.INTERNAL_SERVER_ERROR, "The language model state could not be changed.") from exc
        return {"ok": True, **llm_configuration_payload()}

    @router.add("GET", "/api/admin/events")
    def events(request: Request) -> dict:
        try:
            limit = int(request.query.get("limit", "200"))
        except ValueError:
            limit = 200
        return {"events": app.documents.events(limit=limit, level=request.query.get("level", ""))}
