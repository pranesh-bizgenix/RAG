"""Statistics for the local JSON vector store."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .store import LocalVectorStore


@dataclass(frozen=True)
class StoreStats:
    """Counts and source names currently present in a vector store."""

    document_count: int
    chunk_count: int
    documents: tuple[str, ...]


def document_name(source: str) -> str:
    """Return the original filename from a chunk source label."""

    return source.partition(":")[0].partition("#chunk_")[0]


def get_store_stats(store: LocalVectorStore | Path | str) -> StoreStats:
    """Calculate document and chunk totals for a store or store path."""

    vector_store = store if isinstance(store, LocalVectorStore) else LocalVectorStore(store)
    documents = tuple(
        sorted(
            {
                name
                for chunk in vector_store.chunks
                if (name := document_name(str(chunk.get("source", ""))).strip())
            }
        )
    )
    return StoreStats(
        document_count=len(documents),
        chunk_count=len(vector_store.chunks),
        documents=documents,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show local vector-store statistics.")
    parser.add_argument(
        "--store",
        type=Path,
        default=Path("storage/vectors.json"),
        help="Path to the vector-store JSON file",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stats = get_store_stats(args.store)
    if args.json:
        payload = asdict(stats)
        payload["documents"] = list(stats.documents)
        print(json.dumps(payload, indent=2))
        return

    print(f"Documents: {stats.document_count}")
    print(f"Chunks: {stats.chunk_count}")
    if stats.documents:
        print("Sources:")
        for name in stats.documents:
            print(f"  - {name}")


if __name__ == "__main__":
    main()
