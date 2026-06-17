from __future__ import annotations

import re
from typing import Optional

from models import HadafEmployee
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

# Patterns to identify serial number column headers
_SERIAL_HEADERS = {"رقم", "تسلسلي", "م", "#", "serial", "no", "seq", "رقم تسلسلي", "الرقم"}
_NAME_HEADERS = {"اسم", "الاسم", "موظف", "الموظف", "name", "employee", "اسم الموظف"}
_NID_HEADERS = {"هوية", "الهوية", "هوية وطنية", "الهوية الوطنية", "id", "national id", "رقم الهوية"}


def _header_matches(cell: str, patterns: set[str]) -> bool:
    cell_lower = cell.lower().strip()
    return any(p in cell_lower for p in patterns)


def _is_serial(value: str) -> bool:
    return bool(re.match(r"^\d{1,5}$", value.strip()))


def _is_national_id(value: str) -> bool:
    cleaned = re.sub(r"\s", "", value)
    return bool(re.match(r"^[12]\d{9}$", cleaned))


def _detect_columns(header_row: list[str]) -> dict[str, int]:
    """Map column semantic roles to their indices."""
    mapping: dict[str, int] = {}
    for idx, cell in enumerate(header_row):
        # Use 'not in mapping' (not .get()) — index 0 is falsy but valid
        if "serial" not in mapping and _header_matches(cell, _SERIAL_HEADERS):
            mapping["serial"] = idx
        elif "name" not in mapping and _header_matches(cell, _NAME_HEADERS):
            mapping["name"] = idx
        elif "nid" not in mapping and _header_matches(cell, _NID_HEADERS):
            mapping["nid"] = idx
    return mapping


def _parse_table(table: list[list[str]]) -> list[HadafEmployee]:
    """Parse a single table into HadafEmployee records."""
    if not table or len(table) < 2:
        return []

    col_map = _detect_columns(table[0])
    employees: list[HadafEmployee] = []

    for row in table[1:]:
        if not any(cell.strip() for cell in row):
            continue
        try:
            serial_val = clean_cell(row[col_map["serial"]]) if "serial" in col_map else ""
            name_val = clean_cell(row[col_map["name"]]) if "name" in col_map else ""
            nid_val = clean_cell(row[col_map.get("nid", -1)]) if "nid" in col_map else ""

            if not name_val or not _is_serial(serial_val):
                continue

            employees.append(
                HadafEmployee(
                    serial=int(serial_val),
                    name_arabic=name_val,
                    national_id=nid_val if _is_national_id(nid_val) else None,
                )
            )
        except (IndexError, ValueError):
            continue

    return employees


def _parse_from_text(text: str) -> list[HadafEmployee]:
    """Fallback: parse line-by-line when table extraction fails."""
    employees: list[HadafEmployee] = []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    for line in lines:
        # Expect lines like: "1  عساف عبدالرحمن الرشيدي  1234567890"
        match = re.match(r"^(\d{1,5})\s+(.+?)(?:\s+(1\d{9}|2\d{9}))?$", line)
        if match:
            serial = int(match.group(1))
            name = match.group(2).strip()
            nid = match.group(3)
            if name:
                employees.append(
                    HadafEmployee(
                        serial=serial,
                        name_arabic=name,
                        national_id=nid,
                    )
                )
    return employees


class HadafParser:
    """Parses Hadaf programme PDF files to extract employee records."""

    def parse(self, file_bytes: bytes) -> list[HadafEmployee]:
        pdf_type = detect_pdf_type(file_bytes)
        logger.info("Parsing Hadaf PDF (type=%s)", pdf_type)

        if pdf_type == "scanned":
            return self._parse_scanned(file_bytes)
        return self._parse_text(file_bytes)

    def _parse_text(self, file_bytes: bytes) -> list[HadafEmployee]:
        # Try pdfplumber tables first
        tables = extract_tables_pdfplumber(file_bytes)
        for table in tables:
            employees = _parse_table(table)
            if employees:
                logger.info("Hadaf: extracted %d employees via pdfplumber tables", len(employees))
                return employees

        # Fallback: tabula
        tables = extract_tables_tabula(file_bytes)
        for table in tables:
            employees = _parse_table(table)
            if employees:
                logger.info("Hadaf: extracted %d employees via tabula", len(employees))
                return employees

        # Fallback: raw text
        text = extract_text_pdfplumber(file_bytes)
        employees = _parse_from_text(text)
        logger.info("Hadaf: extracted %d employees via text parsing", len(employees))
        return employees

    def _parse_scanned(self, file_bytes: bytes) -> list[HadafEmployee]:
        text = ocr_pdf(file_bytes)
        employees = _parse_from_text(text)
        logger.info("Hadaf: extracted %d employees via OCR", len(employees))
        return employees
