from __future__ import annotations

import base64

from pdfassembler.png import PNGFormatError, parse_png


SAMPLE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


def test_parse_png_metadata() -> None:
    parsed = parse_png(SAMPLE_PNG)
    assert parsed.width == 1
    assert parsed.height == 1
    assert parsed.bit_depth == 8
    assert parsed.color_type == 2
    assert parsed.compressed_data
    assert parsed.decode_parms["Columns"] == 1


def test_parse_png_rejects_non_png() -> None:
    try:
        parse_png(b"not png data")
    except PNGFormatError:
        pass
    else:  # pragma: no cover - defensive branch
        raise AssertionError("PNGFormatError was not raised")
