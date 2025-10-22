"""Minimal PNG parser used to embed PNG data in PDF files.

The parser focuses on RGB (true-color) PNG images with 8-bit channels and no
interlacing. This restriction keeps the implementation short and ensures the
resulting compressed data is directly consumable by a PDF `/FlateDecode`
stream when combined with the appropriate decode parameters (PNG uses the
same deflate compression).
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Dict

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass
class ParsedPNG:
    width: int
    height: int
    bit_depth: int
    color_type: int
    compressed_data: bytes
    decode_parms: Dict[str, int]


class PNGFormatError(ValueError):
    """Raised when an unsupported PNG is supplied."""


def parse_png(data: bytes) -> ParsedPNG:
    """Parse PNG bytes and return the metadata required for PDF embedding.

    Only true-colour (RGB) PNG files with 8-bit depth, no interlacing, and the
    default compression/filter settings are supported. The compressed IDAT data
    is returned as-is because the PDF stream can reuse the deflated bytes with
    the correct predictor parameters.
    """

    if not data.startswith(PNG_SIGNATURE):
        raise PNGFormatError("File is not a valid PNG image")

    offset = len(PNG_SIGNATURE)
    width = height = bit_depth = color_type = None
    compressed_chunks: list[bytes] = []

    while offset < len(data):
        if offset + 8 > len(data):
            raise PNGFormatError("Unexpected end of PNG data")
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        offset += 4
        chunk_type = data[offset : offset + 4]
        offset += 4
        chunk_data = data[offset : offset + length]
        offset += length
        # skip CRC (4 bytes)
        offset += 4

        if chunk_type == b"IHDR":
            if length != 13:
                raise PNGFormatError("Invalid IHDR chunk length")
            width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
                ">IIBBBBB", chunk_data
            )
            if compression != 0 or filter_method != 0:
                raise PNGFormatError("Unsupported PNG compression or filter method")
            if interlace != 0:
                raise PNGFormatError("Interlaced PNG images are not supported")
            if bit_depth != 8:
                raise PNGFormatError("Only 8-bit PNG images are supported")
            if color_type != 2:
                raise PNGFormatError("Only RGB PNG images are supported")
        elif chunk_type == b"IDAT":
            compressed_chunks.append(chunk_data)
        elif chunk_type == b"IEND":
            break
        else:
            # ignore ancillary chunks
            continue

    if width is None or height is None:
        raise PNGFormatError("Missing IHDR chunk in PNG data")

    compressed_data = b"".join(compressed_chunks)
    if not compressed_data:
        raise PNGFormatError("PNG file has no image data")

    decode_parms = {
        "Predictor": 15,
        "Colors": 3,
        "BitsPerComponent": 8,
        "Columns": width,
    }

    return ParsedPNG(
        width=width,
        height=height,
        bit_depth=bit_depth,
        color_type=color_type,
        compressed_data=compressed_data,
        decode_parms=decode_parms,
    )


__all__ = ["ParsedPNG", "PNGFormatError", "parse_png"]
