"""JSON-backed vector store for local development and small deployments."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

import numpy as np

from rag.embedder import tokenize


class LocalVectorStore:
    """Thread-safe store. Mutations swap in new lists, so searches work on consistent snapshots."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.embedding_backend = "local-hash"
        self.embedding_model = ""
        self.dimension = 512
        self._lock = threading.RLock()
        self._chunks: list[dict[str, Any]] = []
        self._matrix: np.ndarray | None = None
        self._token_sets: list[frozenset[str]] | None = None
        if self.path.exists():
            self.load()

    @property
    def chunks(self) -> list[dict[str, Any]]:
        return self._chunks

    @chunks.setter
    def chunks(self, value: list[dict[str, Any]]) -> None:
        with self._lock:
            self._chunks = list(value)
            self._matrix = None
            self._token_sets = None

    def set_metadata(self, embedding_backend: str, dimension: int, embedding_model: str = "") -> None:
        self.embedding_backend = embedding_backend
        self.dimension = int(dimension)
        self.embedding_model = embedding_model

    def add_chunks(self, chunks: list[dict[str, Any]], vectors: list[list[float]]) -> None:
        """Replace the whole store with the given chunks (original single-document behaviour)."""
        if len(chunks) != len(vectors):
            raise ValueError("Chunks and vectors length mismatch.")
        self.chunks = [
            {"id": index, "source": chunk["source"], "text": chunk["text"], "vector": vector}
            for index, (chunk, vector) in enumerate(zip(chunks, vectors))
        ]

    def reset(self) -> None:
        self.chunks = []

    # Document-level operations used by the ingestion service.

    def document_chunks(self, document_id: str) -> list[dict[str, Any]]:
        return [chunk for chunk in self._chunks if chunk.get("document_id") == document_id]

    def document_ids(self) -> set[str]:
        return {str(chunk["document_id"]) for chunk in self._chunks if chunk.get("document_id")}

    def replace_document(
        self,
        document_id: str,
        chunks: list[dict[str, Any]],
        vectors: list[list[float]],
        embedding_backend: str,
        embedding_model: str = "",
    ) -> None:
        """Atomically swap one document's chunks; other documents must share the embedding space."""
        if len(chunks) != len(vectors) or not chunks:
            raise ValueError("Chunks and vectors must be non-empty and of equal length.")
        with self._lock:
            retained = [chunk for chunk in self._chunks if chunk.get("document_id") != document_id]
            if retained and (self.embedding_backend, self.dimension, self.embedding_model) != (
                embedding_backend,
                len(vectors[0]),
                embedding_model,
            ):
                raise ValueError("Embedding configuration differs from the existing index. Reindex all documents.")
            added = [
                {"document_id": document_id, "source": chunk["source"], "text": chunk["text"], "vector": vector}
                for chunk, vector in zip(chunks, vectors)
            ]
            self.set_metadata(embedding_backend, len(vectors[0]), embedding_model)
            self.chunks = self._renumber(retained + added)

    def remove_document(self, document_id: str) -> int:
        with self._lock:
            retained = [chunk for chunk in self._chunks if chunk.get("document_id") != document_id]
            removed = len(self._chunks) - len(retained)
            if removed:
                self.chunks = self._renumber(retained)
            return removed

    def replace_all(
        self,
        chunks: list[dict[str, Any]],
        vectors: list[list[float]],
        embedding_backend: str,
        embedding_model: str = "",
    ) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("Chunks and vectors length mismatch.")
        with self._lock:
            dimension = len(vectors[0]) if vectors else self.dimension
            self.set_metadata(embedding_backend, dimension, embedding_model)
            self.chunks = self._renumber(
                [{**{k: v for k, v in chunk.items() if k != "vector"}, "vector": vector} for chunk, vector in zip(chunks, vectors)]
            )

    @staticmethod
    def _renumber(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{**chunk, "id": index} for index, chunk in enumerate(chunks)]

    # Persistence.

    def save(self) -> None:
        with self._lock:
            payload = {
                "metadata": {
                    "embedding_backend": self.embedding_backend,
                    "embedding_model": self.embedding_model,
                    "dimension": self.dimension,
                },
                "chunks": self._chunks,
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(f"{self.path.name}.tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
            os.replace(temporary, self.path)  # readers never see a half-written file

    def load(self) -> None:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        metadata = data.get("metadata", {})
        with self._lock:
            self.embedding_backend = metadata.get("embedding_backend", "local-hash")
            self.embedding_model = metadata.get("embedding_model", "")
            self.dimension = int(metadata.get("dimension", 512))
            self.chunks = data.get("chunks", [])

    # Search.

    def _snapshot_matrix(self) -> tuple[list[dict[str, Any]], np.ndarray | None]:
        with self._lock:
            chunks = self._chunks
            if self._matrix is None and chunks:
                matrix = np.asarray([item["vector"] for item in chunks], dtype=np.float32)
                if matrix.ndim == 2:
                    norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-8
                    self._matrix = matrix / norms
            return chunks, self._matrix

    def _snapshot_tokens(self) -> tuple[list[dict[str, Any]], list[frozenset[str]]]:
        with self._lock:
            if self._token_sets is None:
                self._token_sets = [frozenset(tokenize(item["text"])) for item in self._chunks]
            return self._chunks, self._token_sets

    @staticmethod
    def _result(item: dict[str, Any], score: float) -> dict[str, Any]:
        return {
            "document_id": item.get("document_id"),
            "source": item["source"],
            "text": item["text"],
            "score": float(score),
        }

    def search_by_vector(self, query_vector: list[float], top_k: int = 4) -> list[dict[str, Any]]:
        chunks, matrix = self._snapshot_matrix()
        if not chunks or matrix is None:
            return []
        query = np.asarray(query_vector, dtype=np.float32)
        if matrix.shape[1] != query.shape[0]:
            return []
        scores = matrix @ (query / (np.linalg.norm(query) + 1e-8))
        return [self._result(chunks[int(i)], scores[i]) for i in np.argsort(scores)[::-1][:top_k]]

    def search_lexical(self, query: str, top_k: int = 4) -> list[dict[str, Any]]:
        query_tokens = set(tokenize(query))
        if not query_tokens:
            return []
        chunks, token_sets = self._snapshot_tokens()
        results = [
            self._result(item, len(query_tokens & tokens) / len(query_tokens))
            for item, tokens in zip(chunks, token_sets)
        ]
        results.sort(key=lambda item: item["score"], reverse=True)
        positive = [item for item in results if item["score"] > 0]
        return (positive or results)[:top_k]
