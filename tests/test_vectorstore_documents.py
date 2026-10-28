import json
import tempfile
import unittest
from pathlib import Path

from vectorstore.documents import delete_document, document_chunk_counts
from vectorstore.store import LocalVectorStore


class VectorStoreDocumentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary_directory.name) / "vectors.json"
        self.path.write_text(
            json.dumps(
                {
                    "metadata": {"embedding_backend": "local-hash", "dimension": 2},
                    "chunks": [
                        {"id": 0, "source": "one.pdf:page_1#chunk_1", "text": "a", "vector": [1, 0]},
                        {"id": 1, "source": "one.pdf:page_1#chunk_2", "text": "b", "vector": [0, 1]},
                        {"id": 2, "source": "two.txt:block_1#chunk_1", "text": "c", "vector": [1, 1]},
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_lists_chunk_count_for_each_document(self) -> None:
        counts = document_chunk_counts(LocalVectorStore(self.path))
        self.assertEqual(counts, {"one.pdf": 2, "two.txt": 1})

    def test_deletes_only_the_requested_document(self) -> None:
        store = LocalVectorStore(self.path)
        self.assertEqual(delete_document(store, "ONE.PDF"), 2)

        reloaded = LocalVectorStore(self.path)
        self.assertEqual(document_chunk_counts(reloaded), {"two.txt": 1})
        self.assertEqual(reloaded.chunks[0]["id"], 0)

    def test_missing_document_does_not_change_store(self) -> None:
        store = LocalVectorStore(self.path)
        self.assertEqual(delete_document(store, "missing.pdf"), 0)
        self.assertEqual(len(LocalVectorStore(self.path).chunks), 3)


if __name__ == "__main__":
    unittest.main()
