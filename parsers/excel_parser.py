"""Excel cell extraction."""

from pathlib import Path


def parse_excel(path: Path) -> list[dict[str, str]]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError("Excel parsing requires 'openpyxl'.") from exc

    workbook = load_workbook(path, read_only=True, data_only=True)
    output = []
    try:
        for sheet in workbook.worksheets:
            for row_number, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                values = [str(value).strip() for value in row if value is not None and str(value).strip()]
                if values:
                    output.append(
                        {
                            "source": f"{path.name}:{sheet.title}:row_{row_number}",
                            "text": " | ".join(values),
                        }
                    )
    finally:
        workbook.close()
    return output
