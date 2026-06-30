from __future__ import annotations

import re
from typing import Optional

from models import BankEmployee
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

_IBAN_RE = re.compile(r"\bSA\d{22}\b", re.IGNORECASE)
_AMOUNT_RE = re.compile(r"\b\d[\d,]*(?:\.\d{1,2})?\b")
_NID_RE = re.compile(r"\b[12]\d{9}\b")
_SERIAL_RE = re.compile(r"^\d{1,6}$")

# تنسيق سطر البنك الدقيق:
# SAR  6,766.67  SA...24...  BANKCODE  اسم الموظف  NID(10-16)  م
_BANK_LINE_RE = re.compile(
    r"SAR\s+([\d,]+\.\d{2})\s+(SA\d{22})\s+\S+\s+(.*?)\s+([12]\d{9,15})\s+(\d{1,6})\s*$"
)

_NAME_HEADERS = {
    "اسم", "الاسم", "موظف", "المستفيد", "مستفيد", "اسم الموظف", "اسم المستفيد",
    "name", "employee", "beneficiary", "account name", "account holder",
}
_IBAN_HEADERS = {
    "iban", "آيبان", "رقم الآيبان", "رقم الحساب", "حساب", "account number", "account",
}
_AMOUNT_HEADERS = {
    "مبلغ", "المبلغ", "قيمة", "القيمة", "الراتب", "راتب", "amount", "salary",
    "credit", "transfer amount", "المبلغ المحول",
}
_REF_HEADERS = {
    "مرجع", "المرجع", "رقم المرجع", "reference", "ref", "transaction", "عملية",
}
_NID_HEADERS = {
    "هوية", "الهوية", "رقم الهوية", "الهوية الوطنية", "national id", "national", "id number",
}
_SERIAL_HEADERS = {
    "تسلسلي", "م", "ت", "serial", "seq", "رقم تسلسلي",
}


def _header_match(cell: str, patterns: set[str]) -> bool:
    c = cell.lower().strip()
    return any(p in c for p in patterns)


def _detect_columns_by_header(header_row: list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    header_map = [
        ("name", _NAME_HEADERS),
        ("iban", _IBAN_HEADERS),
        ("amount", _AMOUNT_HEADERS),
        ("reference", _REF_HEADERS),
        ("nid", _NID_HEADERS),
        ("serial", _SERIAL_HEADERS),
    ]
    for idx, cell in enumerate(header_row):
        cell_clean = clean_cell(cell)
        for role, patterns in header_map:
            if role not in mapping and _header_match(cell_clean, patterns):
                mapping[role] = idx
                break
    return mapping


def _parse_amount(value: str) -> float:
    cleaned = re.sub(r"[,\s]", "", value)
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _extract_iban(value: str) -> Optional[str]:
    m = _IBAN_RE.search(value)
    return m.group(0).upper() if m else None


def _parse_table(table: list[list[str]]) -> list[BankEmployee]:
    if not table or len(table) < 2:
        return []

    col_map = _detect_columns_by_header(table[0])
    if "name" not in col_map:
        logger.info("Header detection found no name col (%s), trying content-based...", col_map)
        content_map = detect_columns_by_content(table, skip_header_rows=1)
        for role, idx in content_map.items():
            if role not in col_map:
                col_map[role] = idx
        logger.info("Bank column map after content detection: %s", col_map)

    if "name" not in col_map:
        return []

    employees: list[BankEmployee] = []
    for row in table[1:]:
        if not any(clean_cell(c) for c in row):
            continue
        try:
            def _get(role: str) -> str:
                idx = col_map.get(role)
                return clean_cell(row[idx]) if idx is not None and idx < len(row) else ""

            name = _get("name")
            if not name or name.lower() in {"n/a", "na", "-", ""}:
                continue

            iban_raw = _get("iban")
            iban = _extract_iban(iban_raw)
            if not iban:
                # search all cells for IBAN
                for cell in row:
                    iban = _extract_iban(clean_cell(cell))
                    if iban:
                        break

            amount = _parse_amount(_get("amount")) if "amount" in col_map else 0.0
            if amount == 0:
                # Try any numeric cell
                for cell in row:
                    cv = clean_cell(cell).replace(",", "")
                    try:
                        v = float(cv)
                        if v > 100:  # reasonable salary
                            amount = v
                            break
                    except ValueError:
                        pass

            ref = _get("reference") or None

            serial_raw = _get("serial")
            serial: Optional[int] = int(serial_raw) if _SERIAL_RE.match(serial_raw) else None

            nid_raw = _get("nid")
            nid_clean = re.sub(r"\s", "", nid_raw)
            nid: Optional[str] = nid_clean if re.match(r"^[12]\d{9}$", nid_clean) else None
            if not nid:
                for cell in row:
                    m = _NID_RE.search(clean_cell(cell))
                    if m:
                        nid = m.group(0)
                        break

            employees.append(
                BankEmployee(name=name, iban=iban, amount=amount, reference=ref,
                             serial=serial, national_id=nid)
            )
        except (IndexError, ValueError) as exc:
            logger.debug("Skipping bank row: %s", exc)
            continue

    return employees


def _parse_from_text_structured(text: str) -> list[BankEmployee]:
    """
    استخراج دقيق باستخدام نمط السطر البنكي المعروف:
    SAR <مبلغ> <SA+22رقم> <كود_البنك> <اسم> <هوية> <م>
    """
    employees: list[BankEmployee] = []
    for line in text.splitlines():
        m = _BANK_LINE_RE.search(line.strip())
        if not m:
            continue
        amount_str, iban, name, nid, serial = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        try:
            amount = float(amount_str.replace(",", ""))
        except ValueError:
            amount = 0.0
        employees.append(BankEmployee(
            name=name.strip(),
            iban=iban.upper(),
            amount=amount,
            national_id=nid if len(nid) == 10 else None,
            serial=int(serial),
        ))
    return employees


def _parse_from_text(text: str) -> list[BankEmployee]:
    """Line-by-line fallback for unstructured bank PDFs."""
    employees: list[BankEmployee] = []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    for line in lines:
        iban_match = _IBAN_RE.search(line)
        iban = iban_match.group(0).upper() if iban_match else None

        nid_match = _NID_RE.search(line)
        nid = nid_match.group(0) if nid_match else None

        amount_matches = _AMOUNT_RE.findall(line)
        amount = 0.0
        for am in reversed(amount_matches):
            try:
                v = float(am.replace(",", ""))
                if v > 100:
                    amount = v
                    break
            except ValueError:
                pass

        # Remove IBAN, NID, numbers → isolate name
        name_candidate = line
        if iban_match:
            name_candidate = name_candidate.replace(iban_match.group(0), "")
        if nid_match:
            name_candidate = name_candidate.replace(nid_match.group(0), "")
        name_candidate = re.sub(r"\b[\d,\.]+\b", "", name_candidate)
        name_candidate = re.sub(r"\s+", " ", name_candidate).strip()

        has_letters = bool(re.search(r"[A-Za-zؠ-ۿ]", name_candidate))
        if not (has_letters and len(name_candidate) > 3 and iban):
            continue

        employees.append(BankEmployee(name=name_candidate, iban=iban,
                                      amount=amount, national_id=nid))

    return employees


class BankParser:
    """Parses bank payroll PDF files to extract employee payment records."""

    def parse(self, file_bytes: bytes) -> list[BankEmployee]:
        pdf_type = detect_pdf_type(file_bytes)
        logger.info("Parsing Bank PDF (type=%s, size=%d bytes)", pdf_type, len(file_bytes))

        if pdf_type == "scanned":
            return self._parse_scanned(file_bytes)
        return self._parse_text(file_bytes)

    def _parse_text(self, file_bytes: bytes) -> list[BankEmployee]:
        tables = extract_tables_pdfplumber(file_bytes)
        logger.info("Bank: pdfplumber found %d tables", len(tables))
        all_from_tables: list[BankEmployee] = []
        for i, table in enumerate(tables):
            employees = _parse_table(table)
            if employees:
                logger.info("Bank: table #%d → %d employees", i, len(employees))
                all_from_tables.extend(employees)

        if all_from_tables:
            return all_from_tables

        # Tabula fallback
        tables = extract_tables_tabula(file_bytes)
        logger.info("Bank: tabula found %d tables", len(tables))
        for i, table in enumerate(tables):
            employees = _parse_table(table)
            if employees:
                all_from_tables.extend(employees)

        if all_from_tables:
            return all_from_tables

        # Text fallback — أولاً النمط الدقيق ثم العام
        text = extract_text_pdfplumber(file_bytes)
        employees = _parse_from_text_structured(text)
        logger.info("Bank: %d employees from structured text (SAR pattern)", len(employees))
        if not employees:
            employees = _parse_from_text(text)
            logger.info("Bank: %d employees from generic text parsing", len(employees))
        return employees

    def _parse_scanned(self, file_bytes: bytes) -> list[BankEmployee]:
        text = ocr_pdf(file_bytes)
        employees = _parse_from_text_structured(text)
        if not employees:
            employees = _parse_from_text(text)
        logger.info("Bank: %d employees via OCR", len(employees))
        return employees

    def debug_extract(self, file_bytes: bytes) -> dict:
        """Return raw extraction info for debugging."""
        import io
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
