import json
import tempfile
import unittest
from pathlib import Path

from vectorstore.stats import document_name, get_store_stats


class VectorStoreStatsTests(unittest.TestCase):
    def test_document_name_removes_location_and_chunk_suffix(self) -> None:
        self.assertEqual(document_name("report.pdf:page_2#chunk_3"), "report.pdf")
        self.assertEqual(document_name("notes.txt#chunk_1"), "notes.txt")

    def test_counts_unique_documents_and_all_chunks(self) -> None:
        payload = {
            "metadata": {"embedding_backend": "local-hash", "dimension": 2},
            "chunks": [
                {"source": "one.pdf:page_1#chunk_1", "text": "a", "vector": [1, 0]},
                {"source": "one.pdf:page_1#chunk_2", "text": "b", "vector": [0, 1]},
                {"source": "two.txt:block_1#chunk_1", "text": "c", "vector": [1, 1]},
            ],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "vectors.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            stats = get_store_stats(path)

        self.assertEqual(stats.document_count, 2)
        self.assertEqual(stats.chunk_count, 3)
        self.assertEqual(stats.documents, ("one.pdf", "two.txt"))


if __name__ == "__main__":
    unittest.main()
