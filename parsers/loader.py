"""Choose the correct parser for an input document."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .excel_parser import parse_excel
from .image_parser import parse_image
from .pdf_parser import parse_pdf
from .word_parser import parse_word

Document = dict[str, str]
Parser = Callable[[Path], list[Document]]


def _parse_json(path: Path) -> list[Document]:
    def flatten(value: object, prefix: str = "") -> list[Document]:
        documents: list[Document] = []
        if isinstance(value, dict):
            for key, child in value.items():
                name = f"{prefix}.{key}" if prefix else str(key)
                documents.extend(flatten(child, name))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                documents.extend(flatten(child, f"{prefix}[{index}]"))
        elif value is not None and (text := str(value).strip()):
            documents.append({"source": prefix or "root", "text": text})
        return documents

    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        {"source": f"{path.name}:{item['source']}", "text": item["text"]}
        for item in flatten(data)
        if len(item["text"]) > 10
    ]


def _parse_text(path: Path) -> list[Document]:
    import re

    text = path.read_text(encoding="utf-8")
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    return [
        {"source": f"{path.name}:block_{index}", "text": block}
        for index, block in enumerate(blocks, start=1)
    ]


PARSERS: dict[str, Parser] = {
    ".json": _parse_json,
    ".txt": _parse_text,
    ".md": _parse_text,
    ".pdf": parse_pdf,
    ".docx": parse_word,
    ".xlsx": parse_excel,
    ".xlsm": parse_excel,
    ".png": parse_image,
    ".jpg": parse_image,
    ".jpeg": parse_image,
    ".tif": parse_image,
    ".tiff": parse_image,
}
SUPPORTED_EXTENSIONS = frozenset(PARSERS)


def load_documents(file_path: Path | str) -> list[Document]:
    """Parse one supported file into source-labelled text documents."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")
    try:
        parser = PARSERS[path.suffix.lower()]
    except KeyError as exc:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(f"Unsupported file type '{path.suffix}'. Supported: {supported}") from exc
    return parser(path)
