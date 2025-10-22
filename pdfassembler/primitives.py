"""Core PDF primitive data structures used by the local pdfassembler module.

These classes mimic a very small subset of what a traditional PDF library
would provide.  They are intentionally lightweight so the module can operate
without third-party dependencies while still exposing a friendly object model
for the GUI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PDFName:
    """Represents a PDF name object (e.g. ``/Page``).

    The value is stored without the leading slash to make it easier to work
    with inside Python code.  ``str(name)`` reintroduces the slash when
    serialising.
    """

    value: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"/{self.value}"

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"PDFName({self.value!r})"


@dataclass(frozen=True)
class PDFReference:
    """Object reference (``12 0 R``)."""

    obj_id: int
    generation: int = 0

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"PDFReference({self.obj_id}, {self.generation})"


@dataclass
class PDFStream:
    """Holds a PDF stream dictionary and the associated bytes."""

    dictionary: Any
    data: bytes


@dataclass
class PDFObject:
    """Wrapper around parsed PDF objects.

    Attributes
    ----------
    obj_id:
        Integer identifier of the object.
    generation:
        Generation number (almost always ``0`` for files we create).
    value:
        Parsed Python representation of the object.  This can be a dictionary,
        list, name, number, etc.
    stream:
        Optional :class:`PDFStream` representing the stream data associated
        with the object.
    """

    obj_id: int
    generation: int
    value: Any
    stream: PDFStream | None = None

    def clone_with(self, *, value: Any | None = None, stream: PDFStream | None = None) -> "PDFObject":
        """Return a shallow copy with the provided overrides."""

        return PDFObject(
            obj_id=self.obj_id,
            generation=self.generation,
            value=self.value if value is None else value,
            stream=self.stream if stream is None else stream,
        )
