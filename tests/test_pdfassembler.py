from __future__ import annotations

import base64
from pathlib import Path

from pdfassembler import load_pdf, new_document
from pdfassembler.document import PDFDocument

SAMPLE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


def test_round_trip_pdf(tmp_path: Path) -> None:
    document = new_document()
    text_item = document.add_text(0, "Hello World", x=100, y=150, font_size=16)
    image_item = document.add_image_from_bytes(0, SAMPLE_PNG, x=120, y=250)

    output = tmp_path / "roundtrip.pdf"
    document.save(output)

    data = output.read_bytes()
    assert data.startswith(b"%PDF-1.7")
    assert b"%%PDFAssembler:" in data

    loaded = load_pdf(output)
    assert isinstance(loaded, PDFDocument)
    assert len(loaded.pages) == 1
    page = loaded.pages[0]
    assert len(page.texts) == 1
    assert len(page.images) == 1
    assert page.texts[0].content == "Hello World"
    assert page.images[0].pixel_width == 1

    loaded.move_item(text_item.id, 180, 200)
    loaded.move_item(image_item.id, 200, 300)

    second_output = tmp_path / "roundtrip_updated.pdf"
    loaded.save(second_output)
    reload = load_pdf(second_output)
    updated_text = reload.find_text(text_item.id)
    assert updated_text is not None
    assert updated_text.x == 180
    assert updated_text.y == 200


def test_load_pdf_without_metadata(tmp_path: Path) -> None:
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    try:
        load_pdf(fake_pdf)
    except ValueError as exc:
        assert "metadata" in str(exc)
    else:  # pragma: no cover - defensive branch
        raise AssertionError("ValueError was not raised for missing metadata")
