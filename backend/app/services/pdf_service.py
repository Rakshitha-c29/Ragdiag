"""PDF text extraction: pdfplumber, with Tesseract OCR for image-based pages.

A page where pdfplumber finds fewer than OCR_MIN_CHARS characters is treated as
image-based (a scan or a photo). It is rasterized with pdf2image (needs Poppler)
and read with pytesseract (needs the Tesseract binary). If either tool is
missing, those pages are skipped with a warning and the rest of the PDF is used.
"""

import logging
import shutil
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import get_settings

log = logging.getLogger(__name__)


class PDFError(ValueError):
    pass


@dataclass
class PageText:
    page: int  # 1-based
    text: str
    ocr: bool = False  # text came from Tesseract


def count_pages(path: Path) -> int:
    import pdfplumber

    try:
        with pdfplumber.open(path) as pdf:
            return len(pdf.pages)
    except Exception as exc:  # pdfplumber raises several error types for bad files
        raise PDFError(f"Could not read PDF: {exc}") from exc


# ---------- OCR ----------

@lru_cache(maxsize=1)
def ocr_unavailable_reason() -> str | None:
    """None if OCR can run, otherwise why not. Checked once per process,
    so restart the server after installing Tesseract or Poppler."""
    s = get_settings()
    if not s.ocr_enabled:
        return "OCR is disabled (OCR_ENABLED=false)"

    try:
        import pytesseract
        from pdf2image import convert_from_path  # noqa: F401
    except ImportError as exc:
        return f"Python package missing: {exc.name} (pip install pdf2image pytesseract)"

    if s.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = s.tesseract_cmd
    try:
        version = pytesseract.get_tesseract_version()
    except Exception:
        if s.tesseract_cmd:
            return f"Tesseract not found at TESSERACT_CMD={s.tesseract_cmd}"
        return (
            "Tesseract is not installed or not on PATH "
            "(install it, or set TESSERACT_CMD to the full path of tesseract.exe)"
        )

    if s.poppler_path:
        if not any((Path(s.poppler_path) / n).exists() for n in ("pdftoppm", "pdftoppm.exe")):
            return f"Poppler not found in POPPLER_PATH={s.poppler_path} (pdftoppm missing)"
    elif not shutil.which("pdftoppm"):
        return "Poppler is not installed or not on PATH (needed by pdf2image; or set POPPLER_PATH)"

    try:
        langs = set(pytesseract.get_languages(config=""))
        missing = [l for l in s.ocr_lang.split("+") if l not in langs]
        if missing:
            return f"Tesseract language data missing: {', '.join(missing)} (installed: {', '.join(sorted(langs))})"
    except Exception:
        pass  # older Tesseract builds can't list languages; let OCR try anyway

    log.info("OCR available: Tesseract %s, language %s", version, s.ocr_lang)
    return None


def _ocr_page(path: Path, page_no: int) -> str:
    import pytesseract
    from pdf2image import convert_from_path

    s = get_settings()
    images = convert_from_path(
        str(path),
        dpi=s.ocr_dpi,
        first_page=page_no,
        last_page=page_no,
        grayscale=True,
        poppler_path=s.poppler_path or None,
    )
    if not images:
        return ""
    try:
        return pytesseract.image_to_string(images[0], lang=s.ocr_lang, timeout=s.ocr_timeout_s).strip()
    finally:
        for img in images:
            img.close()


# ---------- Extraction ----------

def extract_pages(path: Path) -> list[PageText]:
    """Return non-empty page texts, using OCR for image-based pages.
    Raises PDFError if no text can be extracted at all."""
    import pdfplumber

    s = get_settings()
    try:
        with pdfplumber.open(path) as pdf:
            raw = [(i, (page.extract_text() or "").strip()) for i, page in enumerate(pdf.pages, start=1)]
    except Exception as exc:
        raise PDFError(f"Could not read PDF: {exc}") from exc

    image_pages = [i for i, text in raw if len(text) < s.ocr_min_chars]
    ocr_text: dict[int, str] = {}
    skipped: list[int] = []
    reason = ocr_unavailable_reason() if image_pages else None

    if image_pages and reason:
        skipped = image_pages
        log.warning(
            "%s: %d image-based page(s) skipped, OCR unavailable: %s. Pages: %s",
            path.name, len(image_pages), reason, _page_list(image_pages),
        )
    elif image_pages:
        started = time.perf_counter()
        for i in image_pages:
            try:
                ocr_text[i] = _ocr_page(path, i)
            except Exception as exc:  # timeout, corrupt image, Poppler error...
                skipped.append(i)
                log.warning("%s: OCR failed on page %d, skipping it: %s", path.name, i, exc)
        log.info(
            "%s: OCR ran on %d page(s) in %.1fs",
            path.name, len(image_pages) - len(skipped), time.perf_counter() - started,
        )

    pages: list[PageText] = []
    for i, text in raw:
        ocr = ocr_text.get(i, "")
        if len(ocr) > len(text):
            pages.append(PageText(page=i, text=ocr, ocr=True))
        elif text:
            pages.append(PageText(page=i, text=text))

    if not pages:
        if reason:
            raise PDFError(
                f"No extractable text found. The PDF looks scanned and OCR is unavailable: {reason}."
            )
        if skipped:
            raise PDFError(
                f"No extractable text found. OCR failed on {len(skipped)} page(s) ({_page_list(skipped)}); "
                "see the server log for details."
            )
        raise PDFError("No extractable text found, even with OCR. The pages may be blank or unreadable.")
    return pages


def _page_list(pages: list[int], limit: int = 20) -> str:
    shown = ", ".join(map(str, pages[:limit]))
    return shown + (f" (+{len(pages) - limit} more)" if len(pages) > limit else "")
