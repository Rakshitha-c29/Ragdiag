"""PDF text extraction with pdfplumber."""

from dataclasses import dataclass
from pathlib import Path


class PDFError(ValueError):
    pass


@dataclass
class PageText:
    page: int  # 1-based
    text: str


def count_pages(path: Path) -> int:
    import pdfplumber

    try:
        with pdfplumber.open(path) as pdf:
            return len(pdf.pages)
    except Exception as exc:  # pdfplumber raises several error types for bad files
        raise PDFError(f"Could not read PDF: {exc}") from exc


def extract_pages(path: Path) -> list[PageText]:
    """Return non-empty page texts. Raises PDFError if nothing is extractable."""
    import pdfplumber

    pages: list[PageText] = []
    try:
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                text = text.strip()
                if text:
                    pages.append(PageText(page=i, text=text))
    except Exception as exc:
        raise PDFError(f"Could not read PDF: {exc}") from exc

    if not pages:
        raise PDFError(
            "No extractable text found. The PDF is probably scanned images; run OCR first."
        )
    return pages
