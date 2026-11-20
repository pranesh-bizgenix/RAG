"""Tests for the Vercel request adapter."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from api.index import _original_target


class VercelAdapterTests(unittest.TestCase):
    def test_internal_rewrite_restores_public_path_and_query(self) -> None:
        self.assertEqual(_original_target("/api/index?__path=/"), "/")
        self.assertEqual(
            _original_target("/api/index?__path=/api/admin/documents&q=delivery&status=indexed"),
            "/api/admin/documents?q=delivery&status=indexed",
        )

    def test_local_request_is_unchanged(self) -> None:
        self.assertEqual(_original_target("/api/health"), "/api/health")

    def test_static_frontend_is_not_rewritten_through_python(self) -> None:
        root = Path(__file__).resolve().parent.parent
        config = json.loads((root / "vercel.json").read_text(encoding="utf-8"))
        rewrites = {item["source"]: item["destination"] for item in config["rewrites"]}
        sources = list(rewrites)
        self.assertIn("/api/:path*", sources)
        self.assertNotIn("/(.*)", sources)
        self.assertEqual(rewrites["/login"], "/login.html")
        self.assertTrue((root / "public" / "index.html").is_file())
        self.assertTrue((root / "public" / "login.html").is_file())
        self.assertTrue((root / "public" / "static" / "js" / "chat.js").is_file())


if __name__ == "__main__":
    unittest.main()
