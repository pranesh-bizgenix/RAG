"""Wires services together and dispatches every HTTP request through one guarded path."""

from __future__ import annotations

import hmac
import logging
import secrets
import threading
import time
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from api import admin_routes, auth_routes, chat_routes, page_routes
from api.http import (
    UNSAFE_METHODS,
    EventStream,
    HTTPError,
    Request,
    Response,
    Route,
    Router,
    parse_target,
    write_response,
)
from core.config import Settings
from core.database import Database
from core.llm_configuration import load_configuration
from core.logging_setup import log_fields
from rag.embedder import APIEmbeddingClient
from rag.llm import LLMClient, create_llm_client
from rag.query import RAGChatbot
from services.conversation_service import ConversationService
from services.document_service import DocumentError, DocumentService
from services.employee_service import EmployeeService
from services.auth_service import AuthService
from services.workspace import ensure_workspace
from vectorstore import LocalVectorStore

logger = logging.getLogger("app")
access_logger = logging.getLogger("access")
_DEFAULT = object()


class RateLimiter:
    """Sliding-window limit per key (for example, chat messages per client IP per minute)."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit, self.window = limit, window_seconds
        self._hits: dict[object, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: object) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True


class Application:
    def __init__(
        self,
        settings: Settings,
        *,
        llm: LLMClient | None | object = _DEFAULT,
        embedding_client: APIEmbeddingClient | None = None,
    ) -> None:
        self.settings = settings
        self.db = Database(settings.db_path)
        self.store = LocalVectorStore(settings.store_path)
        self.embedding_client = embedding_client or APIEmbeddingClient()
        # No accounts: everyone shares one workspace. The CSRF token stops other websites from
        # sending commands through a visitor's browser.
        self.workspace_id = ensure_workspace(self.db)
        # Serverless platforms can route consecutive browser requests to
        # different instances. A configured token keeps CSRF validation stable
        # across those instances; local runs still receive a random token.
        self.csrf_token = settings.csrf_token or secrets.token_urlsafe(32)
        self.conversations = ConversationService(self.db)
        self.employees = EmployeeService(self.db)
        self.auth = AuthService(self.db, self.employees)
        self.documents = DocumentService(self.db, self.store, settings, self.embedding_client)
        self.chatbot = RAGChatbot(
            store=self.store,
            top_k=settings.top_k,
            llm=create_llm_client(load_configuration(settings.llm_config_path)) if llm is _DEFAULT else llm,
            embedding_client=self.embedding_client,
            min_vector_score=settings.min_vector_score,
        )
        self.generation_slots = threading.BoundedSemaphore(settings.max_concurrent_generations)
        self.chat_limiter = RateLimiter(settings.chat_messages_per_minute, 60)
        self.started_at = time.time()
        self.router = Router()
        for module in (auth_routes, chat_routes, admin_routes, page_routes):
            module.register(self.router, self)

    # Lifecycle.

    def start(self) -> None:
        if bool(self.settings.initial_admin_email) != bool(self.settings.initial_admin_password):
            raise RuntimeError("INITIAL_ADMIN_EMAIL and INITIAL_ADMIN_PASSWORD must be configured together.")
        if self.settings.initial_admin_email and not self.auth.has_admin():
            self.auth.setup_admin(
                {
                    "email": self.settings.initial_admin_email,
                    "password": self.settings.initial_admin_password,
                }
            )
        self.documents.start()

    def stop(self) -> None:
        self.documents.stop()

    def make_server(self, host: str | None = None, port: int | None = None) -> ThreadingHTTPServer:
        app = self

        class AppHandler(BaseHTTPRequestHandler):
            server_version = "KnowledgeAssistant"
            sys_version = ""
            timeout = 120  # drop clients that stall mid-request

            def do_GET(self) -> None:  # noqa: N802
                app.dispatch(self)

            do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_GET

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                return

        class Server(ThreadingHTTPServer):
            daemon_threads = True
            request_queue_size = 64

        return Server((host or self.settings.host, self.settings.port if port is None else port), AppHandler)

    # Request handling.

    def event_stream(self, request: Request) -> EventStream:
        return EventStream(request.handler)

    def client_ip(self, handler: BaseHTTPRequestHandler) -> str:
        if self.settings.trust_proxy and (forwarded := handler.headers.get("X-Forwarded-For", "")):
            return forwarded.split(",")[0].strip()
        return handler.client_address[0]

    def _check_origin(self, request: Request) -> None:
        origin = request.header("Origin")
        if origin:
            host = request.header("X-Forwarded-Host") if self.settings.trust_proxy else ""
            host = host or request.header("Host")
            if urlparse(origin).netloc != host:
                raise HTTPError(HTTPStatus.FORBIDDEN, "Cross-origin request blocked.")
        elif request.header("Sec-Fetch-Site") == "cross-site":
            raise HTTPError(HTTPStatus.FORBIDDEN, "Cross-origin request blocked.")

    def _check_request(self, route: Route, request: Request) -> None:
        if request.method in UNSAFE_METHODS:
            self._check_origin(request)
            sent = request.header("X-CSRF-Token")
            if route.csrf and (not sent or not hmac.compare_digest(sent, self.csrf_token)):
                raise HTTPError(HTTPStatus.FORBIDDEN, "The page is out of date. Refresh it and try again.")

    def _authorize(self, request: Request) -> Response | None:
        request.user = self.auth.current(request.header("Cookie"))
        public = (
            request.path == "/login"
            or request.path == "/favicon.ico"
            or request.path == "/api/health"
            or request.path.startswith("/static/")
            or request.path.startswith("/api/auth/")
        )
        if public:
            return None
        if request.user is None:
            if request.method == "GET" and request.path in {"/", "/admin"}:
                return Response(body=b"", status=HTTPStatus.FOUND, headers={"Location": "/login"})
            raise HTTPError(HTTPStatus.UNAUTHORIZED, "Sign in to continue.")
        if (request.path == "/admin" or request.path.startswith("/api/admin/")) and request.user["role"] != "admin":
            if request.method == "GET" and request.path == "/admin":
                return Response(body=b"", status=HTTPStatus.FOUND, headers={"Location": "/"})
            raise HTTPError(HTTPStatus.FORBIDDEN, "Administrator access is required.")
        return None

    def dispatch(self, handler: BaseHTTPRequestHandler) -> None:
        started = time.perf_counter()
        path, query = parse_target(handler.path)
        request = Request(handler, handler.command, path, query, {}, self.client_ip(handler))
        status = 500
        try:
            try:
                authorization = self._authorize(request)
                if authorization is not None:
                    response = authorization
                    status = response.status
                    write_response(handler, response)
                    return
                route, request.params = self.router.match(request.method, path)
                self._check_request(route, request)
                result = route.handler(request)
                if result is None:  # the route streamed its own response
                    status = 200
                    return
                response = result if isinstance(result, Response) else Response(result)
            except HTTPError as exc:
                response = Response({"error": exc.message}, exc.status)
            except DocumentError as exc:
                response = Response({"error": str(exc)}, exc.status)
            except Exception:
                logger.exception("Unhandled error", extra=log_fields(path=path))
                response = Response({"error": "An unexpected error occurred. Please try again."}, 500)
            status = response.status
            write_response(handler, response)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        finally:
            if not path.startswith("/static/"):
                access_logger.info(
                    "%s %s %s",
                    request.method,
                    path,
                    status,
                    extra=log_fields(ms=round((time.perf_counter() - started) * 1000), ip=request.client_ip),
                )
