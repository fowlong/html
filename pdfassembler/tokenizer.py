"""A very small PDF tokenizer used by the custom pdfassembler implementation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator, List

from .primitives import PDFName

_WHITESPACE = b"\x00\t\n\r\f \v"
_DELIMITERS = b"()<>[]{}/%"


@dataclass
class PDFString:
    value: str

    def __str__(self) -> str:  # pragma: no cover
        return self.value


@dataclass
class PDFHexString:
    value: bytes


Token = str | float | int | PDFName | PDFString | PDFHexString


class TokenStream:
    """Helper that behaves like an iterator with peek support."""

    def __init__(self, tokens: List[Token]):
        self._tokens = tokens
        self._index = 0

    def __iter__(self) -> Iterator[Token]:  # pragma: no cover
        return self

    def __next__(self) -> Token:  # pragma: no cover
        if self._index >= len(self._tokens):
            raise StopIteration
        value = self._tokens[self._index]
        self._index += 1
        return value

    def peek(self) -> Token | None:
        if self._index >= len(self._tokens):
            return None
        return self._tokens[self._index]

    def pop(self) -> Token:
        value = self.peek()
        if value is None:
            raise ValueError("Unexpected end of token stream")
        self._index += 1
        return value

    def remaining(self) -> List[Token]:  # pragma: no cover
        return self._tokens[self._index :]

    def peek_n(self, offset: int) -> Token | None:
        index = self._index + offset
        if index < 0 or index >= len(self._tokens):
            return None
        return self._tokens[index]


def _parse_name(data: bytes, index: int) -> tuple[PDFName, int]:
    start = index + 1
    index = start
    while index < len(data):
        byte = data[index : index + 1]
        if byte in _WHITESPACE or byte in _DELIMITERS:
            break
        index += 1
    raw = data[start:index].decode("latin-1")
    raw = raw.replace("#", "#")
    return PDFName(raw), index


def _parse_number_or_keyword(data: bytes, index: int) -> tuple[Token, int]:
    start = index
    while index < len(data):
        byte = data[index : index + 1]
        if byte in _WHITESPACE or byte in _DELIMITERS:
            break
        index += 1
    token = data[start:index]
    if token in {b"true", b"false"}:
        return token.decode("ascii"), index
    if token == b"null":
        return "null", index
    if re.match(rb"^[+-]?\d+\.?\d*$", token):
        if b"." in token:
            return float(token), index
        return int(token), index
    return token.decode("latin-1"), index


def _parse_literal_string(data: bytes, index: int) -> tuple[PDFString, int]:
    index += 1  # skip opening '('
    depth = 1
    result = []
    while index < len(data) and depth > 0:
        byte = data[index:index+1]
        char = byte.decode("latin-1")
        if char == "\\":
            index += 1
            if index >= len(data):
                break
            char = data[index:index+1].decode("latin-1")
            if char == "n":
                result.append("\n")
            elif char == "r":
                result.append("\r")
            elif char == "t":
                result.append("\t")
            elif char == "b":
                result.append("\b")
            elif char == "f":
                result.append("\f")
            else:
                result.append(char)
        elif char == "(":
            depth += 1
            result.append(char)
        elif char == ")":
            depth -= 1
            if depth > 0:
                result.append(char)
        else:
            result.append(char)
        index += 1
    return PDFString("".join(result)), index


def _parse_hex_string(data: bytes, index: int) -> tuple[PDFHexString, int]:
    end = data.index(b">", index + 1)
    hex_data = data[index + 1:end]
    hex_data = hex_data.replace(b" ", b"")
    if len(hex_data) % 2:
        hex_data += b"0"
    return PDFHexString(bytes.fromhex(hex_data.decode("ascii"))), end + 1


def tokenize(data: bytes) -> List[Token]:
    tokens: List[Token] = []
    index = 0
    length = len(data)
    while index < length:
        byte = data[index:index+1]
        if not byte or byte in _WHITESPACE:
            index += 1
            continue
        if byte == b"%":
            while index < length and data[index:index+1] not in {b"\n", b"\r"}:
                index += 1
            continue
        if byte == b"/":
            name, index = _parse_name(data, index)
            tokens.append(name)
            continue
        if byte == b"(":
            string, index = _parse_literal_string(data, index)
            tokens.append(string)
            continue
        if byte == b"<":
            if data[index+1:index+2] == b"<":
                tokens.append("<<")
                index += 2
                continue
            hex_string, index = _parse_hex_string(data, index)
            tokens.append(hex_string)
            continue
        if byte == b">":
            if data[index+1:index+2] == b">":
                tokens.append(">>")
                index += 2
            else:
                index += 1
            continue
        if byte == b"[":
            tokens.append("[")
            index += 1
            continue
        if byte == b"]":
            tokens.append("]")
            index += 1
            continue
        token, index = _parse_number_or_keyword(data, index)
        tokens.append(token)
    return tokens
