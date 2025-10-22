"""Persistence helpers for pdfassembler."""

from __future__ import annotations

import json
from pathlib import Path

from .document import PDFDocument
from .pdf_writer import build_pdf

METADATA_MARKER = b"%%PDFAssembler:"


def save_pdf(document: PDFDocument, path: str | Path) -> None:
    metadata = document.to_dict()
    metadata_bytes = json.dumps(metadata, separators=(",", ":"), sort_keys=True).encode("utf-8")
    pdf_bytes = build_pdf(document, metadata_bytes)
    Path(path).write_bytes(pdf_bytes)


def load_pdf(path: str | Path) -> PDFDocument:
    data = Path(path).read_bytes()
    marker_index = data.rfind(METADATA_MARKER)
    if marker_index == -1:
        raise ValueError("The PDF does not contain pdfassembler metadata and cannot be edited")
    metadata_start = marker_index + len(METADATA_MARKER)
    metadata_end = data.find(b"\n", metadata_start)
    if metadata_end == -1:
        metadata_end = len(data)
    metadata_bytes = data[metadata_start:metadata_end]
    metadata = json.loads(metadata_bytes.decode("utf-8"))
    return PDFDocument.from_dict(metadata)


__all__ = ["load_pdf", "save_pdf"]
