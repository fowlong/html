"""PDF serialization primitives used by the pdfassembler library."""

from __future__ import annotations

from io import BytesIO
from typing import Dict, List, Tuple

from .document import PDFDocument, PDFImageItem, PDFPage, PDFTextItem
from .png import parse_png


def build_pdf(document: PDFDocument, metadata_json: bytes) -> bytes:
    """Serialize *document* to a minimal but standards-compliant PDF."""

    objects: List[bytes | None] = []

    def add_object(body: bytes | str | None) -> int:
        objects.append(body if isinstance(body, (bytes, type(None))) else body.encode("latin-1"))
        return len(objects)

    def set_object(obj_num: int, body: bytes | str) -> None:
        objects[obj_num - 1] = body.encode("latin-1") if isinstance(body, str) else body

    # Built-in Helvetica font
    font_obj = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    # Reserve place for the /Pages node (parent of page objects)
    pages_obj = add_object(None)

    image_object_numbers: Dict[str, int] = {}
    page_object_numbers: List[int] = []

    for page in document.pages:
        page_image_names: Dict[str, str] = {}
        content_stream = _build_content_stream(page, font_resource="F1", image_names=page_image_names)

        # Ensure image objects exist before the page references them.
        for image in page.images:
            if image.id not in image_object_numbers:
                image_obj_num = add_object(_build_image_object(image))
                image_object_numbers[image.id] = image_obj_num

        content_obj = add_object(_stream(content_stream))
        resources = _build_resources(font_obj, image_object_numbers, page_image_names)
        page_obj_body = _build_page_object(page, pages_obj, content_obj, resources)
        page_obj_num = add_object(page_obj_body)
        page_object_numbers.append(page_obj_num)

    set_object(pages_obj, _build_pages_object(page_object_numbers))
    catalog_obj = add_object(f"<< /Type /Catalog /Pages {pages_obj} 0 R >>")

    if any(body is None for body in objects):  # pragma: no cover - defensive branch
        raise RuntimeError("Internal error: unresolved PDF objects")

    return _build_pdf_binary(objects, catalog_obj, metadata_json)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_resources(font_obj: int, image_objects: Dict[str, int], page_image_names: Dict[str, str]) -> bytes:
    parts = [f"/Font << /F1 {font_obj} 0 R >>"]
    if page_image_names:
        xobject_entries = " ".join(
            f"/{name} {image_objects[image_id]} 0 R" for image_id, name in page_image_names.items()
        )
        parts.append(f"/XObject << {xobject_entries} >>")
    inner = " ".join(parts)
    return f"<< {inner} >>".encode("latin-1")


def _build_content_stream(page: PDFPage, font_resource: str, image_names: Dict[str, str]) -> bytes:
    lines: List[bytes] = []

    for text in page.texts:
        lines.extend(_text_to_pdf_lines(text, font_resource))

    image_counter = 1
    for image in page.images:
        if image.id not in image_names:
            image_names[image.id] = f"Im{image_counter}"
            image_counter += 1
        resource_name = image_names[image.id]
        lines.extend(_image_to_pdf_lines(image, resource_name))

    return b"\n".join(lines) + b"\n"


def _text_to_pdf_lines(text: PDFTextItem, font_resource: str) -> List[bytes]:
    escaped = text.content.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    r, g, b = _hex_to_rgb(text.fill)
    return [
        b"BT",
        f"/{font_resource} {text.font_size:.2f} Tf".encode("latin-1"),
        f"{r:.3f} {g:.3f} {b:.3f} rg".encode("latin-1"),
        f"1 0 0 1 {text.x:.2f} {text.y:.2f} Tm".encode("latin-1"),
        f"({escaped}) Tj".encode("latin-1"),
        b"ET",
    ]


def _image_to_pdf_lines(image: PDFImageItem, resource_name: str) -> List[bytes]:
    return [
        b"q",
        f"{image.width:.2f} 0 0 {image.height:.2f} {image.x:.2f} {image.y:.2f} cm".encode("latin-1"),
        f"/{resource_name} Do".encode("latin-1"),
        b"Q",
    ]


def _build_image_object(image: PDFImageItem) -> bytes:
    parsed = parse_png(image.data)
    entries = {
        "Type": "/XObject",
        "Subtype": "/Image",
        "Width": str(parsed.width),
        "Height": str(parsed.height),
        "ColorSpace": "/DeviceRGB",
        "BitsPerComponent": str(parsed.bit_depth),
        "Filter": "/FlateDecode",
        "Length": str(len(parsed.compressed_data)),
    }
    if parsed.decode_parms:
        decode_entries = " ".join(f"/{key} {value}" for key, value in parsed.decode_parms.items())
        entries["DecodeParms"] = f"<< {decode_entries} >>"
    dict_content = " ".join(f"/{key} {value}" for key, value in entries.items())
    header = f"<< {dict_content} >>\nstream\n".encode("latin-1")
    return header + parsed.compressed_data + b"\nendstream"


def _build_page_object(page: PDFPage, pages_obj: int, content_obj: int, resources: bytes) -> bytes:
    mediabox = f"[0 0 {page.width:.2f} {page.height:.2f}]"
    body = f"<< /Type /Page /Parent {pages_obj} 0 R /MediaBox {mediabox} /Resources {resources.decode('latin-1')} /Contents {content_obj} 0 R >>"
    return body.encode("latin-1")


def _build_pages_object(page_object_numbers: List[int]) -> bytes:
    kids = " ".join(f"{num} 0 R" for num in page_object_numbers) or ""
    return f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_numbers)} >>".encode("latin-1")


def _stream(content: bytes) -> bytes:
    return f"<< /Length {len(content)} >>\nstream\n".encode("latin-1") + content + b"endstream"


def _hex_to_rgb(color: str) -> Tuple[float, float, float]:
    color = color.lstrip("#")
    if len(color) != 6:
        return 0.0, 0.0, 0.0
    r = int(color[0:2], 16) / 255.0
    g = int(color[2:4], 16) / 255.0
    b = int(color[4:6], 16) / 255.0
    return r, g, b


def _build_pdf_binary(objects: List[bytes | None], catalog_obj: int, metadata_json: bytes) -> bytes:
    buffer = BytesIO()
    buffer.write(b"%PDF-1.7\n%\xE2\xE3\xCF\xD3\n")

    offsets: List[int] = []
    for index, body in enumerate(objects, start=1):
        if body is None:
            raise RuntimeError(f"PDF object {index} was left undefined")
        offsets.append(buffer.tell())
        buffer.write(f"{index} 0 obj\n".encode("latin-1"))
        buffer.write(body)
        if not body.endswith(b"\n"):
            buffer.write(b"\n")
        buffer.write(b"endobj\n")

    xref_offset = buffer.tell()
    buffer.write(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    buffer.write(b"0000000000 65535 f \n")
    for offset in offsets:
        buffer.write(f"{offset:010d} 00000 n \n".encode("latin-1"))
    buffer.write(b"trailer\n")
    buffer.write(f"<< /Size {len(objects) + 1} /Root {catalog_obj} 0 R >>\n".encode("latin-1"))
    buffer.write(b"startxref\n")
    buffer.write(f"{xref_offset}\n".encode("latin-1"))
    buffer.write(b"%%PDFAssembler:" + metadata_json + b"\n")
    buffer.write(b"%%EOF\n")
    return buffer.getvalue()


__all__ = ["build_pdf"]
