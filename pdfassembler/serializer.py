"""Helpers for serialising Python structures back into PDF syntax."""

from __future__ import annotations

import io
from typing import Iterable

from .primitives import PDFName, PDFObject, PDFReference, PDFStream


def _escape_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )


def serialize(value) -> bytes:
    if isinstance(value, PDFName):
        return str(value).encode("latin-1")
    if isinstance(value, PDFReference):
        return f"{value.obj_id} {value.generation} R".encode("ascii")
    if isinstance(value, bool):
        return b"true" if value else b"false"
    if value is None:
        return b"null"
    if isinstance(value, (int, float)):
        if isinstance(value, float):
            text = ("%.6f" % value).rstrip("0").rstrip(".")
        else:
            text = str(value)
        return text.encode("ascii")
    if isinstance(value, str):
        return f"({_escape_text(value)})".encode("latin-1")
    if isinstance(value, bytes):
        return b"<" + value.hex().encode("ascii") + b">"
    if isinstance(value, dict):
        parts = [b"<<"]
        for key, item in value.items():
            if isinstance(key, PDFName):
                key_bytes = serialize(key)
            elif isinstance(key, str):
                key_bytes = serialize(PDFName(key))
            else:  # pragma: no cover - defensive
                raise TypeError(f"Unsupported key type: {type(key)!r}")
            parts.append(key_bytes + b" ")
            parts.append(serialize(item))
            parts.append(b"\n")
        parts.append(b">>")
        return b"".join(parts)
    if isinstance(value, (list, tuple)):
        items = b" ".join(serialize(item) for item in value)
        return b"[" + items + b"]"
    raise TypeError(f"Unsupported value type: {type(value)!r}")


def write_pdf(objects: Iterable[PDFObject], trailer: dict) -> bytes:
    buffer = io.BytesIO()
    buffer.write(b"%PDF-1.4\n")
    sorted_objects = sorted(objects, key=lambda obj: obj.obj_id)
    offsets = {}
    for obj in sorted_objects:
        offsets[obj.obj_id] = buffer.tell()
        buffer.write(f"{obj.obj_id} {obj.generation} obj\n".encode("ascii"))
        value_bytes = serialize(obj.value)
        buffer.write(value_bytes)
        if obj.stream is not None:
            stream_data = obj.stream.data
            length = len(stream_data)
            if isinstance(obj.value, dict):
                obj.value["Length"] = length
            buffer.write(b"\nstream\n")
            buffer.write(stream_data)
            buffer.write(b"\nendstream")
        buffer.write(b"\nendobj\n")
    xref_position = buffer.tell()
    count = len(sorted_objects) + 1
    buffer.write(f"xref\n0 {count}\n".encode("ascii"))
    buffer.write(b"0000000000 65535 f \n")
    for obj in sorted_objects:
        offset = offsets[obj.obj_id]
        buffer.write(f"{offset:010d} 00000 n \n".encode("ascii"))
    trailer_dict = dict(trailer)
    trailer_dict["Size"] = count
    buffer.write(b"trailer\n")
    buffer.write(serialize(trailer_dict))
    buffer.write(b"\nstartxref\n")
    buffer.write(str(xref_position).encode("ascii") + b"\n%%EOF")
    return buffer.getvalue()


def write_pdf_to_file(objects: Iterable[PDFObject], trailer: dict, path: str) -> None:
    data = write_pdf(objects, trailer)
    with open(path, "wb") as handle:
        handle.write(data)
