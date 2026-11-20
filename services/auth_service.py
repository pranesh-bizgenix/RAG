"""Credential authentication and opaque server-side login sessions."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from typing import Any

from core.database import Database, utc_now
from services.document_service import DocumentError
from services.employee_service import EmployeeService, verify_password

SESSION_COOKIE = "rag_session"
SESSION_HOURS = 12


class AuthService:
    def __init__(self, db: Database, employees: EmployeeService) -> None:
        self.db = db
        self.employees = employees

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("ascii")).hexdigest()

    @staticmethod
    def token_from_cookie(header: str) -> str:
        cookie = SimpleCookie()
        try:
            cookie.load(header or "")
        except Exception:
            return ""
        return cookie.get(SESSION_COOKIE).value if cookie.get(SESSION_COOKIE) else ""

    def has_admin(self) -> bool:
        with self.db.connect() as connection:
            return connection.execute("SELECT 1 FROM employees WHERE role = 'admin' LIMIT 1").fetchone() is not None

    def setup_admin(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.has_admin():
            raise DocumentError("Administrator setup has already been completed.", 409)
        with self.db.connect() as connection:
            department = connection.execute("SELECT id FROM departments WHERE name = 'Admin'").fetchone()
        if department is None:
            department_id = self.employees.create_department("Admin")["id"]
        else:
            department_id = department["id"]
        email = str(payload.get("email", "")).strip().lower()
        name = email.split("@", 1)[0].replace(".", " ").replace("_", " ").strip().title() or "Administrator"
        with self.db.connect() as connection:
            used_ids = {
                row["employee_id"].casefold()
                for row in connection.execute("SELECT employee_id FROM employees WHERE employee_id LIKE 'ADMIN-%'")
            }
        number = 1
        while f"admin-{number:03d}" in used_ids:
            number += 1
        return self.employees.create(
            {
                "employee_id": f"ADMIN-{number:03d}",
                "name": name,
                "email": email,
                "password": payload.get("password", ""),
                "department_id": department_id,
                "role": "admin",
            }
        )

    def login(self, email: str, password: str) -> tuple[str, dict[str, Any]]:
        email = str(email).strip().lower()
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT e.id, e.employee_id, e.name, e.email, e.password_hash, e.role, e.status,"
                " e.department_id, d.name AS department_name FROM employees e"
                " JOIN departments d ON d.id = e.department_id"
                " WHERE e.email = ? COLLATE NOCASE",
                (email,),
            ).fetchone()
        if row is None or row["status"] != "active" or not verify_password(str(password), row["password_hash"]):
            raise DocumentError("Invalid credentials or suspended account.", 401)
        token = secrets.token_urlsafe(32)
        expires = (datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)).isoformat(timespec="seconds")
        with self.db.connect() as connection:
            connection.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (utc_now(),))
            connection.execute(
                "INSERT INTO auth_sessions (token_hash, employee, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (self._hash(token), row["id"], utc_now(), expires),
            )
        user = {key: row[key] for key in row.keys() if key != "password_hash"}
        return token, user

    def current(self, cookie_header: str) -> dict[str, Any] | None:
        token = self.token_from_cookie(cookie_header)
        if not token:
            return None
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT e.id, e.employee_id, e.name, e.email, e.role, e.status, e.department_id,"
                " d.name AS department_name FROM auth_sessions s JOIN employees e ON e.id = s.employee"
                " JOIN departments d ON d.id = e.department_id"
                " WHERE s.token_hash = ? AND s.expires_at > ?",
                (self._hash(token), utc_now()),
            ).fetchone()
        return dict(row) if row is not None and row["status"] == "active" else None

    def logout(self, cookie_header: str) -> None:
        token = self.token_from_cookie(cookie_header)
        if token:
            with self.db.connect() as connection:
                connection.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (self._hash(token),))
