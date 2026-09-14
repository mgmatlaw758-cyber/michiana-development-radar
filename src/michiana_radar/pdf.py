from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from .parsers.elkhart import Page


def extract_pdf_pages(path: Path) -> list[Page]:
    reader = PdfReader(path)
    return [
        Page(number=index, text=page.extract_text() or "")
        for index, page in enumerate(reader.pages, start=1)
    ]
