"""Structured previews of Office files, which browsers cannot display natively."""

from __future__ import annotations

from pathlib import Path
from typing import Any

MAX_ROWS = 500
MAX_COLUMNS = 50
MAX_BLOCKS = 2000


def _cell(value: Any) -> str:
    return "" if value is None else str(value)


def _excel(path: Path) -> dict[str, Any]:
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    sheets, truncated = [], False
    try:
        for sheet in workbook.worksheets:
            rows = []
            for row in sheet.iter_rows(values_only=True):
                if len(rows) == MAX_ROWS:
                    truncated = True
                    break
                truncated = truncated or len(row) > MAX_COLUMNS
                rows.append([_cell(value) for value in row[:MAX_COLUMNS]])
            # Drop trailing blank rows and columns that read-only mode reports for formatted cells.
            while rows and not any(rows[-1]):
                rows.pop()
            width = max((max((i + 1 for i, value in enumerate(row) if value), default=0) for row in rows), default=0)
            sheets.append({"name": sheet.title, "rows": [row[:width] for row in rows]})
    finally:
        workbook.close()
    return {"kind": "spreadsheet", "sheets": sheets, "truncated": truncated}


def _word(path: Path) -> dict[str, Any]:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = Document(str(path))
    blocks: list[dict[str, Any]] = []
    # Walk the body in order so tables stay between the paragraphs that surround them.
    for element in document.element.body.iterchildren():
        if len(blocks) == MAX_BLOCKS:
            return {"kind": "document", "blocks": blocks, "truncated": True}
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "p":
            paragraph = Paragraph(element, document)
            style = (paragraph.style.name if paragraph.style is not None else "").lower()
            level = int(style[-1]) if style.startswith("heading") and style[-1:].isdigit() else 0
            if style == "title":
                level = 1
            blocks.append({"type": "heading" if level else "paragraph", "level": min(level, 4), "text": paragraph.text})
        elif tag == "tbl":
            table = Table(element, document)
            blocks.append({"type": "table", "rows": [[cell.text for cell in row.cells] for row in table.rows[:MAX_ROWS]]})
    # Collapse runs of empty paragraphs.
    cleaned = [b for i, b in enumerate(blocks) if b.get("text") or b["type"] == "table" or (i and blocks[i - 1].get("text"))]
    return {"kind": "document", "blocks": cleaned, "truncated": False}


PREVIEWERS = {".xlsx": _excel, ".xlsm": _excel, ".docx": _word}


def office_preview(path: Path) -> dict[str, Any] | None:
    """Return a JSON-friendly preview, or ``None`` if the type is not an Office format."""
    previewer = PREVIEWERS.get(path.suffix.lower())
    return previewer(path) if previewer else None
