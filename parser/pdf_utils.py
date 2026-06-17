from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Optional

from utils.logger import get_logger

logger = get_logger(__name__)


def detect_pdf_type(file_bytes: bytes) -> str:
    """Return 'text' if PDF contains extractable text, else 'scanned'."""
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            total_chars = 0
            pages_checked = min(3, len(pdf.pages))
            for page in pdf.pages[:pages_checked]:
                text = page.extract_text() or ""
                total_chars += len(text.strip())
            threshold = 50 * pages_checked
            result = "text" if total_chars >= threshold else "scanned"
            logger.info("PDF type detected: %s (chars=%d)", result, total_chars)
            return result
    except Exception as exc:
        logger.warning("PDF type detection failed: %s — defaulting to 'text'", exc)
        return "text"


def extract_tables_pdfplumber(file_bytes: bytes) -> list[list[list[str]]]:
    """Extract all tables from all pages of a text-based PDF using pdfplumber."""
    import pdfplumber

    all_tables: list[list[list[str]]] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            try:
                tables = page.extract_tables()
                for table in tables:
                    cleaned = [
                        [cell.strip() if cell else "" for cell in row]
                        for row in table
                        if any(cell for cell in row)
                    ]
                    if len(cleaned) >= 2:
                        all_tables.append(cleaned)
            except Exception as exc:
                logger.warning("Page %d table extraction failed: %s", page_num, exc)
    return all_tables


def extract_text_pdfplumber(file_bytes: bytes) -> str:
    """Extract full text from all pages."""
    import pdfplumber

    texts: list[str] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            texts.append(text)
    return "\n".join(texts)


def extract_text_per_page(file_bytes: bytes) -> list[str]:
    """Return list of text per page (for multi-page analysis)."""
    import pdfplumber

    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return pages


def extract_tables_tabula(file_bytes: bytes) -> list[list[list[str]]]:
    """Fallback table extraction using tabula-py."""
    try:
        import tabula

        tmp_path = Path("_tmp_tabula.pdf")
        tmp_path.write_bytes(file_bytes)
        dfs = tabula.read_pdf(str(tmp_path), pages="all", multiple_tables=True, silent=True)
        tmp_path.unlink(missing_ok=True)

        tables: list[list[list[str]]] = []
        for df in dfs:
            if df.empty:
                continue
            rows = [list(df.columns)]
            for _, row in df.iterrows():
                rows.append([str(v) if v is not None else "" for v in row])
            if len(rows) >= 2:
                tables.append(rows)
        return tables
    except Exception as exc:
        logger.warning("tabula extraction failed: %s", exc)
        return []


def ocr_pdf(file_bytes: bytes, lang: str = "ara+eng", config: str = "--oem 3 --psm 6") -> str:
    """Convert scanned PDF pages to text via OCR."""
    try:
        from pdf2image import convert_from_bytes
        import pytesseract

        images = convert_from_bytes(file_bytes, dpi=300)
        pages_text: list[str] = []
        for img in images:
            text = pytesseract.image_to_string(img, lang=lang, config=config)
            pages_text.append(text)
        return "\n".join(pages_text)
    except Exception as exc:
        logger.error("OCR failed: %s", exc)
        raise RuntimeError(f"OCR processing failed: {exc}") from exc


def clean_cell(value) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


# ---- Content-based column detection helpers ----

_NID_RE = re.compile(r"^[12]\d{9}$")
_SERIAL_RE = re.compile(r"^\d{1,6}$")
_IBAN_RE = re.compile(r"SA\d{22}", re.IGNORECASE)
_AMOUNT_RE = re.compile(r"^[\d,]+(?:\.\d{1,2})?$")
_ARABIC_RE = re.compile(r"[؀-ۿ]")
_ENGLISH_NAME_RE = re.compile(r"^[A-Za-z\s]{5,}$")


def _score_column(values: list[str]) -> dict[str, float]:
    """Return role-probability scores for a column based on its cell content."""
    non_empty = [v for v in values if v and v.lower() not in {"n/a", "na", "-", "none", ""}]
    total = max(len(non_empty), 1)

    serial_n = sum(1 for v in non_empty if _SERIAL_RE.match(v))
    nid_n = sum(1 for v in non_empty if _NID_RE.match(re.sub(r"\s", "", v)))
    iban_n = sum(1 for v in non_empty if _IBAN_RE.search(v))
    amount_n = sum(1 for v in non_empty if _AMOUNT_RE.match(v.replace(",", "")))
    arabic_n = sum(1 for v in non_empty if _ARABIC_RE.search(v) and len(v) > 4)
    english_n = sum(1 for v in non_empty if _ENGLISH_NAME_RE.match(v) and len(v.split()) >= 2)

    name_n = arabic_n + english_n

    # Disambiguate serial vs amount (both are digits)
    avg_len = sum(len(v) for v in non_empty) / total if non_empty else 0

    return {
        "serial": (serial_n / total) * (1.0 if avg_len <= 5 else 0.3),
        "nid": nid_n / total,
        "iban": iban_n / total,
        "amount": (amount_n / total) * (0.3 if avg_len <= 4 else 1.0),
        "name": name_n / total,
    }


def detect_columns_by_content(
    rows: list[list[str]],
    skip_header_rows: int = 0,
) -> dict[str, int]:
    """
    Detect column roles purely from cell content — header-independent.

    Returns mapping: {'serial': 0, 'name': 1, 'nid': 2, ...}
    """
    if len(rows) < 2:
        return {}

    data_rows = rows[skip_header_rows:]
    num_cols = max((len(r) for r in data_rows), default=0)
    if num_cols == 0:
        return {}

    col_scores: list[dict[str, float]] = []
    for col_idx in range(num_cols):
        values = [clean_cell(r[col_idx]) if col_idx < len(r) else "" for r in data_rows]
        col_scores.append(_score_column(values))

    mapping: dict[str, int] = {}
    # Assign roles greedily: highest unambiguous score wins
    for role in ("iban", "nid", "name", "serial", "amount"):
        best_idx, best_score = -1, 0.3  # minimum threshold
        for col_idx, scores in enumerate(col_scores):
            if col_idx in mapping.values():
                continue
            if scores[role] > best_score:
                best_score = scores[role]
                best_idx = col_idx
        if best_idx >= 0:
            mapping[role] = best_idx

    return mapping
