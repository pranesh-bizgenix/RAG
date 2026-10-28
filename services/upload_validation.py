"""Validation for uploaded knowledge-base files."""

from __future__ import annotations

import json
import re
import unicodedata
import zipfile
from io import BytesIO
from pathlib import PurePosixPath, PureWindowsPath

from parsers import SUPPORTED_EXTENSIONS

CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".json": "application/json",
    ".txt": "text/plain",
    ".md": "text/markdown",
}

_OFFICE_MARKERS = {".docx": "word/", ".xlsx": "xl/", ".xlsm": "xl/"}


class UploadError(ValueError):
    pass


def safe_filename(raw_name: str) -> str:
    """Strip directories and characters that would break storage or citation labels."""
    name = PureWindowsPath(PurePosixPath(raw_name or "").name).name
    name = unicodedata.normalize("NFC", name)
    # ':' and '#' delimit locations in chunk labels such as "file.pdf:page_1#chunk_2".
    name = re.sub(r'[\x00-\x1f\x7f:#<>"/\\|?*]', "_", name).strip(" .")
    if not name or name.startswith("."):
        raise UploadError("The file name is not valid.")
    stem, dot, suffix = name.rpartition(".")
    if len(name) > 150:
        name = f"{stem[: 150 - len(suffix) - 1]}.{suffix}" if dot else name[:150]
    return name


def validate_upload(raw_name: str, data: bytes, max_bytes: int) -> tuple[str, str, str]:
    """Return ``(filename, extension, content_type)`` or raise ``UploadError``."""
    filename = safe_filename(raw_name)
    extension = PurePosixPath(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise UploadError(f"Unsupported file type. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
    if not data:
        raise UploadError("The file is empty.")
    if len(data) > max_bytes:
        raise UploadError(f"The file exceeds the {max_bytes // (1024 * 1024)} MB limit.")
    if not _content_matches(extension, data):
        raise UploadError(f"The file content does not match its {extension} extension.")
    return filename, extension, CONTENT_TYPES[extension]


def _content_matches(extension: str, data: bytes) -> bool:
    if extension == ".pdf":
        return data[:1024].lstrip().startswith(b"%PDF-")
    if extension in _OFFICE_MARKERS:
        if not data.startswith(b"PK\x03\x04"):
            return False
        try:
            with zipfile.ZipFile(BytesIO(data)) as archive:
                names = archive.namelist()
        except zipfile.BadZipFile:
            return False
        return any(name.startswith(_OFFICE_MARKERS[extension]) for name in names)
    if extension == ".png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if extension in {".jpg", ".jpeg"}:
        return data.startswith(b"\xff\xd8\xff")
    if extension in {".tif", ".tiff"}:
        return data[:4] in {b"II*\x00", b"MM\x00*"}
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return False
    if "\x00" in text:
        return False
    if extension == ".json":
        try:
            json.loads(text)
        except json.JSONDecodeError:
            return False
    return True
