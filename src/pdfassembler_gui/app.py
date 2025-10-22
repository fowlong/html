"""Tkinter GUI for the bundled pdfassembler library."""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter import font as tkfont

from pdfassembler import PDFDocument, PDFImageItem, PDFPage, PDFTextItem, load_pdf, new_document
from pdfassembler.png import parse_png


class PDFAssemblerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("PDF Assembler GUI")
        self.zoom = 1.0

        self.document: PDFDocument = new_document()
        self.current_path: Optional[Path] = None
        self.current_page_index: int = 0

        self.canvas_items: Dict[int, Tuple[str, str]] = {}
        self.object_to_canvas: Dict[str, int] = {}
        self.image_cache: Dict[str, tk.PhotoImage] = {}
        self.selection_indicator: Optional[int] = None
        self.selected_object_id: Optional[str] = None
        self.selected_kind: Optional[str] = None
        self.drag_state: Optional[Dict[str, object]] = None

        self.status_var = tk.StringVar(value="Ready")

        self._build_ui()
        self.render_page()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self._build_menu()
        self._build_toolbar()
        self._build_canvas()
        self._build_statusbar()

    def _build_menu(self) -> None:
        menu = tk.Menu(self.root)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="New", command=self.new_document)
        file_menu.add_command(label="Open…", command=self.open_document)
        file_menu.add_separator()
        file_menu.add_command(label="Save", command=self.save_document)
        file_menu.add_command(label="Save As…", command=self.save_document_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menu.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(menu, tearoff=False)
        edit_menu.add_command(label="Add Text", command=self.add_text_dialog)
        edit_menu.add_command(label="Add Image", command=self.add_image_dialog)
        edit_menu.add_separator()
        edit_menu.add_command(label="Delete Selected", command=self.delete_selected)
        menu.add_cascade(label="Edit", menu=edit_menu)

        navigate_menu = tk.Menu(menu, tearoff=False)
        navigate_menu.add_command(label="Previous Page", command=self.prev_page)
        navigate_menu.add_command(label="Next Page", command=self.next_page)
        menu.add_cascade(label="Navigate", menu=navigate_menu)

        self.root.config(menu=menu)

    def _build_toolbar(self) -> None:
        frame = ttk.Frame(self.root, padding=(8, 4))
        frame.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(frame, text="Add Text", command=self.add_text_dialog).pack(side=tk.LEFT, padx=4)
        ttk.Button(frame, text="Add Image", command=self.add_image_dialog).pack(side=tk.LEFT, padx=4)
        ttk.Button(frame, text="Delete", command=self.delete_selected).pack(side=tk.LEFT, padx=4)
        ttk.Button(frame, text="Prev", command=self.prev_page).pack(side=tk.LEFT, padx=4)
        ttk.Button(frame, text="Next", command=self.next_page).pack(side=tk.LEFT, padx=4)

    def _build_canvas(self) -> None:
        self.canvas = tk.Canvas(self.root, background="#dddddd", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.bind("<Button-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)

    def _build_statusbar(self) -> None:
        status = ttk.Label(self.root, textvariable=self.status_var, anchor=tk.W, padding=(8, 2))
        status.pack(side=tk.BOTTOM, fill=tk.X)

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------
    def new_document(self) -> None:
        self.document = new_document()
        self.current_path = None
        self.current_page_index = 0
        self.selected_object_id = None
        self.selected_kind = None
        self.status_var.set("Created new document")
        self.render_page()
        self._update_title()

    def open_document(self) -> None:
        filename = filedialog.askopenfilename(
            parent=self.root,
            title="Open PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not filename:
            return
        try:
            self.document = load_pdf(filename)
        except Exception as exc:  # pragma: no cover - UI path
            messagebox.showerror("Open PDF", f"Unable to open PDF: {exc}")
            return
        self.current_path = Path(filename)
        self.current_page_index = 0
        self.selected_object_id = None
        self.selected_kind = None
        self.status_var.set(f"Loaded {Path(filename).name}")
        self.render_page()
        self._update_title()

    def save_document(self) -> None:
        if self.current_path is None:
            self.save_document_as()
            return
        self.document.save(str(self.current_path))
        self.status_var.set(f"Saved to {self.current_path.name}")

    def save_document_as(self) -> None:
        filename = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save PDF",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not filename:
            return
        self.current_path = Path(filename)
        self.document.save(filename)
        self.status_var.set(f"Saved to {Path(filename).name}")
        self._update_title()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def prev_page(self) -> None:
        if self.current_page_index > 0:
            self.current_page_index -= 1
            self.render_page()
            self.status_var.set(f"Page {self.current_page_index + 1}")

    def next_page(self) -> None:
        if self.current_page_index < len(self.document.pages) - 1:
            self.current_page_index += 1
            self.render_page()
            self.status_var.set(f"Page {self.current_page_index + 1}")

    # ------------------------------------------------------------------
    # Editing actions
    # ------------------------------------------------------------------
    def add_text_dialog(self) -> None:
        page = self.document.pages[self.current_page_index]
        x = page.width / 4
        y = page.height / 2
        text = simpledialog.askstring("Add Text", "Enter text:", parent=self.root)
        if not text:
            return
        item = self.document.add_text(self.current_page_index, text, x=x, y=y, font_size=18)
        self.selected_object_id = item.id
        self.selected_kind = "text"
        self.render_page()
        self.status_var.set("Text added")

    def add_image_dialog(self) -> None:
        filename = filedialog.askopenfilename(
            parent=self.root,
            title="Insert Image",
            filetypes=[("PNG images", "*.png"), ("All files", "*.*")],
        )
        if not filename:
            return
        page = self.document.pages[self.current_page_index]
        try:
            item = self.document.add_image_from_file(
                self.current_page_index,
                filename,
                x=page.width / 3,
                y=page.height / 3,
            )
        except Exception as exc:  # pragma: no cover - UI path
            messagebox.showerror("Add Image", f"Unable to insert image: {exc}")
            return
        self.selected_object_id = item.id
        self.selected_kind = "image"
        self.render_page()
        self.status_var.set("Image added")

    def delete_selected(self) -> None:
        if not self.selected_object_id:
            self.status_var.set("Nothing selected")
            return
        try:
            self.document.remove_item(self.selected_object_id)
        except KeyError:
            self.status_var.set("Selection missing")
            return
        self.selected_object_id = None
        self.selected_kind = None
        self.render_page()
        self.status_var.set("Item removed")

    def edit_selected_text(self) -> None:
        if self.selected_kind != "text" or not self.selected_object_id:
            return
        text_item = self.document.find_text(self.selected_object_id)
        if not text_item:
            return
        new_content = simpledialog.askstring(
            "Edit Text",
            "Update text:",
            initialvalue=text_item.content,
            parent=self.root,
        )
        if new_content is None:
            return
        text_item.content = new_content
        new_size = simpledialog.askfloat(
            "Font Size",
            "Enter font size (points):",
            initialvalue=text_item.font_size,
            parent=self.root,
            minvalue=6.0,
        )
        if new_size:
            text_item.font_size = float(new_size)
        self.render_page()
        self.status_var.set("Text updated")

    def replace_selected_image(self) -> None:
        if self.selected_kind != "image" or not self.selected_object_id:
            return
        image_item = self.document.find_image(self.selected_object_id)
        if not image_item:
            return
        filename = filedialog.askopenfilename(
            parent=self.root,
            title="Replace Image",
            filetypes=[("PNG images", "*.png"), ("All files", "*.*")],
        )
        if not filename:
            return
        try:
            with open(filename, "rb") as handle:
                raw = handle.read()
            parsed_png = parse_png(raw)
        except Exception as exc:  # pragma: no cover - UI path
            messagebox.showerror("Replace Image", f"Unable to load image: {exc}")
            return
        image_item.data = raw
        image_item.pixel_width = parsed_png.width
        image_item.pixel_height = parsed_png.height
        image_item.decode_parms = parsed_png.decode_parms
        image_item.width = float(parsed_png.width)
        image_item.height = float(parsed_png.height)
        self.render_page()
        self.status_var.set("Image replaced")

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def render_page(self) -> None:
        page = self.document.pages[self.current_page_index]
        self.canvas.delete("all")
        self.canvas_items.clear()
        self.object_to_canvas.clear()
        self.image_cache.clear()

        width = int(page.width * self.zoom)
        height = int(page.height * self.zoom)
        self.canvas.config(scrollregion=(0, 0, width, height))
        self.canvas.config(width=width, height=height)

        # Background page rectangle (slight margin for aesthetics).
        margin = 20
        bg = self.canvas.create_rectangle(
            margin,
            margin,
            width - margin,
            height - margin,
            fill="#ffffff",
            outline="#bbbbbb",
            width=2,
            tags=("page_bg",),
        )
        self.canvas.lower(bg)

        for text in page.texts:
            canvas_id = self._draw_text_item(page, text)
            self.canvas_items[canvas_id] = ("text", text.id)
            self.object_to_canvas[text.id] = canvas_id

        for image in page.images:
            canvas_id = self._draw_image_item(page, image)
            self.canvas_items[canvas_id] = ("image", image.id)
            self.object_to_canvas[image.id] = canvas_id

        self._update_selection_indicator()
        self._update_title()

    def _draw_text_item(self, page: PDFPage, text: PDFTextItem) -> int:
        x, y = self._pdf_to_canvas(page, text.x, text.y)
        font = self._font(text.font_name, text.font_size)
        canvas_id = self.canvas.create_text(
            x,
            y,
            text=text.content,
            anchor="sw",
            fill=text.fill,
            font=font,
            tags=("object", "text"),
        )
        self.canvas.tag_bind(canvas_id, "<Double-1>", self._on_text_double_click)
        return canvas_id

    def _draw_image_item(self, page: PDFPage, image: PDFImageItem) -> int:
        x, y = self._pdf_to_canvas(page, image.x, image.y)
        photo = tk.PhotoImage(data=base64.b64encode(image.data), format="PNG")
        self.image_cache[image.id] = photo
        canvas_id = self.canvas.create_image(
            x,
            y,
            image=photo,
            anchor="sw",
            tags=("object", "image"),
        )
        self.canvas.tag_bind(canvas_id, "<Double-1>", self._on_image_double_click)
        return canvas_id

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _on_text_double_click(self, event: tk.Event[tk.Canvas]) -> None:
        item = event.widget.find_withtag("current")
        if not item:
            return
        canvas_id = item[0]
        kind, object_id = self.canvas_items.get(canvas_id, (None, None))
        if kind != "text":
            return
        self.selected_object_id = object_id
        self.selected_kind = kind
        self.edit_selected_text()

    def _on_image_double_click(self, event: tk.Event[tk.Canvas]) -> None:
        item = event.widget.find_withtag("current")
        if not item:
            return
        canvas_id = item[0]
        kind, object_id = self.canvas_items.get(canvas_id, (None, None))
        if kind != "image":
            return
        self.selected_object_id = object_id
        self.selected_kind = kind
        self.replace_selected_image()

    def _on_canvas_press(self, event: tk.Event[tk.Canvas]) -> None:
        item = self.canvas.find_withtag("current")
        if not item:
            self.selected_object_id = None
            self.selected_kind = None
            self._update_selection_indicator()
            return
        canvas_id = item[0]
        info = self.canvas_items.get(canvas_id)
        if not info:
            self.selected_object_id = None
            self.selected_kind = None
            self._update_selection_indicator()
            return
        kind, object_id = info
        self.selected_object_id = object_id
        self.selected_kind = kind
        self.drag_state = {"canvas_id": canvas_id, "x": event.x, "y": event.y}
        self._update_selection_indicator()

    def _on_canvas_drag(self, event: tk.Event[tk.Canvas]) -> None:
        if not self.drag_state:
            return
        canvas_id = int(self.drag_state["canvas_id"])  # type: ignore[arg-type]
        dx = event.x - int(self.drag_state["x"])  # type: ignore[arg-type]
        dy = event.y - int(self.drag_state["y"])  # type: ignore[arg-type]
        self.canvas.move(canvas_id, dx, dy)
        self.drag_state["x"] = event.x
        self.drag_state["y"] = event.y
        self._update_selection_indicator()

    def _on_canvas_release(self, event: tk.Event[tk.Canvas]) -> None:
        if not self.drag_state:
            return
        canvas_id = int(self.drag_state["canvas_id"])  # type: ignore[arg-type]
        kind, object_id = self.canvas_items.get(canvas_id, (None, None))
        if not kind or not object_id:
            self.drag_state = None
            return
        coords = self.canvas.coords(canvas_id)
        page = self.document.pages[self.current_page_index]
        pdf_x, pdf_y = self._canvas_to_pdf(page, coords[0], coords[1])
        if kind == "text":
            item = self.document.find_text(object_id)
        else:
            item = self.document.find_image(object_id)
        if item:
            item.x = pdf_x
            item.y = pdf_y
        self.drag_state = None
        self.status_var.set("Item moved")

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def _update_title(self) -> None:
        title = "PDF Assembler GUI"
        if self.current_path:
            title += f" - {self.current_path.name}"
        page = self.document.pages[self.current_page_index]
        title += f" (Page {page.number}/{len(self.document.pages)})"
        self.root.title(title)

    def _pdf_to_canvas(self, page: PDFPage, x: float, y: float) -> Tuple[float, float]:
        cx = x * self.zoom + 20
        cy = (page.height - y) * self.zoom + 20
        return cx, cy

    def _canvas_to_pdf(self, page: PDFPage, x: float, y: float) -> Tuple[float, float]:
        pdf_x = (x - 20) / self.zoom
        pdf_y = page.height - ((y - 20) / self.zoom)
        return pdf_x, pdf_y

    def _update_selection_indicator(self) -> None:
        if self.selection_indicator is not None:
            self.canvas.delete(self.selection_indicator)
            self.selection_indicator = None
        if not self.selected_object_id:
            return
        canvas_id = self.object_to_canvas.get(self.selected_object_id)
        if not canvas_id:
            return
        bbox = self.canvas.bbox(canvas_id)
        if not bbox:
            return
        x0, y0, x1, y1 = bbox
        padding = 6
        self.selection_indicator = self.canvas.create_rectangle(
            x0 - padding,
            y0 - padding,
            x1 + padding,
            y1 + padding,
            outline="#1e88e5",
            dash=(4, 2),
            width=2,
        )
        self.canvas.tag_raise(self.selection_indicator)
        self.canvas.tag_raise(canvas_id)

    @lru_cache(maxsize=64)
    def _font(self, family: str, size: float) -> tkfont.Font:
        return tkfont.Font(family=family or "Helvetica", size=max(1, int(size * self.zoom)))


def launch() -> None:
    root = tk.Tk()
    app = PDFAssemblerApp(root)
    root.mainloop()


__all__ = ["PDFAssemblerApp", "launch"]
