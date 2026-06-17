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
    """Extract all tables from a text-based PDF using pdfplumber."""
    import pdfplumber

    all_tables: list[list[list[str]]] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                cleaned = [
                    [cell.strip() if cell else "" for cell in row]
                    for row in table
                    if any(cell for cell in row)
                ]
                if cleaned:
                    all_tables.append(cleaned)
    return all_tables


def extract_text_pdfplumber(file_bytes: bytes) -> str:
    """Extract plain text from all pages of a PDF."""
    import pdfplumber

    texts: list[str] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            texts.append(text)
    return "\n".join(texts)


def extract_tables_tabula(file_bytes: bytes) -> list[list[list[str]]]:
    """Fallback table extraction using tabula-py."""
    try:
        import tabula
        import pandas as pd

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


def clean_cell(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()
