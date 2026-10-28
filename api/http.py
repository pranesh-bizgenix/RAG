"""Request, response, and routing primitives for ``http.server``."""

from __future__ import annotations

import json
import re
import select
import socket
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
MAX_JSON_BYTES = 64 * 1024

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
        "form-action 'self'; frame-ancestors 'none'"
    ),
}


class HTTPError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class ClientDisconnected(Exception):
    """The browser went away (closed tab or pressed Stop) while we were streaming."""


@dataclass
class Request:
    handler: BaseHTTPRequestHandler
    method: str
    path: str
    query: dict[str, str]
    params: dict[str, str]
    client_ip: str
    _body: bytes | None = field(default=None, repr=False)

    def header(self, name: str, default: str = "") -> str:
        return self.handler.headers.get(name, default)

    def body(self, limit: int = MAX_JSON_BYTES) -> bytes:
        if self._body is not None:
            return self._body
        if self.header("Transfer-Encoding"):
            raise HTTPError(HTTPStatus.LENGTH_REQUIRED, "Chunked request bodies are not supported.")
        try:
            length = int(self.header("Content-Length", "0") or 0)
        except ValueError as exc:
            raise HTTPError(HTTPStatus.BAD_REQUEST, "Invalid Content-Length.") from exc
        if length < 0 or length > limit:
            raise HTTPError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Request body is too large.")
        self._body = self.handler.rfile.read(length) if length else b""
        return self._body

    def json(self) -> dict[str, Any]:
        if not self.header("Content-Type").lower().startswith("application/json"):
            raise HTTPError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Content-Type must be application/json.")
        try:
            payload = json.loads(self.body().decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPError(HTTPStatus.BAD_REQUEST, "Invalid JSON payload.") from exc
        if not isinstance(payload, dict):
            raise HTTPError(HTTPStatus.BAD_REQUEST, "JSON body must be an object.")
        return payload


@dataclass
class Response:
    payload: Any = None
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes | None = None
    content_type: str = "application/json; charset=utf-8"


Handler = Callable[[Request], "Response | dict | list | None"]


@dataclass(frozen=True)
class Route:
    method: str
    pattern: re.Pattern[str]
    handler: Handler
    csrf: bool


class Router:
    def __init__(self) -> None:
        self.routes: list[Route] = []

    def add(
        self, method: str, path: str, csrf: bool = True, raw: bool = False
    ) -> Callable[[Handler], Handler]:
        """Register a route; ``<name>`` segments match ``[A-Za-z0-9_-]+`` unless ``raw`` regex is given."""
        pattern = re.compile("^" + (path if raw else re.sub(r"<(\w+)>", r"(?P<\1>[A-Za-z0-9_-]+)", path)) + "$")

        def decorator(handler: Handler) -> Handler:
            self.routes.append(Route(method, pattern, handler, csrf))
            return handler

        return decorator

    def match(self, method: str, path: str) -> tuple[Route, dict[str, str]]:
        allowed = False
        for route in self.routes:
            found = route.pattern.match(path)
            if not found:
                continue
            if route.method == method or (method == "HEAD" and route.method == "GET"):
                return route, found.groupdict()
            allowed = True
        if allowed:
            raise HTTPError(HTTPStatus.METHOD_NOT_ALLOWED, "Method not allowed.")
        raise HTTPError(HTTPStatus.NOT_FOUND, "Not found.")


def parse_target(raw_path: str) -> tuple[str, dict[str, str]]:
    parsed = urlparse(raw_path)
    query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
    return parsed.path or "/", query


def write_response(handler: BaseHTTPRequestHandler, response: Response) -> None:
    body = response.body
    if body is None:
        body = json.dumps(response.payload, ensure_ascii=True, default=str).encode("utf-8")
    handler.send_response(response.status)
    headers = {**SECURITY_HEADERS, "Content-Type": response.content_type, **response.headers}
    headers.setdefault("Cache-Control", "no-store")
    for name, value in headers.items():
        handler.send_header(name, value)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    if handler.command != "HEAD":
        handler.wfile.write(body)


class EventStream:
    """Server-sent events over a plain HTTP/1.0 response (connection closes when done)."""

    def __init__(self, handler: BaseHTTPRequestHandler) -> None:
        self.handler = handler
        handler.send_response(200)
        for name, value in SECURITY_HEADERS.items():
            handler.send_header(name, value)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("X-Accel-Buffering", "no")  # disable proxy buffering (nginx)
        handler.end_headers()
        handler.close_connection = True

    def client_gone(self) -> bool:
        """Detect a closed connection before writing; a write into a dead socket can appear to succeed."""
        connection = self.handler.connection
        try:
            readable, _, _ = select.select([connection], [], [], 0)
            return bool(readable) and connection.recv(1, socket.MSG_PEEK) == b""
        except (OSError, ValueError):
            return True

    def send(self, event: str, data: dict[str, Any]) -> None:
        if self.client_gone():
            raise ClientDisconnected
        message = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=True)}\n\n".encode("utf-8")
        try:
            self.handler.wfile.write(message)
            self.handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError, OSError) as exc:
            raise ClientDisconnected from exc
