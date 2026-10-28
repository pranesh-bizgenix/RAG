"""Microsoft Word text extraction."""

from pathlib import Path


def parse_word(path: Path) -> list[dict[str, str]]:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("Word parsing requires 'python-docx'.") from exc

    output = []
    for index, paragraph in enumerate(Document(str(path)).paragraphs, start=1):
        if text := paragraph.text.strip():
            output.append({"source": f"{path.name}:paragraph_{index}", "text": text})
    return output
