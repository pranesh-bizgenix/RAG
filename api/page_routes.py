"""HTML pages and static assets."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

from api.http import HTTPError, Request, Response, Router
from core.config import PROJECT_ROOT

if TYPE_CHECKING:
    from api.application import Application

WEB_DIR = PROJECT_ROOT / "public"
STATIC_DIR = (WEB_DIR / "static").resolve()
CONTENT_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


def _page(name: str) -> Response:
    return Response(body=(WEB_DIR / name).read_bytes(), content_type="text/html; charset=utf-8")


def _redirect(location: str) -> Response:
    return Response(body=b"", status=HTTPStatus.FOUND, headers={"Location": location})


def register(router: Router, app: "Application") -> None:
    @router.add("GET", "/")
    def chat_page(request: Request) -> Response:
        return _page("index.html")

    @router.add("GET", "/admin")
    def admin_page(request: Request) -> Response:
        return _page("admin.html")

    @router.add("GET", "/login")
    def login_page(request: Request) -> Response:
        # Old bookmarks: there is no sign-in any more.
        return _redirect("/")

    @router.add("GET", r"/static/(?P<asset>[A-Za-z0-9_\-./]+)", raw=True)
    def static_asset(request: Request) -> Response:
        path = (STATIC_DIR / request.params["asset"]).resolve()
        if not path.is_relative_to(STATIC_DIR) or not path.is_file() or path.suffix not in CONTENT_TYPES:
            raise HTTPError(HTTPStatus.NOT_FOUND, "Not found.")
        return Response(
            body=path.read_bytes(), content_type=CONTENT_TYPES[path.suffix], headers={"Cache-Control": "no-cache"}
        )

    @router.add("GET", "/favicon.ico")
    def favicon(request: Request) -> Response:
        return _redirect("/static/img/favicon.png")
