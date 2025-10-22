"""Public interface for the lightweight pdfassembler package used in tests."""

from .document import EditablePDF, EditablePage, TextElement, ImageElement, PDFAssemblerError

__all__ = [
    "EditablePDF",
    "EditablePage",
    "TextElement",
    "ImageElement",
    "PDFAssemblerError",
]
