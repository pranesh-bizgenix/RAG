"""Tests for the Vercel request adapter."""

from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
