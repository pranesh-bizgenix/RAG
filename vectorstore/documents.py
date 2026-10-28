"""Command-line document management for the local vector store."""

from __future__ import annotations

import argparse
from pathlib import Path

from .stats import document_name, get_store_stats
from .store import LocalVectorStore


def document_chunk_counts(store: LocalVectorStore) -> dict[str, int]:
    """Return each indexed document and its number of chunks."""

    counts: dict[str, int] = {}
    for chunk in store.chunks:
        name = document_name(str(chunk.get("source", ""))).strip()
        if name:
            counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[0].casefold()))


def delete_document(store: LocalVectorStore, name: str) -> int:
    """Delete one exact document from the store and return its removed chunk count."""

    requested = name.strip().casefold()
    retained = [
        chunk
        for chunk in store.chunks
        if document_name(str(chunk.get("source", ""))).strip().casefold() != requested
    ]
    removed = len(store.chunks) - len(retained)
    if not removed:
        return 0

    for index, chunk in enumerate(retained):
        chunk["id"] = index
    store.chunks = retained
    store.save()
    return removed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List or delete indexed documents.")
    parser.add_argument(
        "--store",
        type=Path,
        default=Path("storage/vectors.json"),
        help="Path to the vector-store JSON file",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="List documents and their chunk counts")

    delete_parser = subparsers.add_parser("delete", help="Delete one document and all its chunks")
    delete_parser.add_argument("name", help="Exact document filename shown by the list command")
    delete_parser.add_argument("--yes", action="store_true", help="Delete without prompting")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    store = LocalVectorStore(args.store)

    if args.command == "list":
        counts = document_chunk_counts(store)
        if not counts:
            print("No documents are currently indexed.")
            return
        print(f"Documents: {len(counts)}")
        print(f"Chunks: {sum(counts.values())}")
        for name, chunks in counts.items():
            print(f"  - {name} ({chunks} chunks)")
        return

    counts = document_chunk_counts(store)
    matched_name = next((name for name in counts if name.casefold() == args.name.strip().casefold()), None)
    if matched_name is None:
        raise SystemExit(f'Document not found: "{args.name}"')

    if not args.yes:
        answer = input(
            f'Delete "{matched_name}" and its {counts[matched_name]} chunks? [y/N] '
        ).strip().casefold()
        if answer not in {"y", "yes"}:
            print("Deletion cancelled.")
            return

    removed = delete_document(store, matched_name)
    remaining = get_store_stats(store)
    print(f'Deleted "{matched_name}" ({removed} chunks).')
    print(f"Remaining documents: {remaining.document_count}")
    print(f"Remaining chunks: {remaining.chunk_count}")


if __name__ == "__main__":
    main()
