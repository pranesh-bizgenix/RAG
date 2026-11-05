"""Tests for HTTP behavior that differs under serverless adapters."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from api.http import EventStream


class EventStreamTests(unittest.TestCase):
    def test_unsupported_socket_probe_does_not_fake_a_disconnect(self) -> None:
        stream = EventStream.__new__(EventStream)
        stream.handler = SimpleNamespace(connection=object())
        with patch("api.http.select.select", side_effect=ValueError("not selectable")):
            self.assertFalse(stream.client_gone())


if __name__ == "__main__":
    unittest.main()
