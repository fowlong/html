"""High level editable PDF object model used by the GUI and tests."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import struct
import zlib
import binascii
from typing import Dict, List, Optional

from .parser import parse_pdf_from_file
from .primitives import PDFName, PDFObject, PDFReference, PDFStream
from .serializer import write_pdf_to_file
from .tokenizer import tokenize

def _format_number(value: float) -> str:
    if abs(value - int(value)) < 1e-6:
        return str(int(round(value)))
    text = f"{value:.4f}"
    return text.rstrip("0").rstrip(".")


def _png_chunk(tag: bytes, payload: bytes) -> bytes:
    return struct.pack("!I", len(payload)) + tag + payload + struct.pack(
        "!I", binascii.crc32(tag + payload) & 0xFFFFFFFF
    )


def _flate_to_png(width: int, height: int, compressed: bytes) -> bytes:
    raw = zlib.decompress(compressed)
    expected = width * height * 3
    if len(raw) != expected:
        raise ValueError("Unexpected image data length")
    rows = []
    row_bytes = width * 3
    for row_index in range(height):
        start = row_index * row_bytes
        rows.append(b"\x00" + raw[start : start + row_bytes])
    pixel_data = b"".join(rows)
    encoded = zlib.compress(pixel_data)
    header = struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0)
    signature = b"\x89PNG\r\n\x1a\n"
    return signature + _png_chunk(b"IHDR", header) + _png_chunk(b"IDAT", encoded) + _png_chunk(b"IEND", b"")


class PDFAssemblerError(RuntimeError):
    pass


@dataclass
class PageElement:
    page: "EditablePage"
    element_id: str
    matrix: List[float]
    order: int

    def display_height(self) -> float:
        raise NotImplementedError

    def display_width(self) -> float:
        raise NotImplementedError

    def top_left(self) -> tuple[float, float]:
        x = self.matrix[4]
        y_bottom = self.matrix[5]
        return x, self.page.height - (y_bottom + self.display_height())

    def set_top_left(self, x: float, y: float) -> None:
        self.matrix[4] = float(x)
        self.matrix[5] = float(self.page.height - y - self.display_height())

    def to_pdf_chunks(self) -> List[str]:
        raise NotImplementedError

    def to_json(self) -> dict:
        raise NotImplementedError


@dataclass
class TextElement(PageElement):
    text: str
    font_name: str
    font_size: float

    def display_height(self) -> float:
        return abs(self.font_size)

    def display_width(self) -> float:
        return max(self.font_size * 0.6 * len(self.text or " "), self.font_size * 0.6)

    def set_text(self, value: str) -> None:
        self.text = value

    def to_pdf_chunks(self) -> List[str]:
        matrix_values = " ".join(_format_number(v) for v in self.matrix)
        escaped = (
            self.text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        )
        return [
            "BT",
            f"/{self.font_name} {_format_number(self.font_size)} Tf",
            f"{matrix_values} Tm",
            f"({escaped}) Tj",
            "ET",
        ]

    def to_json(self) -> dict:
        x, y = self.top_left()
        return {
            "id": self.element_id,
            "type": "text",
            "text": self.text,
            "font": self.font_name,
            "fontSize": self.font_size,
            "x": x,
            "y": y,
            "width": self.display_width(),
            "height": self.display_height(),
            "order": self.order,
        }


@dataclass
class ImageElement(PageElement):
    name: str
    xobject_ref: PDFReference
    width: float
    height: float
    raw_data: bytes
    color_space: str = "DeviceRGB"
    filter_name: str | None = None

    def display_height(self) -> float:
        return abs(self.height)

    def display_width(self) -> float:
        return abs(self.width)

    def to_pdf_chunks(self) -> List[str]:
        matrix_values = " ".join(_format_number(v) for v in self.matrix)
        return [
            "q",
            f"{matrix_values} cm",
            f"/{self.name} Do",
            "Q",
        ]

    def to_json(self) -> dict:
        x, y = self.top_left()
        mime = "application/octet-stream"
        binary = self.raw_data
        if self.filter_name == "DCTDecode":
            mime = "image/jpeg"
        elif self.filter_name == "FlateDecode":
            try:
                binary = _flate_to_png(int(self.width), int(self.height), self.raw_data)
                mime = "image/png"
            except Exception:  # pragma: no cover - defensive fallback
                binary = self.raw_data
        elif self.filter_name == "JPXDecode":
            mime = "image/jp2"
        data_url = f"data:{mime};base64,{base64.b64encode(binary).decode('ascii')}"
        return {
            "id": self.element_id,
            "type": "image",
            "name": self.name,
            "x": x,
            "y": y,
            "width": self.display_width(),
            "height": self.display_height(),
            "order": self.order,
            "src": data_url,
        }


@dataclass
class EditablePage:
    pdf: "EditablePDF"
    index: int
    obj: PDFObject
    contents: List[PDFObject]
    height: float
    width: float
    elements: List[PageElement] = field(default_factory=list)

    def _ensure_font(self) -> tuple[str, PDFReference]:
        resources = self.obj.value.setdefault("Resources", {})
        fonts = resources.setdefault("Font", {})
        existing = list(fonts.items())
        if existing:
            name, ref = existing[0]
            if isinstance(name, PDFName):
                return name.value, ref
            return name, ref
        font_name = f"F{len(fonts) + 1}"
        font_obj = self.pdf._create_font_object("Helvetica")
        fonts[font_name] = PDFReference(font_obj.obj_id, font_obj.generation)
        return font_name, fonts[font_name]

    def add_text(self, text: str, x: float, y: float, font_size: float = 18.0) -> TextElement:
        font_name, font_ref = self._ensure_font()
        matrix = [font_size, 0.0, 0.0, font_size, x, self.height - y - font_size]
        element_id = self.pdf.generate_element_id(self.index)
        element = TextElement(
            page=self,
            element_id=element_id,
            matrix=matrix,
            order=len(self.elements),
            text=text,
            font_name=font_name,
            font_size=font_size,
        )
        self.elements.append(element)
        return element

    def add_image(self, name: str, data: bytes, width: float, height: float) -> ImageElement:
        xobject_ref, filter_name = self.pdf._create_image_object(name, data, width, height)
        matrix = [width, 0.0, 0.0, height, 0.0, 0.0]
        element_id = self.pdf.generate_element_id(self.index)
        element = ImageElement(
            page=self,
            element_id=element_id,
            matrix=matrix,
            order=len(self.elements),
            name=name,
            xobject_ref=xobject_ref,
            width=width,
            height=height,
            raw_data=self.pdf.objects[xobject_ref.obj_id].stream.data,
            filter_name=filter_name,
        )
        self.elements.append(element)
        resources = self.obj.value.setdefault("Resources", {})
        xobjects = resources.setdefault("XObject", {})
        xobjects[name] = xobject_ref
        return element

    def to_json(self) -> dict:
        return {
            "index": self.index,
            "width": self.width,
            "height": self.height,
            "elements": [element.to_json() for element in sorted(self.elements, key=lambda el: el.order)],
        }

    def rebuild_content_stream(self) -> None:
        if not self.contents:
            return
        ordered = sorted(self.elements, key=lambda el: el.order)
        chunks: List[str] = []
        for element in ordered:
            chunks.extend(element.to_pdf_chunks())
        content_data = "\n".join(chunks).encode("latin-1")
        target = self.contents[0]
        target.stream = PDFStream(target.value, content_data)
        target.value["Length"] = len(content_data)

    def apply_updates(self, updates: List[dict]) -> None:
        element_lookup = {element.element_id: element for element in self.elements}
        for payload in updates:
            element = element_lookup.get(payload["id"])
            if not element:
                continue
            element.order = int(payload.get("order", element.order))
            if payload.get("type") == "text" and isinstance(element, TextElement):
                if "text" in payload:
                    element.set_text(payload["text"])
            if "x" in payload and "y" in payload:
                element.set_top_left(float(payload["x"]), float(payload["y"]))
            if isinstance(element, ImageElement):
                if "width" in payload:
                    element.width = float(payload["width"])
                    element.matrix[0] = element.width
                if "height" in payload:
                    element.height = float(payload["height"])
                    element.matrix[3] = element.height
            if isinstance(element, TextElement):
                if "fontSize" in payload:
                    element.font_size = float(payload["fontSize"])
                    element.matrix[0] = element.font_size
                    element.matrix[3] = element.font_size


@dataclass
class EditablePDF:
    objects: Dict[int, PDFObject]
    trailer: dict
    path: Optional[str] = None
    pages: List[EditablePage] = field(default_factory=list)
    _element_counter: int = 0

    @classmethod
    def load(cls, path: str) -> "EditablePDF":
        objects, trailer = parse_pdf_from_file(path)
        instance = cls(objects=objects, trailer=trailer, path=path)
        instance._populate_pages()
        return instance

    @classmethod
    def blank(cls, width: float = 612.0, height: float = 792.0) -> "EditablePDF":
        objects: Dict[int, PDFObject] = {}
        next_id = 1

        def add_object(value, stream: PDFStream | None = None) -> PDFObject:
            nonlocal next_id
            obj = PDFObject(next_id, 0, value, stream)
            objects[next_id] = obj
            next_id += 1
            return obj

        pages_array: List[PDFReference] = []

        pages_dict = {"Type": PDFName("Pages"), "Count": 1, "Kids": pages_array}
        catalog = add_object({"Type": PDFName("Catalog"), "Pages": PDFReference(2)})
        pages_obj = add_object(pages_dict)
        media_box = [0, 0, width, height]
        page_stream = PDFStream({"Length": 0}, b"")
        content_obj = add_object(page_stream.dictionary, stream=page_stream)
        page_obj = add_object(
            {
                "Type": PDFName("Page"),
                "Parent": PDFReference(pages_obj.obj_id),
                "MediaBox": media_box,
                "Contents": PDFReference(content_obj.obj_id),
                "Resources": {},
            }
        )
        pages_array.append(PDFReference(page_obj.obj_id))
        trailer = {"Root": PDFReference(catalog.obj_id)}
        pdf = cls(objects=objects, trailer=trailer, path=None)
        pdf._populate_pages()
        return pdf

    def _populate_pages(self) -> None:
        self.pages.clear()
        catalog_ref = self.trailer.get("Root")
        if not isinstance(catalog_ref, PDFReference):
            raise PDFAssemblerError("Invalid PDF catalog reference")
        catalog = self.objects[catalog_ref.obj_id]
        pages_ref = catalog.value.get("Pages")
        if not isinstance(pages_ref, PDFReference):
            raise PDFAssemblerError("Catalog missing /Pages reference")
        pages_node = self.objects[pages_ref.obj_id]
        kids = pages_node.value.get("Kids", [])
        for index, kid in enumerate(kids):
            if not isinstance(kid, PDFReference):
                continue
            page_obj = self.objects[kid.obj_id]
            contents_value = page_obj.value.get("Contents")
            content_objects: List[PDFObject] = []
            if isinstance(contents_value, PDFReference):
                content_objects.append(self.objects[contents_value.obj_id])
            elif isinstance(contents_value, list):
                for ref in contents_value:
                    if isinstance(ref, PDFReference):
                        content_objects.append(self.objects[ref.obj_id])
            media_box = page_obj.value.get("MediaBox", [0, 0, 612, 792])
            width = float(media_box[2])
            height = float(media_box[3])
            page = EditablePage(
                pdf=self,
                index=index,
                obj=page_obj,
                contents=content_objects,
                width=width,
                height=height,
            )
            page.elements = self._parse_page_elements(page)
            self.pages.append(page)

    def _parse_page_elements(self, page: EditablePage) -> List[PageElement]:
        elements: List[PageElement] = []
        if not page.contents:
            return elements
        resources = page.obj.value.get("Resources", {})
        fonts = resources.get("Font", {})
        xobjects = resources.get("XObject", {})
        stream_data = b"\n".join(content.stream.data for content in page.contents if content.stream)
        tokens = tokenize(stream_data)
        operands: List = []
        order = 0
        current_font = ("F1", 12.0)
        text_matrix = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
        pending_cm: Optional[List[float]] = None
        for token in tokens:
            if isinstance(token, str) and token in {"BT", "ET", "Tf", "Tm", "Tj", "cm", "Do", "q", "Q"}:
                if token == "Tf":
                    if len(operands) >= 2:
                        font_name_token = operands[-2]
                        size = float(operands[-1])
                        if isinstance(font_name_token, PDFName):
                            current_font = (font_name_token.value, size)
                        else:
                            current_font = (str(font_name_token), size)
                    operands.clear()
                elif token == "Tm":
                    if len(operands) >= 6:
                        text_matrix = [float(v) for v in operands[-6:]]
                    operands.clear()
                elif token == "Tj":
                    if operands:
                        text_value = operands[-1]
                        if hasattr(text_value, "value"):
                            text_str = text_value.value
                        else:
                            text_str = str(text_value)
                        element_id = self.generate_element_id(page.index)
                        element = TextElement(
                            page=page,
                            element_id=element_id,
                            matrix=list(text_matrix),
                            order=order,
                            text=text_str,
                            font_name=current_font[0],
                            font_size=current_font[1],
                        )
                        elements.append(element)
                        order += 1
                    operands.clear()
                elif token == "cm":
                    if len(operands) >= 6:
                        pending_cm = [float(v) for v in operands[-6:]]
                    operands.clear()
                elif token == "Do":
                    if operands:
                        name_token = operands[-1]
                        if isinstance(name_token, PDFName):
                            name_value = name_token.value
                        else:
                            name_value = str(name_token)
                        ref = xobjects.get(name_value)
                        if isinstance(ref, PDFReference):
                            xobj = self.objects.get(ref.obj_id)
                        else:
                            xobj = None
                        if xobj and xobj.stream:
                            width = float(xobj.value.get("Width", pending_cm[0] if pending_cm else 0))
                            height = float(xobj.value.get("Height", pending_cm[3] if pending_cm else 0))
                            element_id = self.generate_element_id(page.index)
                            element = ImageElement(
                                page=page,
                                element_id=element_id,
                                matrix=list(pending_cm or [width, 0, 0, height, 0, 0]),
                                order=order,
                                name=name_value,
                                xobject_ref=ref if isinstance(ref, PDFReference) else PDFReference(xobj.obj_id),
                                width=width,
                                height=height,
                                raw_data=xobj.stream.data,
                                filter_name=(
                                    xobj.value.get("Filter").value
                                    if isinstance(xobj.value.get("Filter"), PDFName)
                                    else xobj.value.get("Filter")
                                ),
                            )
                            elements.append(element)
                            order += 1
                    operands.clear()
                else:
                    operands.clear()
            else:
                operands.append(token)
        return elements

    def generate_element_id(self, page_index: int) -> str:
        self._element_counter += 1
        return f"p{page_index}_el{self._element_counter}"

    def to_json(self) -> dict:
        return {"path": self.path, "pages": [page.to_json() for page in self.pages]}

    def apply_updates(self, payload: dict) -> None:
        for page_update in payload.get("pages", []):
            index = page_update.get("page_index")
            if index is None:
                continue
            if 0 <= index < len(self.pages):
                self.pages[index].apply_updates(page_update.get("elements", []))

    def save(self, path: Optional[str] = None) -> str:
        target = path or self.path
        if not target:
            raise PDFAssemblerError("No output path specified")
        for page in self.pages:
            page.rebuild_content_stream()
        write_pdf_to_file(self.objects.values(), self.trailer, target)
        self.path = target
        return target

    def _create_font_object(self, base_font: str) -> PDFObject:
        value = {"Type": PDFName("Font"), "Subtype": PDFName("Type1"), "BaseFont": PDFName(base_font)}
        new_id = max(self.objects) + 1 if self.objects else 1
        obj = PDFObject(new_id, 0, value)
        self.objects[new_id] = obj
        return obj

    def _create_image_object(
        self, name: str, data: bytes, width: float, height: float
    ) -> tuple[PDFReference, str]:
        new_id = max(self.objects) + 1 if self.objects else 1
        pixel_count = int(width) * int(height) * 3
        if len(data) == pixel_count:
            compressed = zlib.compress(data)
            filter_name = PDFName("FlateDecode")
        else:
            compressed = data
            filter_name = PDFName("DCTDecode")
        stream_dict = {
            "Type": PDFName("XObject"),
            "Subtype": PDFName("Image"),
            "Width": int(width),
            "Height": int(height),
            "ColorSpace": PDFName("DeviceRGB"),
            "BitsPerComponent": 8,
            "Filter": filter_name,
            "Length": len(compressed),
        }
        stream = PDFStream(stream_dict, compressed)
        obj = PDFObject(new_id, 0, stream_dict, stream=stream)
        self.objects[new_id] = obj
        return PDFReference(new_id), filter_name.value

    def document_summary(self) -> dict:
        summary = {"pages": []}
        for page in self.pages:
            summary["pages"].append(
                {
                    "index": page.index,
                    "elementCount": len(page.elements),
                    "textElements": sum(isinstance(el, TextElement) for el in page.elements),
                    "imageElements": sum(isinstance(el, ImageElement) for el in page.elements),
                }
            )
        return summary
