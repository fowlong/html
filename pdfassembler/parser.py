"""Lightweight PDF parsing helpers for the custom pdfassembler module."""

from __future__ import annotations

import io
import re
from typing import Dict, Tuple

from .primitives import PDFName, PDFObject, PDFReference, PDFStream
from .tokenizer import PDFHexString, PDFString, TokenStream, tokenize


class PDFSyntaxError(RuntimeError):
    """Raised when the simplistic parser encounters malformed input."""


def _parse_value(tokens: TokenStream):
    token = tokens.pop()
    if token == "<<":
        result: Dict[str, object] = {}
        while tokens.peek() != ">>":
            key = tokens.pop()
            if not isinstance(key, PDFName):
                raise PDFSyntaxError("Expected PDF name inside dictionary")
            result[key.value] = _parse_value(tokens)
        tokens.pop()  # consume '>>'
        return result
    if token == "[":
        items = []
        while tokens.peek() != "]":
            items.append(_parse_value(tokens))
        tokens.pop()
        return items
    if isinstance(token, PDFString):
        return token.value
    if isinstance(token, PDFHexString):
        return token.value
    if isinstance(token, PDFName):
        return token
    if isinstance(token, (int, float)):
        next_token = tokens.peek()
        next_next = tokens.peek_n(1)
        if (
            isinstance(token, int)
            and isinstance(next_token, int)
            and next_next == "R"
        ):
            obj_id = token
            generation = tokens.pop()
            tokens.pop()  # consume 'R'
            return PDFReference(obj_id, generation)
        return token
    if token in {"true", "false"}:
        return token == "true"
    if token == "null":
        return None
    return token


def _parse_object_body(body: bytes):
    tokens = TokenStream(tokenize(body))
    return _parse_value(tokens)


_OBJECT_RE = re.compile(rb"(\d+)\s+(\d+)\s+obj(.*?)endobj", re.S)
_TRAILER_RE = re.compile(rb"trailer\s*(<<.*?>>)", re.S)
_STARTXREF_RE = re.compile(rb"startxref\s*(\d+)", re.S)


def parse_pdf(data: bytes) -> Tuple[Dict[int, PDFObject], dict]:
    objects: Dict[int, PDFObject] = {}
    for match in _OBJECT_RE.finditer(data):
        obj_id = int(match.group(1))
        generation = int(match.group(2))
        body = match.group(3).strip()
        stream_value = None
        if b"stream" in body:
            head, stream_chunk = body.split(b"stream", 1)
            if b"endstream" not in stream_chunk:
                raise PDFSyntaxError("Stream without endstream")
            stream_data, tail = stream_chunk.split(b"endstream", 1)
            stream_dict = _parse_object_body(head.strip())
            stream_bytes = stream_data.strip(b"\r\n")
            stream_value = PDFStream(stream_dict, stream_bytes)
            body_value = stream_dict
        else:
            body_value = _parse_object_body(body)
        objects[obj_id] = PDFObject(obj_id, generation, body_value, stream_value)

    trailer_match = _TRAILER_RE.search(data)
    if not trailer_match:
        raise PDFSyntaxError("Trailer dictionary missing")
    trailer_dict = _parse_object_body(trailer_match.group(1))

    startxref_match = _STARTXREF_RE.search(data)
    startxref = int(startxref_match.group(1)) if startxref_match else 0
    trailer_dict.setdefault("StartXref", startxref)

    return objects, trailer_dict


def parse_pdf_from_file(path: str) -> Tuple[Dict[int, PDFObject], dict]:
    with open(path, "rb") as handle:
        data = handle.read()
    return parse_pdf(data)
