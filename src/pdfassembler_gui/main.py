"""CLI entrypoint for launching the PDF assembler GUI."""

from __future__ import annotations

from .app import launch


def main() -> None:
    launch()


if __name__ == "__main__":  # pragma: no cover
    main()
