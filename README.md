# pdfassembler GUI

This repository contains a lightweight implementation of the `pdfassembler` object
model together with a small web-based GUI for loading, editing, and exporting
PDF files.  It is designed to run without external dependencies so it can operate
in restricted execution environments.

## Features

- Parse a subset of PDF files into an editable object model that exposes
  pages, text elements, and image elements.
- Update element text, positions, order, and font size while preserving
  the original PDF structure.
- Minimal HTTP server (`app/server.py`) that powers a drag-and-drop GUI.
- Web client that renders pages, allows text editing, dragging elements,
  re-ordering layers, and downloading the edited PDF.
- Test suite validating round-trip edits using the local pdfassembler module.

## Requirements

- Python 3.11+
- No third-party packages are required.

## Running the tests

```bash
pytest
```

## Starting the GUI server

```bash
python -m app.server --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000` in a browser. Upload a PDF generated with the
included tooling (or another document that uses standard text/image content
streams). Use the inspector to adjust element properties, save the layout, and
download the edited PDF via the toolbar.

The server stores uploaded and edited documents in `app/storage/` (ignored by
Git).

## Project layout

```
pdfassembler/      # Minimal pdfassembler module (parsing, model, writer)
app/server.py      # HTTP server exposing REST endpoints and static UI
app/static/        # Front-end HTML/CSS/JavaScript assets
tests/             # Pytest suite covering pdfassembler behaviour
```
