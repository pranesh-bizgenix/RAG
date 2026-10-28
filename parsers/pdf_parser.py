"""PDF text extraction."""

from pathlib import Path


def parse_pdf(path: Path) -> list[dict[str, str]]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF parsing requires 'pypdf'.") from exc

    documents = []
    for page_number, page in enumerate(PdfReader(str(path)).pages, start=1):
        if text := (page.extract_text() or "").strip():
            documents.append({"source": f"{path.name}:page_{page_number}", "text": text})
    return documents
