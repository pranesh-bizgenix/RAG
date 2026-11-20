"""Login, logout, and one-time administrator setup endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from api.http import Request, Response, Router
from services.auth_service import SESSION_COOKIE, SESSION_HOURS

if TYPE_CHECKING:
    from api.application import Application


def register(router: Router, app: "Application") -> None:
    def cookie(token: str, max_age: int) -> str:
        value = f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}"
        return f"{value}; Secure" if app.settings.is_production else value

    @router.add("GET", "/api/auth/status", csrf=False)
    def status(request: Request) -> dict:
        return {"setup_required": not app.auth.has_admin(), "user": request.user}

    @router.add("POST", "/api/auth/login", csrf=False)
    def login(request: Request) -> Response:
        payload = request.json()
        token, user = app.auth.login(str(payload.get("email", "")), str(payload.get("password", "")))
        return Response(
            {"ok": True, "user": user},
            headers={"Set-Cookie": cookie(token, SESSION_HOURS * 3600)},
        )

    @router.add("POST", "/api/auth/logout")
    def logout(request: Request) -> Response:
        app.auth.logout(request.header("Cookie"))
        return Response({"ok": True}, headers={"Set-Cookie": cookie("", 0)})
