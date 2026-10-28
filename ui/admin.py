"""Knowledge-base ingestion service used by the admin CLI."""

from pathlib import Path

from parsers import load_documents
from rag.embedder import APIEmbeddingClient, embed_texts
from vectorstore import LocalVectorStore


def chunk_text(text: str, chunk_size: int = 180, overlap: int = 40) -> list[str]:
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than overlap.")
    words = text.split()
    chunks, step = [], chunk_size - overlap
    for start in range(0, len(words), step):
        chunks.append(" ".join(words[start : start + chunk_size]))
        if start + chunk_size >= len(words):
            break
    return chunks


def chunk_documents(documents: list[dict[str, str]], chunk_size: int = 180, overlap: int = 40) -> list[dict[str, str]]:
    return [{"source": f"{doc['source']}#chunk_{index}", "text": text} for doc in documents for index, text in enumerate(chunk_text(doc["text"], chunk_size, overlap), start=1)]


class IngestionService:
    def __init__(self, store_path: Path | str) -> None:
        self.store = LocalVectorStore(store_path)
        self.client = APIEmbeddingClient()

    def ingest(self, input_path: Path | str, backend: str = "auto", chunk_size: int = 180, overlap: int = 40, reset: bool = False) -> int:
        chunks = chunk_documents(load_documents(input_path), chunk_size, overlap)
        if not chunks:
            raise ValueError("No valid text chunks were created from the input file.")
        selected = ("api" if self.client.is_configured else "local-hash") if backend == "auto" else backend
        vectors = embed_texts([chunk["text"] for chunk in chunks], selected, self.client)
        if reset:
            self.store.reset()
        self.store.set_metadata(selected, len(vectors[0]))
        self.store.add_chunks(chunks, vectors)
        self.store.save()
        return len(chunks)
