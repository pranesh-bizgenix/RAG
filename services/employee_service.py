"""Employee and department administration for document-access assignments."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import sqlite3
import uuid
from typing import Any

from core.database import Database, utc_now
from services.document_service import DocumentError

EMPLOYEE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PBKDF2_ITERATIONS = 310_000


def _password_hash(password: str) -> str:
    password = str(password)
    if len(password) < 8 or len(password) > 256:
        raise DocumentError("Password must be between 8 and 256 characters.")
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(actual.hex(), expected)
    except (TypeError, ValueError):
        return False


class EmployeeService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def departments(self) -> list[dict[str, Any]]:
        with self.db.connect() as connection:
            rows = connection.execute(
                "SELECT d.id, d.name, d.created_at, COUNT(e.id) AS employee_count"
                " FROM departments d LEFT JOIN employees e ON e.department_id = d.id"
                " GROUP BY d.id ORDER BY d.name COLLATE NOCASE"
            ).fetchall()
        return [dict(row) for row in rows]

    def active_admin_count(self) -> int:
        with self.db.connect() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM employees WHERE role = 'admin' AND status = 'active'"
                ).fetchone()[0]
            )

    def create_department(self, name: str) -> dict[str, Any]:
        name = " ".join(str(name).split()).strip()
        if not name or len(name) > 80:
            raise DocumentError("Department name must be between 1 and 80 characters.")
        department_id = uuid.uuid4().hex
        try:
            with self.db.connect() as connection:
                connection.execute(
                    "INSERT INTO departments (id, name, created_at) VALUES (?, ?, ?)",
                    (department_id, name, utc_now()),
                )
        except sqlite3.IntegrityError as exc:
            raise DocumentError("A department with this name already exists.", 409) from exc
        return next(item for item in self.departments() if item["id"] == department_id)

    def delete_department(self, department_id: str) -> None:
        with self.db.connect() as connection:
            row = connection.execute("SELECT name FROM departments WHERE id = ?", (department_id,)).fetchone()
            if row is None:
                raise DocumentError("Department not found.", 404)
            employees = connection.execute(
                "SELECT COUNT(*) FROM employees WHERE department_id = ?", (department_id,)
            ).fetchone()[0]
            documents = connection.execute(
                "SELECT COUNT(*) FROM documents WHERE department = ?", (department_id,)
            ).fetchone()[0]
            if employees or documents:
                raise DocumentError("Move its employees and documents before deleting this department.", 409)
            connection.execute("DELETE FROM departments WHERE id = ?", (department_id,))

    @staticmethod
    def _employee_payload(
        payload: dict[str, Any], *, require_password: bool
    ) -> tuple[str, str, str, str, str | None]:
        employee_id = str(payload.get("employee_id", "")).strip()
        name = " ".join(str(payload.get("name", "")).split()).strip()
        email = str(payload.get("email", "")).strip().lower()
        department_id = str(payload.get("department_id", "")).strip()
        password = str(payload.get("password", ""))
        if not EMPLOYEE_ID.fullmatch(employee_id):
            raise DocumentError("Employee ID must be 3-64 characters using letters, numbers, dots, dashes, or underscores.")
        if not name or len(name) > 120:
            raise DocumentError("Employee name must be between 1 and 120 characters.")
        if len(email) > 254 or not EMAIL.fullmatch(email):
            raise DocumentError("Enter a valid employee email address.")
        if require_password and not password:
            raise DocumentError("Enter a password for the employee.")
        return employee_id, name, email, department_id, password or None

    def _require_department(self, connection: sqlite3.Connection, department_id: str) -> str:
        row = connection.execute("SELECT name FROM departments WHERE id = ?", (department_id,)).fetchone()
        if not row:
            raise DocumentError("Choose a valid department.")
        return str(row["name"])

    def list(self, search: str = "", status: str = "", department: str = "") -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if search.strip():
            clauses.append("(e.employee_id LIKE ? OR e.name LIKE ? OR e.email LIKE ?)")
            value = f"%{search.strip()}%"
            params.extend((value, value, value))
        if status in {"active", "suspended"}:
            clauses.append("e.status = ?")
            params.append(status)
        if department:
            clauses.append("e.department_id = ?")
            params.append(department)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.db.connect() as connection:
            rows = connection.execute(
                "SELECT e.id, e.employee_id, e.name, e.email, e.role, e.department_id, d.name AS department_name,"
                f" e.status, e.created_at, e.updated_at FROM employees e JOIN departments d ON d.id = e.department_id{where}"
                " ORDER BY e.name COLLATE NOCASE",
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        employee_id, name, email, department_id, password = self._employee_payload(payload, require_password=True)
        role = str(payload.get("role", "employee")).strip().lower()
        if role not in {"employee", "admin"}:
            raise DocumentError("Role must be employee or admin.")
        now = utc_now()
        try:
            with self.db.connect() as connection:
                department_name = self._require_department(connection, department_id)
                if department_name.casefold() == "admin":
                    role = "admin"
                cursor = connection.execute(
                    "INSERT INTO employees (employee_id, name, email, password_hash, department_id, role, status, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)",
                    (employee_id, name, email, _password_hash(password or ""), department_id, role, now, now),
                )
        except sqlite3.IntegrityError as exc:
            raise DocumentError("This employee ID or email already exists.", 409) from exc
        return self.get(int(cursor.lastrowid))

    def get(self, employee: int) -> dict[str, Any]:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT e.id, e.employee_id, e.name, e.email, e.role, e.department_id, d.name AS department_name,"
                " e.status, e.created_at, e.updated_at FROM employees e"
                " JOIN departments d ON d.id = e.department_id WHERE e.id = ?",
                (employee,),
            ).fetchone()
        if row is None:
            raise DocumentError("Employee not found.", 404)
        return dict(row)

    def update(self, employee: int, payload: dict[str, Any]) -> dict[str, Any]:
        employee_id, name, email, department_id, password = self._employee_payload(payload, require_password=False)
        status = str(payload.get("status", "active")).strip().lower()
        role = str(payload.get("role", "employee")).strip().lower()
        if status not in {"active", "suspended"}:
            raise DocumentError("Employee status must be active or suspended.")
        if role not in {"employee", "admin"}:
            raise DocumentError("Role must be employee or admin.")
        fields: list[Any] = [employee_id, name, email, department_id, role, status]
        password_sql = ""
        if password:
            password_sql = ", password_hash = ?"
            fields.append(_password_hash(password))
        fields.extend((utc_now(), employee))
        try:
            with self.db.connect() as connection:
                department_name = self._require_department(connection, department_id)
                if department_name.casefold() == "admin":
                    role = "admin"
                    fields[4] = role
                cursor = connection.execute(
                    "UPDATE employees SET employee_id = ?, name = ?, email = ?, department_id = ?, role = ?, status = ?"
                    f"{password_sql}, updated_at = ? WHERE id = ?",
                    fields,
                )
        except sqlite3.IntegrityError as exc:
            raise DocumentError("This employee ID or email already exists.", 409) from exc
        if not cursor.rowcount:
            raise DocumentError("Employee not found.", 404)
        return self.get(employee)

    def delete(self, employee: int) -> None:
        with self.db.connect() as connection:
            cursor = connection.execute("DELETE FROM employees WHERE id = ?", (employee,))
        if not cursor.rowcount:
            raise DocumentError("Employee not found.", 404)
