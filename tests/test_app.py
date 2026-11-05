"""End-to-end tests against a real server on a random port with a stub LLM."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from api.application import Application
from core.config import Settings
from rag.embedder import APIEmbeddingClient
from rag.llm import LLMClient
from vectorstore import LocalVectorStore


class StubLLM(LLMClient):
    provider, model = "stub", "stub-model"

    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    def generate(self, messages: list[dict[str, str]]) -> str:
        return "".join(self.stream(messages))

    def stream(self, messages):  # noqa: ANN001, ANN201
        self.calls.append(messages)
        yield "Answer "
        yield "from context [1]."


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in lines:
            events.append((lines["event"], json.loads(lines["data"])))
    return events


class AppTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.settings = Settings(
            store_path=root / "vectors.json",
            db_path=root / "app.db",
            documents_dir=root / "documents",
            chat_messages_per_minute=100,
        )
        self.env = patch.dict(os.environ, {"EMBEDDING_MODEL": "", "EMBEDDING_BASE_URL": ""})
        self.env.start()
        self.llm = StubLLM()
        self.app = Application(self.settings, llm=self.llm, embedding_client=APIEmbeddingClient())
        self.app.start()
        self.server = self.app.make_server("127.0.0.1", 0)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.app.stop()
        self.env.stop()
        self.directory.cleanup()

    # Helpers.

    def client(self) -> requests.Session:
        session = requests.Session()
        session.headers["X-CSRF-Token"] = session.get(f"{self.base}/api/session").json()["csrf_token"]
        return session

    def upload(self, session: requests.Session, name: str, content: bytes) -> requests.Response:
        return session.post(f"{self.base}/api/admin/documents", files=[("files", (name, content))])

    def upload_and_index(self, session: requests.Session, name: str, content: bytes) -> str:
        response = self.upload(session, name, content)
        self.assertEqual(response.status_code, 202, response.text)
        document_id = response.json()["results"][0]["document"]["id"]
        self.assertTrue(self.app.documents.wait_idle(10))
        detail = session.get(f"{self.base}/api/admin/documents/{document_id}").json()
        self.assertEqual(detail["status"], "indexed", detail)
        return document_id

    def ask(self, session: requests.Session, question: str) -> tuple[str, list[tuple[str, dict]]]:
        conversation = session.post(f"{self.base}/api/conversations").json()
        response = session.post(
            f"{self.base}/api/conversations/{conversation['id']}/messages", json={"content": question}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return conversation["id"], parse_sse(response.text)


class AccessTests(AppTestCase):
    def test_configured_csrf_token_is_stable_across_instances(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = Settings(
                store_path=root / "vectors.json",
                db_path=root / "app.db",
                documents_dir=root / "documents",
                csrf_token="shared-serverless-token",
            )
            first = Application(settings, llm=None, embedding_client=APIEmbeddingClient())
            second = Application(settings, llm=None, embedding_client=APIEmbeddingClient())
            self.assertEqual(first.csrf_token, "shared-serverless-token")
            self.assertEqual(first.csrf_token, second.csrf_token)

    def test_everything_is_available_without_signing_in(self) -> None:
        self.assertEqual(requests.get(f"{self.base}/").status_code, 200)
        self.assertEqual(requests.get(f"{self.base}/admin").status_code, 200)
        self.assertEqual(requests.get(f"{self.base}/api/conversations").status_code, 200)
        self.assertEqual(requests.get(f"{self.base}/api/admin/overview").status_code, 200)
        login = requests.get(f"{self.base}/login", allow_redirects=False)
        self.assertEqual((login.status_code, login.headers["Location"]), (302, "/"))

    def test_state_changes_require_csrf_token(self) -> None:
        client = self.client()
        del client.headers["X-CSRF-Token"]
        self.assertEqual(client.post(f"{self.base}/api/conversations").status_code, 403)
        self.assertEqual(client.post(f"{self.base}/api/admin/reindex").status_code, 403)

    def test_cross_origin_requests_are_blocked(self) -> None:
        client = self.client()
        response = client.post(f"{self.base}/api/conversations", headers={"Origin": "https://evil.example"})
        self.assertEqual(response.status_code, 403)

    def test_pages_and_static_files_are_contained(self) -> None:
        import http.client

        page = requests.get(f"{self.base}/")
        self.assertIn("default-src 'self'", page.headers["Content-Security-Policy"])
        self.assertEqual(page.headers["X-Frame-Options"], "DENY")
        self.assertEqual(requests.get(f"{self.base}/static/js/chat.js").status_code, 200)

        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1])
        for path in ("/static/../../app.py", "/static/js/../../../app.py", "/static/../../.env"):
            connection.request("GET", path)
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.status, 404, path)
            connection.close()

class DocumentAndChatTests(AppTestCase):
    def test_upload_index_chat_and_delete(self) -> None:
        admin = self.client()
        client = self.client()
        document_id = self.upload_and_index(
            admin, "handbook.txt", b"Intro\n\nOur refund policy: customers may request a refund within 30 days of purchase."
        )

        _, events = self.ask(client, "What is the refund policy?")
        kinds = [kind for kind, _ in events]
        self.assertEqual(kinds[0], "start")
        sources = dict(events)["sources"]["sources"]
        self.assertEqual(sources[0]["document"], "handbook.txt")
        self.assertEqual(sources[0]["location"], "Section 2")
        self.assertIn("done", kinds)
        self.assertIn("refund within 30 days", self.llm.calls[-1][-1]["content"])

        self.assertEqual(admin.delete(f"{self.base}/api/admin/documents/{document_id}").json()["removed_chunks"], 2)
        self.assertEqual(LocalVectorStore(self.settings.store_path).chunks, [])
        _, events = self.ask(client, "What is the refund policy?")
        self.assertEqual(dict(events)["sources"]["sources"], [])
        self.assertFalse(any(self.settings.documents_dir.iterdir()))

    def test_undo_delete_restores_document(self) -> None:
        admin = self.client()
        client = self.client()
        document_id = self.upload_and_index(admin, "returns.txt", b"Returns are accepted within 14 days of delivery.")
        self.assertEqual(admin.delete(f"{self.base}/api/admin/documents/{document_id}").status_code, 200)

        response = admin.post(f"{self.base}/api/admin/documents/{document_id}/restore")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "indexed")
        self.assertEqual(len(LocalVectorStore(self.settings.store_path).document_chunks(document_id)), 1)
        self.assertEqual(admin.get(f"{self.base}/api/admin/documents/{document_id}/file").status_code, 200)
        _, events = self.ask(client, "Within how many days are returns accepted?")
        self.assertEqual(dict(events)["sources"]["sources"][0]["document"], "returns.txt")

        # A second restore has nothing left to restore.
        self.assertEqual(admin.post(f"{self.base}/api/admin/documents/{document_id}/restore").status_code, 410)

    def test_multiple_documents_coexist(self) -> None:
        admin = self.client()
        self.upload_and_index(admin, "one.txt", b"Alpha topic about apples.")
        self.upload_and_index(admin, "two.txt", b"Beta topic about bananas.")
        names = {doc["filename"] for doc in admin.get(f"{self.base}/api/admin/documents").json()["documents"]}
        self.assertEqual(names, {"one.txt", "two.txt"})
        self.assertEqual(len(self.app.store.chunks), 2)

    def test_upload_validation(self) -> None:
        admin = self.client()
        self.upload_and_index(admin, "policy.txt", b"Original content here.")
        cases = {
            "fake.pdf": b"not really a pdf",
            "policy.txt": b"Original content here.",
            "virus.exe": b"MZ...",
            "empty.txt": b"",
        }
        for name, content in cases.items():
            result = self.upload(admin, name, content).json()["results"][0]
            self.assertFalse(result["ok"], name)
        renamed = self.upload(admin, "copy.txt", b"Original content here.").json()["results"][0]
        self.assertIn("already in the knowledge base", renamed["error"])

    def test_original_file_view_download_and_preview(self) -> None:
        admin = self.client()
        content = b"<script>alert(1)</script> Shipping takes five days."
        document_id = self.upload_and_index(admin, "shipping.txt", content)
        url = f"{self.base}/api/admin/documents/{document_id}/file"

        inline = admin.get(url)
        self.assertEqual(inline.status_code, 200)
        self.assertEqual(inline.content, content)
        self.assertEqual(inline.headers["Content-Type"], "text/plain; charset=utf-8")
        self.assertTrue(inline.headers["Content-Disposition"].startswith("inline;"))
        self.assertEqual(inline.headers["X-Frame-Options"], "SAMEORIGIN")
        self.assertIn("default-src 'none'", inline.headers["Content-Security-Policy"])

        download = admin.get(url, params={"download": "1"})
        self.assertEqual(download.content, content)
        self.assertEqual(download.headers["Content-Disposition"], "attachment; filename*=UTF-8''shipping.txt")

        # Plain text has no structured preview; the viewer frames the file instead.
        self.assertEqual(admin.get(f"{self.base}/api/admin/documents/{document_id}/preview").status_code, 404)
        self.assertEqual(admin.get(f"{self.base}/api/admin/documents/missing/file").status_code, 404)

    def test_office_preview(self) -> None:
        from openpyxl import Workbook

        from services.document_preview import office_preview

        path = Path(self.settings.documents_dir) / "sheet.xlsx"
        workbook = Workbook()
        workbook.active.title = "Dyes"
        workbook.active.append(["Name", "Fixation"])
        workbook.active.append(["Red 195", 0.82])
        workbook.create_sheet("Empty")
        workbook.save(path)
        preview = office_preview(path)
        self.assertEqual(preview["kind"], "spreadsheet")
        self.assertEqual(preview["sheets"][0], {"name": "Dyes", "rows": [["Name", "Fixation"], ["Red 195", "0.82"]]})
        self.assertEqual(preview["sheets"][1], {"name": "Empty", "rows": []})

        from docx import Document

        path = Path(self.settings.documents_dir) / "memo.docx"
        document = Document()
        document.add_heading("Memo", level=1)
        document.add_paragraph("Before the table.")
        document.add_table(rows=1, cols=2).rows[0].cells[0].text = "Cell"
        document.add_paragraph("After the table.")
        document.save(path)
        blocks = office_preview(path)["blocks"]
        self.assertEqual([block["type"] for block in blocks], ["heading", "paragraph", "table", "paragraph"])
        self.assertEqual(blocks[2]["rows"], [["Cell", ""]])

    def test_path_traversal_filename_is_neutralized(self) -> None:
        admin = self.client()
        response = self.upload(admin, "../../evil.txt", b"harmless text body")
        result = response.json()["results"][0]
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["document"]["filename"], "evil.txt")
        stored = list(self.settings.documents_dir.iterdir())
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].parent, self.settings.documents_dir)

    def test_failed_ingestion_is_reported(self) -> None:
        admin = self.client()
        response = self.upload(admin, "data.json", b"{}")
        document_id = response.json()["results"][0]["document"]["id"]
        self.assertTrue(self.app.documents.wait_idle(10))
        detail = admin.get(f"{self.base}/api/admin/documents/{document_id}").json()
        self.assertEqual(detail["status"], "failed")
        self.assertIn("No readable text", detail["error"])
        self.assertEqual(self.app.store.chunks, [])

    def test_reindex_document(self) -> None:
        admin = self.client()
        document_id = self.upload_and_index(admin, "guide.txt", b"Setup guide for the device.")
        self.assertEqual(admin.post(f"{self.base}/api/admin/documents/{document_id}/reindex").status_code, 202)
        self.assertTrue(self.app.documents.wait_idle(10))
        self.assertEqual(self.app.documents.get_summary(document_id)["status"], "indexed")
        self.assertEqual(len(self.app.store.chunks), 1)
        self.assertEqual(admin.post(f"{self.base}/api/admin/reindex").status_code, 202)
        self.assertTrue(self.app.documents.wait_idle(10))
        self.assertEqual(self.app.documents.get_summary(document_id)["status"], "indexed")

    def test_conversation_history_is_saved(self) -> None:
        client = self.client()
        conversation_id, _ = self.ask(client, "Hello there")
        history = client.get(f"{self.base}/api/conversations/{conversation_id}").json()
        self.assertEqual([message["role"] for message in history["messages"]], ["user", "assistant"])
        self.assertEqual(history["title"], "Hello there")
        self.assertEqual(client.delete(f"{self.base}/api/conversations/{conversation_id}").status_code, 200)
        self.assertEqual(client.get(f"{self.base}/api/conversations/{conversation_id}").status_code, 404)

    def test_delete_all_conversations(self) -> None:
        client = self.client()
        first, _ = self.ask(client, "Question one")
        self.ask(client, "Question two")
        response = client.delete(f"{self.base}/api/conversations")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json()["deleted"], 2)
        self.assertEqual(client.get(f"{self.base}/api/conversations").json()["conversations"], [])
        self.assertEqual(client.get(f"{self.base}/api/conversations/{first}").status_code, 404)

    def test_regenerate_replaces_last_answer(self) -> None:
        client = self.client()
        conversation_id, _ = self.ask(client, "Question one")
        response = client.post(f"{self.base}/api/conversations/{conversation_id}/regenerate")
        self.assertEqual(response.status_code, 200)
        messages = client.get(f"{self.base}/api/conversations/{conversation_id}").json()["messages"]
        self.assertEqual([message["role"] for message in messages], ["user", "assistant"])

    def test_model_failure_returns_friendly_error(self) -> None:
        client = self.client()

        def broken(messages):  # noqa: ANN001, ANN202
            raise RuntimeError("Gemini request failed: 503 secret internal detail")
            yield ""

        self.llm.stream = broken  # type: ignore[method-assign]
        _, events = self.ask(client, "Anything")
        error = dict(events)["error"]["message"]
        self.assertNotIn("secret", error)
        self.assertIn("temporarily unavailable", error)


class FallbackTests(AppTestCase):
    def test_general_question_uses_small_knowledge_base(self) -> None:
        client = self.client()
        self.upload_and_index(client, "invoice.txt", b"Invoice total INR 2359 for the VIP ticket.")
        _, events = self.ask(client, "tell me about the document")
        self.assertEqual(dict(events)["sources"]["sources"][0]["document"], "invoice.txt")
        self.assertIn("INR 2359", self.llm.calls[-1][-1]["content"])

    def test_model_failure_falls_back_to_passages(self) -> None:
        client = self.client()
        self.upload_and_index(client, "invoice.txt", b"Invoice total INR 2359 for the VIP ticket.")

        def quota_exceeded(messages):  # noqa: ANN001, ANN202
            raise RuntimeError('Gemini request failed: 429 {"error": {"code": 429, "message": "You exceeded your current quota."}}')
            yield ""

        self.llm.stream = quota_exceeded  # type: ignore[method-assign]
        _, events = self.ask(client, "What is the invoice total?")
        answer = "".join(data["text"] for kind, data in events if kind == "delta")
        self.assertIn("AI model is unavailable", answer)
        self.assertIn("INR 2359", answer)
        self.assertIn("done", [kind for kind, _ in events])
        health = {check["name"]: check for check in client.get(f"{self.base}/api/admin/health").json()["checks"]}
        self.assertFalse(health["Language model"]["ok"])
        self.assertIn("You exceeded your current quota.", health["Language model"]["detail"])


class LegacyMigrationTests(unittest.TestCase):
    def test_existing_index_is_adopted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = LocalVectorStore(root / "vectors.json")
            store.add_chunks(
                [{"source": "old.pdf:page_1#chunk_1", "text": "legacy text"}, {"source": "old.pdf:page_2#chunk_1", "text": "more"}],
                [[1.0, 0.0], [0.0, 1.0]],
            )
            store.save()
            settings = Settings(store_path=root / "vectors.json", db_path=root / "app.db", documents_dir=root / "docs")
            app = Application(settings, llm=None, embedding_client=APIEmbeddingClient())
            app.start()
            try:
                documents = app.documents.list()
                self.assertEqual([(doc["filename"], doc["status"], doc["chunk_count"]) for doc in documents], [("old.pdf", "indexed", 2)])
                self.assertTrue(all(chunk["document_id"] == documents[0]["id"] for chunk in app.store.chunks))
            finally:
                app.stop()
            time.sleep(0.05)


if __name__ == "__main__":
    unittest.main()
