from __future__ import annotations

from pathlib import Path

import pytest

from pdfassembler import EditablePDF, TextElement, ImageElement


def make_rgb_data(width: int, height: int) -> bytes:
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            r = int(255 * (x / max(1, width - 1)))
            g = int(255 * (y / max(1, height - 1)))
            b = 128
            pixels.extend((r, g, b))
    return bytes(pixels)


def test_blank_document_add_and_edit(tmp_path: Path):
    pdf = EditablePDF.blank(width=400, height=400)
    page = pdf.pages[0]
    text_element = page.add_text("Hello pdfassembler", 50, 120, font_size=24)
    assert isinstance(text_element, TextElement)
    image_data = make_rgb_data(3, 3)
    image_element = page.add_image("Im1", image_data, width=90, height=90)
    assert isinstance(image_element, ImageElement)

    output_path = tmp_path / "assembled.pdf"
    pdf.save(str(output_path))
    assert output_path.exists()

    reloaded = EditablePDF.load(str(output_path))
    assert len(reloaded.pages) == 1
    loaded_page = reloaded.pages[0]
    assert any(isinstance(el, TextElement) for el in loaded_page.elements)
    assert any(isinstance(el, ImageElement) for el in loaded_page.elements)

    payload = {
        "pages": [
            {
                "page_index": 0,
                "elements": [
                    {
                        "id": loaded_page.elements[0].element_id,
                        "type": "text",
                        "x": 100,
                        "y": 140,
                        "order": 0,
                        "text": "Edited text",
                        "fontSize": 26,
                        "width": 150,
                        "height": 32,
                    }
                ],
            }
        ]
    }

    reloaded.apply_updates(payload)
    new_output = tmp_path / "assembled-updated.pdf"
    reloaded.save(str(new_output))
    assert new_output.exists()

    roundtrip = EditablePDF.load(str(new_output))
    text_elements = [el for el in roundtrip.pages[0].elements if isinstance(el, TextElement)]
    assert text_elements[0].text == "Edited text"
    assert text_elements[0].font_size == pytest.approx(26)


def test_apply_updates_moves_image(tmp_path: Path):
    pdf = EditablePDF.blank(width=300, height=300)
    page = pdf.pages[0]
    page.add_text("Baseline", 30, 60, font_size=18)
    image = page.add_image("Im2", make_rgb_data(4, 4), width=80, height=80)
    pdf_path = tmp_path / "image.pdf"
    pdf.save(str(pdf_path))

    loaded = EditablePDF.load(str(pdf_path))
    img = next(el for el in loaded.pages[0].elements if isinstance(el, ImageElement))
    initial_position = img.top_left()

    payload = {
        "pages": [
            {
                "page_index": 0,
                "elements": [
                    {
                        "id": img.element_id,
                        "type": "image",
                        "x": initial_position[0] + 40,
                        "y": initial_position[1] + 20,
                        "width": img.display_width(),
                        "height": img.display_height(),
                        "order": img.order + 1,
                    }
                ],
            }
        ]
    }

    loaded.apply_updates(payload)
    updated_path = tmp_path / "image-updated.pdf"
    loaded.save(str(updated_path))
    assert updated_path.exists()

    validate = EditablePDF.load(str(updated_path))
    moved = next(el for el in validate.pages[0].elements if isinstance(el, ImageElement))
    assert moved.top_left()[0] == pytest.approx(initial_position[0] + 40, abs=0.5)
    assert moved.top_left()[1] == pytest.approx(initial_position[1] + 20, abs=0.5)
