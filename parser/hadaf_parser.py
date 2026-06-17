from __future__ import annotations

import re
from typing import Optional

from models import HadafEmployee
from parser.pdf_utils import (
    clean_cell,
    detect_columns_by_content,
    detect_pdf_type,
    extract_tables_pdfplumber,
    extract_tables_tabula,
    extract_text_pdfplumber,
    ocr_pdf,
)
from utils.logger import get_logger

logger = get_logger(__name__)

_NID_RE = re.compile(r"\b[12]\d{9}\b")
_IBAN_RE = re.compile(r"\bSA\d{22}\b", re.IGNORECASE)
_SERIAL_RE = re.compile(r"^\d{1,6}$")
_AMOUNT_RE = re.compile(r"^[\d,]+(?:\.\d{1,2})?$")

# All known Arabic headers for each column type
_SERIAL_HEADERS = {
    "رقم", "م", "ت", "تسلسلي", "رقم تسلسلي", "مسلسل", "رقم مسلسل", "#", "serial", "no", "seq",
}
_NAME_HEADERS = {
    "اسم", "الاسم", "موظف", "الموظف", "اسم الموظف", "اسم المستفيد", "المستفيد",
    "مستفيد", "name", "employee", "beneficiary",
}
_NID_HEADERS = {
    "هوية", "الهوية", "هوية وطنية", "الهوية الوطنية", "رقم الهوية", "رقم الهوية الوطنية",
    "id", "national id", "رقم المستفيد",
}
_IBAN_HEADERS = {
    "iban", "آيبان", "رقم الآيبان", "رقم الحساب", "حساب",
}
_AMOUNT_HEADERS = {
    "مبلغ", "المبلغ", "قيمة", "القيمة", "قيمة الدعم", "الراتب", "راتب", "amount", "salary",
}


def _header_match(cell: str, patterns: set[str]) -> bool:
    c = cell.lower().strip()
    return any(p in c for p in patterns)


def _detect_columns_by_header(header_row: list[str]) -> dict[str, int]:
    """Try header-based detection first (fast path)."""
    mapping: dict[str, int] = {}
    header_map = [
        ("serial", _SERIAL_HEADERS),
        ("name", _NAME_HEADERS),
        ("nid", _NID_HEADERS),
        ("iban", _IBAN_HEADERS),
        ("amount", _AMOUNT_HEADERS),
    ]
    for idx, cell in enumerate(header_row):
        cell = clean_cell(cell)
        for role, patterns in header_map:
            if role not in mapping and _header_match(cell, patterns):
                mapping[role] = idx
                break
    return mapping


def _parse_amount(value: str) -> Optional[float]:
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None


def _parse_table(table: list[list[str]]) -> list[HadafEmployee]:
    if not table or len(table) < 2:
        return []

    # Try header-based first; fall back to content-based
    col_map = _detect_columns_by_header(table[0])
    if "name" not in col_map or "serial" not in col_map:
        logger.info("Header detection incomplete (%s), trying content-based...", col_map)
        content_map = detect_columns_by_content(table, skip_header_rows=1)
        # Merge — content fills gaps
        for role, idx in content_map.items():
            if role not in col_map:
                col_map[role] = idx
        logger.info("Column map after content detection: %s", col_map)

    if "name" not in col_map:
        logger.warning("No name column detected in table")
        return []

    employees: list[HadafEmployee] = []
    data_rows = table[1:] if _detect_columns_by_header(table[0]) else table

    for row in data_rows:
        if not any(clean_cell(c) for c in row):
            continue
        try:
            # Serial — use content-detected or first numeric column
            serial_val = clean_cell(row[col_map["serial"]]) if "serial" in col_map and col_map["serial"] < len(row) else ""
            name_val = clean_cell(row[col_map["name"]]) if col_map["name"] < len(row) else ""
            nid_val = clean_cell(row[col_map["nid"]]) if "nid" in col_map and col_map["nid"] < len(row) else ""
            iban_val = clean_cell(row[col_map["iban"]]) if "iban" in col_map and col_map["iban"] < len(row) else ""
            amount_val = clean_cell(row[col_map["amount"]]) if "amount" in col_map and col_map["amount"] < len(row) else ""

            if not name_val:
                continue

            # Try to parse serial from value; if blank try row-level NID extraction
            serial: Optional[int] = None
            if _SERIAL_RE.match(serial_val):
                serial = int(serial_val)

            # If no serial found, try to get it from row index
            if serial is None:
                serial = len(employees) + 1

            # Validate / extract NID
            nid: Optional[str] = None
            nid_clean = re.sub(r"\s", "", nid_val)
            if re.match(r"^[12]\d{9}$", nid_clean):
                nid = nid_clean
            else:
                # Search anywhere in the row
                for cell in row:
                    m = _NID_RE.search(clean_cell(cell))
                    if m:
                        nid = m.group(0)
                        break

            # IBAN
            iban: Optional[str] = None
            iban_match = _IBAN_RE.search(iban_val)
            if iban_match:
                iban = iban_match.group(0).upper()
            if not iban:
                for cell in row:
                    m = _IBAN_RE.search(clean_cell(cell))
                    if m:
                        iban = m.group(0).upper()
                        break

            # Amount
            support_amount = _parse_amount(amount_val) if amount_val else None

            employees.append(
                HadafEmployee(
                    serial=serial,
                    name_arabic=name_val,
                    national_id=nid,
                    iban=iban,
                    support_amount=support_amount,
                )
            )
        except (IndexError, ValueError) as exc:
            logger.debug("Skipping row: %s", exc)
            continue

    return employees


def _parse_from_text(text: str) -> list[HadafEmployee]:
    """
    Aggressive text fallback — scans every line for patterns.
    Works on unstructured PDF text output.
    """
    employees: list[HadafEmployee] = []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    serial_counter = 0

    for line in lines:
        # Skip lines that are clearly headers or page numbers
        if len(line) < 4 or re.match(r"^[\-=_\s]+$", line):
            continue

        nid_match = _NID_RE.search(line)
        iban_match = _IBAN_RE.search(line)
        amount_matches = _AMOUNT_RE.findall(line.replace(",", ""))

        # Extract serial from beginning of line
        serial_match = re.match(r"^(\d{1,5})\s+", line)
        if serial_match:
            serial = int(serial_match.group(1))
        else:
            serial = None

        # Remove serial, NID, IBAN, amounts → what's left should be the name
        name_candidate = line
        if serial_match:
            name_candidate = name_candidate[serial_match.end():]
        if nid_match:
            name_candidate = name_candidate.replace(nid_match.group(0), "")
        if iban_match:
            name_candidate = name_candidate.replace(iban_match.group(0), "")
        # Remove number-only tokens
        name_candidate = re.sub(r"\b[\d,\.]+\b", "", name_candidate)
        name_candidate = re.sub(r"\s+", " ", name_candidate).strip()

        # Must contain Arabic characters and be meaningful
        has_arabic = bool(re.search(r"[؀-ۿ]", name_candidate))
        if not (has_arabic and len(name_candidate) > 3):
            continue

        if serial is None:
            serial_counter += 1
            serial = serial_counter

        support_amount: Optional[float] = None
        if amount_matches:
            try:
                support_amount = float(amount_matches[-1])
            except ValueError:
                pass

        employees.append(
            HadafEmployee(
                serial=serial,
                name_arabic=name_candidate,
                national_id=nid_match.group(0) if nid_match else None,
                iban=iban_match.group(0).upper() if iban_match else None,
                support_amount=support_amount,
            )
        )

    return employees


class HadafParser:
    """Parses Hadaf programme PDF files — text, scanned, or mixed format."""

    def parse(self, file_bytes: bytes) -> list[HadafEmployee]:
        pdf_type = detect_pdf_type(file_bytes)
        logger.info("Parsing Hadaf PDF (type=%s, size=%d bytes)", pdf_type, len(file_bytes))

        if pdf_type == "scanned":
            return self._parse_scanned(file_bytes)
        return self._parse_text(file_bytes)

    def _parse_text(self, file_bytes: bytes) -> list[HadafEmployee]:
        # Attempt 1: pdfplumber tables
        tables = extract_tables_pdfplumber(file_bytes)
        logger.info("pdfplumber found %d tables", len(tables))
        for i, table in enumerate(tables):
            employees = _parse_table(table)
            if employees:
                logger.info("Hadaf: %d employees from pdfplumber table #%d", len(employees), i)
                return employees

        # Attempt 2: tabula
        tables = extract_tables_tabula(file_bytes)
        logger.info("tabula found %d tables", len(tables))
        for i, table in enumerate(tables):
            employees = _parse_table(table)
            if employees:
                logger.info("Hadaf: %d employees from tabula table #%d", len(employees), i)
                return employees

        # Attempt 3: raw text parsing
        text = extract_text_pdfplumber(file_bytes)
        logger.info("Falling back to text parsing (%d chars)", len(text))
        employees = _parse_from_text(text)
        logger.info("Hadaf: %d employees from text parsing", len(employees))
        return employees

    def _parse_scanned(self, file_bytes: bytes) -> list[HadafEmployee]:
        text = ocr_pdf(file_bytes)
        employees = _parse_from_text(text)
        logger.info("Hadaf: %d employees via OCR", len(employees))
        return employees

    def debug_extract(self, file_bytes: bytes) -> dict:
        """Return raw extraction info for debugging in the UI."""
        import pdfplumber

        result = {"tables": [], "text_sample": "", "page_count": 0}
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                result["page_count"] = len(pdf.pages)
                for i, page in enumerate(pdf.pages[:3]):
                    tables = page.extract_tables() or []
                    for t in tables:
                        if t:
                            result["tables"].append({
                                "page": i + 1,
                                "rows": len(t),
                                "cols": len(t[0]) if t else 0,
                                "header": t[0] if t else [],
                                "sample": t[1:4],
                            })
                    text = page.extract_text() or ""
                    if text and not result["text_sample"]:
                        result["text_sample"] = text[:500]
        except Exception as exc:
            result["error"] = str(exc)
        return result


# Circular import guard
import io
