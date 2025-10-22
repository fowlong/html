"""In-memory PDF object model and editing helpers."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .png import PNGFormatError, parse_png


@dataclass
class PDFTextItem:
    id: str
    content: str
    x: float
    y: float
    font_size: float = 12.0
    font_name: str = "Helvetica"
    fill: str = "#000000"

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "content": self.content,
            "x": self.x,
            "y": self.y,
            "font_size": self.font_size,
            "font_name": self.font_name,
            "fill": self.fill,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "PDFTextItem":
        return cls(
            id=str(data["id"]),
            content=str(data.get("content", "")),
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            font_size=float(data.get("font_size", 12.0)),
            font_name=str(data.get("font_name", "Helvetica")),
            fill=str(data.get("fill", "#000000")),
        )


@dataclass
class PDFImageItem:
    id: str
    data: bytes
    x: float
    y: float
    width: float
    height: float
    pixel_width: int
    pixel_height: int
    mime_type: str = "image/png"
    decode_parms: Optional[Dict[str, int]] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "data": base64.b64encode(self.data).decode("ascii"),
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "pixel_width": self.pixel_width,
            "pixel_height": self.pixel_height,
            "mime_type": self.mime_type,
            "decode_parms": self.decode_parms or {},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "PDFImageItem":
        raw = base64.b64decode(str(data["data"]))
        parsed = parse_png(raw)
        return cls(
            id=str(data["id"]),
            data=raw,
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            width=float(data.get("width", parsed.width)),
            height=float(data.get("height", parsed.height)),
            pixel_width=int(data.get("pixel_width", parsed.width)),
            pixel_height=int(data.get("pixel_height", parsed.height)),
            mime_type=str(data.get("mime_type", "image/png")),
            decode_parms={k: int(v) for k, v in dict(data.get("decode_parms", {})).items()},
        )


@dataclass
class PDFPage:
    number: int
    width: float
    height: float
    texts: List[PDFTextItem] = field(default_factory=list)
    images: List[PDFImageItem] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "number": self.number,
            "width": self.width,
            "height": self.height,
            "texts": [text.to_dict() for text in self.texts],
            "images": [image.to_dict() for image in self.images],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "PDFPage":
        page = cls(
            number=int(data.get("number", 0)),
            width=float(data.get("width", 595.0)),
            height=float(data.get("height", 842.0)),
        )
        page.texts = [PDFTextItem.from_dict(item) for item in data.get("texts", [])]
        page.images = [PDFImageItem.from_dict(item) for item in data.get("images", [])]
        return page

    def find_text(self, item_id: str) -> Optional[PDFTextItem]:
        return next((item for item in self.texts if item.id == item_id), None)

    def find_image(self, item_id: str) -> Optional[PDFImageItem]:
        return next((item for item in self.images if item.id == item_id), None)


class PDFDocument:
    """Editable PDF document abstraction."""

    def __init__(self, pages: List[PDFPage], next_id: int = 1, metadata: Optional[Dict[str, object]] = None):
        self.pages = pages
        self._next_id = next_id
        self.metadata = metadata or {}

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------
    @classmethod
    def new(cls, page_width: float = 595.0, page_height: float = 842.0, pages: int = 1) -> "PDFDocument":
        page_list = [
            PDFPage(number=index + 1, width=page_width, height=page_height)
            for index in range(pages)
        ]
        return cls(page_list, next_id=1, metadata={"generator": "pdfassembler"})

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "PDFDocument":
        pages = [PDFPage.from_dict(page) for page in data.get("pages", [])]
        next_id = int(data.get("next_id", len(pages) + 1))
        metadata = dict(data.get("metadata", {}))
        return cls(pages=pages, next_id=next_id, metadata=metadata)

    def to_dict(self) -> Dict[str, object]:
        return {
            "pages": [page.to_dict() for page in self.pages],
            "next_id": self._next_id,
            "metadata": self.metadata,
        }

    # ------------------------------------------------------------------
    # Object manipulation
    # ------------------------------------------------------------------
    def _allocate_id(self) -> str:
        ident = f"obj{self._next_id}"
        self._next_id += 1
        return ident

    def add_text(
        self,
        page_index: int,
        content: str,
        x: float,
        y: float,
        font_size: float = 12.0,
        font_name: str = "Helvetica",
        fill: str = "#000000",
    ) -> PDFTextItem:
        page = self.pages[page_index]
        item = PDFTextItem(
            id=self._allocate_id(),
            content=content,
            x=x,
            y=y,
            font_size=font_size,
            font_name=font_name,
            fill=fill,
        )
        page.texts.append(item)
        return item

    def add_image_from_bytes(
        self,
        page_index: int,
        data: bytes,
        x: float,
        y: float,
        width: Optional[float] = None,
        height: Optional[float] = None,
    ) -> PDFImageItem:
        try:
            parsed = parse_png(data)
        except PNGFormatError as exc:  # pragma: no cover - defensive branch
            raise ValueError(str(exc)) from exc

        display_width = float(width if width is not None else parsed.width)
        display_height = float(height if height is not None else parsed.height)

        page = self.pages[page_index]
        item = PDFImageItem(
            id=self._allocate_id(),
            data=data,
            x=x,
            y=y,
            width=display_width,
            height=display_height,
            pixel_width=parsed.width,
            pixel_height=parsed.height,
            mime_type="image/png",
            decode_parms=parsed.decode_parms,
        )
        page.images.append(item)
        return item

    def add_image_from_file(
        self,
        page_index: int,
        path: str,
        x: float,
        y: float,
        width: Optional[float] = None,
        height: Optional[float] = None,
    ) -> PDFImageItem:
        with open(path, "rb") as handle:
            data = handle.read()
        return self.add_image_from_bytes(page_index, data, x=x, y=y, width=width, height=height)

    def find_text(self, item_id: str) -> Optional[PDFTextItem]:
        for page in self.pages:
            match = page.find_text(item_id)
            if match:
                return match
        return None

    def find_image(self, item_id: str) -> Optional[PDFImageItem]:
        for page in self.pages:
            match = page.find_image(item_id)
            if match:
                return match
        return None

    def move_item(self, item_id: str, new_x: float, new_y: float) -> None:
        for page in self.pages:
            match = page.find_text(item_id)
            if match:
                match.x = float(new_x)
                match.y = float(new_y)
                return
            match_img = page.find_image(item_id)
            if match_img:
                match_img.x = float(new_x)
                match_img.y = float(new_y)
                return
        raise KeyError(f"Item '{item_id}' not found")

    def remove_item(self, item_id: str) -> None:
        for page in self.pages:
            for collection in (page.texts, page.images):
                for index, item in enumerate(collection):
                    if item.id == item_id:
                        del collection[index]
                        return
        raise KeyError(f"Item '{item_id}' not found")

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save(self, path: str) -> None:
        from .storage import save_pdf

        save_pdf(self, path)


def new_document(page_width: float = 595.0, page_height: float = 842.0, pages: int = 1) -> PDFDocument:
    return PDFDocument.new(page_width=page_width, page_height=page_height, pages=pages)


__all__ = [
    "PDFDocument",
    "PDFImageItem",
    "PDFPage",
    "PDFTextItem",
    "new_document",
]
