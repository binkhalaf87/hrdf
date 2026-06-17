from __future__ import annotations

import re
from typing import Optional

from models import BankEmployee
from parser.pdf_utils import (
    clean_cell,
    detect_pdf_type,
    extract_tables_pdfplumber,
    extract_tables_tabula,
    extract_text_pdfplumber,
    ocr_pdf,
)
from utils.logger import get_logger

logger = get_logger(__name__)

_NAME_HEADERS = {"اسم", "الاسم", "موظف", "name", "employee", "beneficiary", "المستفيد"}
_IBAN_HEADERS = {"iban", "آيبان", "رقم الحساب", "حساب", "account"}
_AMOUNT_HEADERS = {"مبلغ", "المبلغ", "amount", "salary", "الراتب", "قيمة"}
_REF_HEADERS = {"مرجع", "reference", "ref", "رقم المرجع", "transaction"}
_SERIAL_HEADERS = {"تسلسلي", "serial", "seq", "م"}  # removed "رقم" — too generic, matches رقم الهوية
_NID_HEADERS = {"هوية", "national id", "national", "رقم الهوية", "id number"}

_IBAN_RE = re.compile(r"\bSA\d{22}\b", re.IGNORECASE)
_AMOUNT_RE = re.compile(r"\b\d[\d,]*(?:\.\d{1,2})?\b")
_NID_RE = re.compile(r"\b[12]\d{9}\b")


def _header_matches(cell: str, patterns: set[str]) -> bool:
    cell_lower = cell.lower().strip()
    return any(p in cell_lower for p in patterns)


def _detect_columns(header_row: list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for idx, cell in enumerate(header_row):
        cell = clean_cell(cell)
        if "name" not in mapping and _header_matches(cell, _NAME_HEADERS):
            mapping["name"] = idx
        elif "iban" not in mapping and _header_matches(cell, _IBAN_HEADERS):
            mapping["iban"] = idx
        elif "amount" not in mapping and _header_matches(cell, _AMOUNT_HEADERS):
            mapping["amount"] = idx
        elif "reference" not in mapping and _header_matches(cell, _REF_HEADERS):
            mapping["reference"] = idx
        elif "nid" not in mapping and _header_matches(cell, _NID_HEADERS):
            mapping["nid"] = idx
        elif "serial" not in mapping and _header_matches(cell, _SERIAL_HEADERS):
            mapping["serial"] = idx
    return mapping


def _parse_amount(value: str) -> float:
    cleaned = re.sub(r"[,\s]", "", value)
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _parse_serial(value: str) -> Optional[int]:
    if re.match(r"^\d{1,5}$", value.strip()):
        return int(value.strip())
    return None


def _parse_table(table: list[list[str]]) -> list[BankEmployee]:
    if not table or len(table) < 2:
        return []

    col_map = _detect_columns(table[0])
    if "name" not in col_map:
        return []

    employees: list[BankEmployee] = []
    for row in table[1:]:
        if not any(cell.strip() for cell in row):
            continue
        try:
            name = clean_cell(row[col_map["name"]])
            if not name or name.lower() in {"n/a", "na", "-", ""}:
                continue

            iban_raw = clean_cell(row[col_map["iban"]]) if "iban" in col_map else ""
            iban_match = _IBAN_RE.search(iban_raw)
            iban = iban_match.group(0).upper() if iban_match else (iban_raw or None)

            amount_raw = clean_cell(row[col_map["amount"]]) if "amount" in col_map else "0"
            amount = _parse_amount(amount_raw)

            ref = clean_cell(row[col_map["reference"]]) if "reference" in col_map else None
            serial_raw = clean_cell(row[col_map["serial"]]) if "serial" in col_map else ""
            serial = _parse_serial(serial_raw)

            nid_raw = clean_cell(row[col_map["nid"]]) if "nid" in col_map else ""
            nid_match = _NID_RE.search(nid_raw)
            nid = nid_match.group(0) if nid_match else None

            employees.append(
                BankEmployee(
                    name=name,
                    iban=iban,
                    amount=amount,
                    reference=ref,
                    serial=serial,
                    national_id=nid,
                )
            )
        except (IndexError, ValueError):
            continue

    return employees


def _parse_from_text(text: str) -> list[BankEmployee]:
    """
    Fallback parser: scans lines for IBAN patterns and tries to extract
    adjacent name and amount fields.
    """
    employees: list[BankEmployee] = []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    for line in lines:
        iban_match = _IBAN_RE.search(line)
        iban = iban_match.group(0).upper() if iban_match else None

        amount_matches = _AMOUNT_RE.findall(line)
        amount = _parse_amount(amount_matches[-1]) if amount_matches else 0.0

        nid_match = _NID_RE.search(line)
        nid = nid_match.group(0) if nid_match else None

        # Remove IBAN and numbers to isolate the name
        name_candidate = re.sub(r"\bSA\d{22}\b", "", line, flags=re.IGNORECASE)
        name_candidate = re.sub(r"\b\d[\d,.]*\b", "", name_candidate)
        name_candidate = re.sub(r"\s+", " ", name_candidate).strip()

        if len(name_candidate) > 3 and iban:
            employees.append(
                BankEmployee(
                    name=name_candidate,
                    iban=iban,
                    amount=amount,
                    national_id=nid,
                )
            )

    return employees


class BankParser:
    """Parses bank payroll PDF files to extract employee payment records."""

    def parse(self, file_bytes: bytes) -> list[BankEmployee]:
        pdf_type = detect_pdf_type(file_bytes)
        logger.info("Parsing Bank PDF (type=%s)", pdf_type)

        if pdf_type == "scanned":
            return self._parse_scanned(file_bytes)
        return self._parse_text(file_bytes)

    def _parse_text(self, file_bytes: bytes) -> list[BankEmployee]:
        tables = extract_tables_pdfplumber(file_bytes)
        for table in tables:
            employees = _parse_table(table)
            if employees:
                logger.info("Bank: extracted %d employees via pdfplumber", len(employees))
                return employees

        tables = extract_tables_tabula(file_bytes)
        for table in tables:
            employees = _parse_table(table)
            if employees:
                logger.info("Bank: extracted %d employees via tabula", len(employees))
                return employees

        text = extract_text_pdfplumber(file_bytes)
        employees = _parse_from_text(text)
        logger.info("Bank: extracted %d employees via text parsing", len(employees))
        return employees

    def _parse_scanned(self, file_bytes: bytes) -> list[BankEmployee]:
        text = ocr_pdf(file_bytes)
        employees = _parse_from_text(text)
        logger.info("Bank: extracted %d employees via OCR", len(employees))
        return employees
