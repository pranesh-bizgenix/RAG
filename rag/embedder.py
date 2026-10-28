"""Local and OpenAI-compatible embedding backends."""

from __future__ import annotations

import os
import re
from hashlib import blake2b

import numpy as np
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

STOPWORDS = frozenset(
    "a an and are as at be by for from how i if in is it of on or should the to what when where with you your".split()
)


def tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-zA-Z]{2,}", text.lower()) if token not in STOPWORDS]


def hash_embedding(text: str, dimensions: int = 512) -> list[float]:
    vector = np.zeros(dimensions, dtype=np.float32)
    for token in tokenize(text):
        token_hash = int.from_bytes(blake2b(token.encode("utf-8"), digest_size=8).digest(), "big")
        vector[token_hash % dimensions] += 1.0
    norm = np.linalg.norm(vector)
    return (vector / norm if norm else vector).tolist()


class APIEmbeddingClient:
    """Embedding client for any API implementing the OpenAI embeddings schema."""

    def __init__(self) -> None:
        self.api_key = os.getenv("EMBEDDING_API_KEY", "").strip()
        self.model = os.getenv("EMBEDDING_MODEL", "").strip()
        self.base_url = os.getenv("EMBEDDING_BASE_URL", "").strip() or "https://api.openai.com/v1"
        self.timeout = int(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "60"))

    @property
    def is_configured(self) -> bool:
        return bool(self.model and self.base_url)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not self.is_configured:
            raise RuntimeError("EMBEDDING_MODEL and EMBEDDING_BASE_URL must be configured.")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        response = requests.post(
            f"{self.base_url.rstrip('/')}/embeddings",
            headers=headers,
            json={"model": self.model, "input": texts},
            timeout=self.timeout,
        )
        if not response.ok:
            raise RuntimeError(f"Embedding request failed: {response.status_code} {response.text}")
        items = sorted(response.json()["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in items]


def embed_texts(texts: list[str], backend: str, client: APIEmbeddingClient) -> list[list[float]]:
    if backend in {"api", "openai"}:  # "openai" keeps older vector stores compatible.
        return client.embed_texts(texts)
    if backend == "local-hash":
        return [hash_embedding(text) for text in texts]
    raise ValueError(f"Unsupported embedding backend: {backend}")
