"""Minimal HTTP server providing a GUI for editing PDFs via pdfassembler."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
import cgi

from pdfassembler import EditablePDF, PDFAssemblerError

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)


class DocumentStore:
    def __init__(self) -> None:
        self.pdf: Optional[EditablePDF] = None
        self.source_path: Optional[Path] = None
        self.output_path: Path = STORAGE_DIR / "edited.pdf"

    def load(self, path: Path) -> None:
        self.pdf = EditablePDF.load(str(path))
        self.source_path = path
        self.output_path = STORAGE_DIR / "edited.pdf"
        self.pdf.path = str(self.output_path)

    def ensure_loaded(self) -> EditablePDF:
        if not self.pdf:
            raise PDFAssemblerError("No document loaded")
        return self.pdf

    def to_json(self) -> dict:
        if not self.pdf:
            return {"pages": []}
        return self.pdf.to_json()

    def apply_updates(self, payload: dict) -> None:
        pdf = self.ensure_loaded()
        pdf.apply_updates(payload)

    def save(self, target: Optional[Path] = None) -> Path:
        pdf = self.ensure_loaded()
        destination = target or self.output_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        pdf.save(str(destination))
        return destination

    def read_pdf_bytes(self) -> bytes:
        path = self.save()
        return path.read_bytes()


STORE = DocumentStore()


class PDFRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self):  # noqa: N802 - http method naming
        if self.path.startswith("/api/"):
            self.handle_api_get()
        else:
            super().do_GET()

    def do_POST(self):  # noqa: N802
        if self.path.startswith("/api/"):
            self.handle_api_post()
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")

    def log_message(self, format: str, *args) -> None:  # pragma: no cover - reduce noise
        return

    def handle_api_get(self) -> None:
        if self.path == "/api/document":
            self._send_json(STORE.to_json())
        elif self.path == "/api/document/pdf":
            try:
                data = STORE.read_pdf_bytes()
            except PDFAssemblerError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/api/document/summary":
            try:
                summary = STORE.ensure_loaded().document_summary()
            except PDFAssemblerError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(summary)
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Unknown GET endpoint")

    def handle_api_post(self) -> None:
        if self.path == "/api/upload":
            self._handle_upload()
        elif self.path == "/api/document":
            payload = self._read_json_body()
            if payload is None:
                return
            try:
                STORE.apply_updates(payload)
            except PDFAssemblerError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"status": "updated", "document": STORE.to_json()})
        elif self.path == "/api/document/save":
            try:
                destination = STORE.save()
            except PDFAssemblerError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"status": "saved", "path": str(destination)})
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Unknown POST endpoint")

    def _handle_upload(self) -> None:
        content_type = self.headers.get("Content-Type")
        if not content_type or "multipart/form-data" not in content_type:
            self._send_json({"error": "Expected multipart/form-data"}, status=HTTPStatus.BAD_REQUEST)
            return
        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": content_type,
            },
        )
        file_item = form["file"] if "file" in form else None
        if file_item is None or not getattr(file_item, "filename", ""):
            self._send_json({"error": "Missing uploaded file"}, status=HTTPStatus.BAD_REQUEST)
            return
        data = file_item.file.read()
        upload_path = STORAGE_DIR / file_item.filename
        with open(upload_path, "wb") as handle:
            handle.write(data)
        STORE.load(upload_path)
        self._send_json({"status": "loaded", "document": STORE.to_json(), "path": str(upload_path)})

    def _read_json_body(self) -> Optional[dict]:
        length = self.headers.get("Content-Length")
        if not length:
            self._send_json({"error": "Missing Content-Length"}, status=HTTPStatus.LENGTH_REQUIRED)
            return None
        raw = self.rfile.read(int(length))
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:  # pragma: no cover - user error
            self._send_json({"error": f"Invalid JSON: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return None

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), PDFRequestHandler)
    print(f"Serving PDF assembler GUI on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - manual stop
        print("\nShutting down server")
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the pdfassembler GUI server")
    parser.add_argument("--host", default="127.0.0.1", help="Interface to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    args = parser.parse_args()
    run_server(args.host, args.port)


if __name__ == "__main__":  # pragma: no cover
    main()
