"""Customer chat: conversations and streamed, grounded answers."""

from __future__ import annotations

import logging
from contextlib import closing
from pathlib import Path
from http import HTTPStatus
from typing import TYPE_CHECKING

from api.http import ClientDisconnected, HTTPError, Request, Response, Router
from core.logging_setup import log_fields

if TYPE_CHECKING:
    from api.application import Application

logger = logging.getLogger(__name__)

MAX_MESSAGE_CHARS = 4000
UNAVAILABLE = "The assistant is temporarily unavailable. Please try again in a moment."


def _suggestions(app: "Application") -> dict:
    """Build the welcome prompts once for both bootstrap and the legacy endpoint."""
    names = [
        " ".join(Path(name).stem.replace("_", " ").replace("-", " ").split())
        for name in app.documents.document_names(3)
    ]
    prompts: list[dict[str, str]] = []
    if names:
        prompts.append({"category": "Summary", "text": f"Summarize {names[0]}"})
        prompts.append({"category": "Key facts", "text": f"What are the key facts and figures in {names[0]}?"})
        if len(names) > 1:
            prompts.append({"category": "Compare", "text": f"Compare {names[0]} and {names[1]}"})
        else:
            prompts.append({"category": "Details", "text": f"List the important dates, names, and amounts in {names[0]}"})
        prompts.append({"category": "Overview", "text": "What topics does the knowledge base cover?"})
    return {"suggestions": prompts, "has_documents": bool(names)}


def register(router: Router, app: "Application") -> None:
    def owned(request: Request) -> str:
        conversation_id = request.params["conversation_id"]
        if not app.conversations.owns(app.workspace_id, conversation_id):
            raise HTTPError(HTTPStatus.NOT_FOUND, "Conversation not found.")
        return conversation_id

    @router.add("GET", "/api/health")
    def health(request: Request) -> Response:
        healthy = app.db.ping() and app.documents.worker_alive
        return Response({"status": "ok" if healthy else "degraded"}, 200 if healthy else 503)

    @router.add("GET", "/api/session")
    def session(request: Request) -> dict:
        return {"csrf_token": app.csrf_token}

    @router.add("GET", "/api/bootstrap")
    def bootstrap(request: Request) -> dict:
        """Load all initial chat state in one instance-consistent request."""
        return {
            "csrf_token": app.csrf_token,
            "conversations": app.conversations.list(app.workspace_id),
            **_suggestions(app),
        }

    @router.add("GET", "/api/suggestions")
    def suggestions(request: Request) -> dict:
        return _suggestions(app)

    @router.add("GET", "/api/conversations")
    def list_conversations(request: Request) -> dict:
        return {"conversations": app.conversations.list(app.workspace_id)}

    @router.add("POST", "/api/conversations")
    def create_conversation(request: Request) -> Response:
        return Response(app.conversations.create(app.workspace_id), 201)

    @router.add("DELETE", "/api/conversations")
    def delete_all_conversations(request: Request) -> dict:
        return {"ok": True, "deleted": app.conversations.delete_all(app.workspace_id)}

    @router.add("GET", "/api/conversations/<conversation_id>")
    def get_conversation(request: Request) -> dict:
        conversation = app.conversations.get(app.workspace_id, request.params["conversation_id"])
        if conversation is None:
            raise HTTPError(HTTPStatus.NOT_FOUND, "Conversation not found.")
        return conversation

    @router.add("PATCH", "/api/conversations/<conversation_id>")
    def rename_conversation(request: Request) -> dict:
        conversation_id = owned(request)
        try:
            app.conversations.rename(app.workspace_id, conversation_id, str(request.json().get("title", "")))
        except ValueError as exc:
            raise HTTPError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
        return {"ok": True}

    @router.add("DELETE", "/api/conversations/<conversation_id>")
    def delete_conversation(request: Request) -> dict:
        if not app.conversations.delete(app.workspace_id, request.params["conversation_id"]):
            raise HTTPError(HTTPStatus.NOT_FOUND, "Conversation not found.")
        return {"ok": True}

    def reserve_slot(request: Request) -> None:
        """Check limits before anything is saved, so a rejected request leaves no orphan message."""
        if not app.chat_limiter.allow(request.client_ip):
            raise HTTPError(HTTPStatus.TOO_MANY_REQUESTS, "You're sending messages too quickly. Please wait a moment.")
        if not app.generation_slots.acquire(blocking=False):
            raise HTTPError(HTTPStatus.SERVICE_UNAVAILABLE, "The assistant is busy right now. Please try again shortly.")

    def generate(request: Request, conversation_id: str, query: str, user_message_id: int, title: str) -> None:
        """Stream an answer; the caller must hold a generation slot, which is released here."""
        try:
            stream = app.event_stream(request)
            history = app.conversations.history(conversation_id, user_message_id)
            parts: list[str] = []
            sources: list[dict] = []
            status = "complete"
            try:
                stream.send("start", {"user_message_id": user_message_id, "conversation": {"id": conversation_id, "title": title}})
                with closing(app.chatbot.stream_answer(query, history)) as events:
                    for event in events:
                        if event["type"] == "sources":
                            sources = event["sources"]
                            stream.send("sources", {"sources": sources})
                        elif event["text"]:
                            parts.append(event["text"])
                            stream.send("delta", {"text": event["text"]})
            except ClientDisconnected:
                status = "stopped"
            except Exception:
                logger.exception("Answer generation failed", extra=log_fields(conversation=conversation_id))
                status = "error"
                try:
                    stream.send("error", {"message": UNAVAILABLE})
                except ClientDisconnected:
                    pass

            content = "".join(parts).strip()
            if not content:
                return  # nothing worth keeping; the user can retry with regenerate
            message_id, _ = app.conversations.add_message(
                conversation_id, "assistant", content, sources, "complete" if status == "complete" else "stopped"
            )
            if status == "complete":
                try:
                    stream.send("done", {"message_id": message_id})
                except ClientDisconnected:
                    pass
        finally:
            app.generation_slots.release()

    @router.add("POST", "/api/conversations/<conversation_id>/messages")
    def send_message(request: Request) -> None:
        conversation_id = request.params["conversation_id"]
        # Vercel may send conversation creation and message submission to
        # different instances, each with its own temporary SQLite database.
        # Recreate the empty conversation locally when necessary so the query
        # can still be answered instead of failing with a misleading 404.
        app.conversations.ensure(app.workspace_id, conversation_id)
        content = str(request.json().get("content", "")).strip()
        if not content:
            raise HTTPError(HTTPStatus.BAD_REQUEST, "Message cannot be empty.")
        if len(content) > MAX_MESSAGE_CHARS:
            raise HTTPError(HTTPStatus.BAD_REQUEST, f"Messages are limited to {MAX_MESSAGE_CHARS} characters.")
        reserve_slot(request)
        try:
            message_id, title = app.conversations.add_message(conversation_id, "user", content)
        except Exception:
            app.generation_slots.release()
            raise
        generate(request, conversation_id, content, message_id, title)

    @router.add("POST", "/api/conversations/<conversation_id>/regenerate")
    def regenerate(request: Request) -> None:
        conversation_id = owned(request)
        reserve_slot(request)
        try:
            prepared = app.conversations.prepare_regenerate(conversation_id)
            if prepared is None:
                raise HTTPError(HTTPStatus.BAD_REQUEST, "There is no question to answer again.")
            conversation = app.conversations.get(app.workspace_id, conversation_id)
        except Exception:
            app.generation_slots.release()
            raise
        message_id, content = prepared
        generate(request, conversation_id, content, message_id, conversation["title"] if conversation else "")
