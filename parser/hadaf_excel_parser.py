"""
Parser for Hadaf programme Excel files.

Expected columns (order doesn't matter, detected by keyword match):
    serial      : الرقم التسلسلي
    name        : اسم الموظف
    nid         : رقم الهوية الوطنية
    iban        : الايبان
    amount      : إجمالي الراتب / مبلغ الدعم
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import pandas as pd

from models import HadafEmployee
from utils.logger import get_logger

logger = get_logger(__name__)

# ── keyword patterns for column detection ─────────────────────────────────────
_COL_PATTERNS: dict[str, list[str]] = {
    "serial": ["تسلسل"],
    "name":   ["اسم الموظف", "اسم موظف"],   # exact phrase — avoids matching "حالموظف" in amount col
    "nid":    ["هوية"],
    "iban":   ["iban1"],
    "iban2":  ["iban2"],
    "iban3":  ["iban3"],
    "amount": ["راتب", "مبلغ", "دعم", "إجمالي"],
}


def _normalize_header(text: str) -> str:
    """Normalise Arabic header for comparison (strip, lowercase, remove spaces/diacritics)."""
    s = text.strip().lower()
    # Unify common Arabic Unicode variants found in Excel exports
    replacements = {
        "ھ": "ه",  # ھ (Urdu heh) → ه
        "ة": "ه",  # ة (teh marbuta) → ه
        "ی": "ي",  # ی (Farsi yeh) → ي
        "ى": "ي",  # ى (alef maqsura) → ي
        "أ": "ا",  # أ → ا
        "إ": "ا",  # إ → ا
        "آ": "ا",  # آ → ا
    }
    for src, dst in replacements.items():
        s = s.replace(src, dst)
    return s.replace(" ", "")


def _detect_column(col_name: str) -> Optional[str]:
    """Return semantic role for a DataFrame column header, or None."""
    normalized = _normalize_header(col_name)
    for role, keywords in _COL_PATTERNS.items():
        for kw in keywords:
            kw_norm = _normalize_header(kw)
            if kw_norm in normalized:
                return role
    return None


def _clean_amount(val) -> Optional[float]:
    """Parse amounts like '6766.67 ﷼' or '7,000.00' → float."""
    if pd.isna(val):
        return None
    s = re.sub(r"[﷼,\s]", "", str(val))
    try:
        return float(s)
    except ValueError:
        return None


def _clean_nid(val) -> Optional[str]:
    if pd.isna(val):
        return None
    # Floats like 1106949751.0 must be int-cast before stringify
    try:
        s = str(int(float(val)))
    except (ValueError, TypeError):
        s = re.sub(r"\D", "", str(val))
    return s if len(s) == 10 else None


def _clean_iban(val) -> Optional[str]:
    if pd.isna(val):
        return None
    s = re.sub(r"\s", "", str(val)).upper()
    return s if re.match(r"^SA\d{22}$", s) else None


class HadafExcelParser:
    """Parse Hadaf Excel file (.xlsx / .xls) into HadafEmployee list."""

    def parse(self, file_bytes: bytes) -> list[HadafEmployee]:
        try:
            xl = pd.ExcelFile(pd.io.common.BytesIO(file_bytes))
        except Exception as exc:
            logger.error("Failed to open Excel file: %s", exc)
            return []

        all_employees: list[HadafEmployee] = []

        for sheet in xl.sheet_names:
            employees = self._parse_sheet(xl, sheet)
            all_employees.extend(employees)
            if employees:
                logger.info("Sheet '%s': %d employees", sheet, len(employees))

        logger.info("HadafExcelParser: total %d employees", len(all_employees))
        return all_employees

    def _parse_sheet(self, xl: pd.ExcelFile, sheet: str) -> list[HadafEmployee]:
        try:
            # Try reading with header on row 0 first; if no useful columns found,
            # try row 1 (some files have a title row before headers)
            for header_row in (0, 1):
                df = xl.parse(sheet, header=header_row)
                mapping = self._map_columns(df)
                if mapping:
                    return self._extract(df, mapping)
            logger.warning("Sheet '%s': no recognisable columns found", sheet)
            return []
        except Exception as exc:
            logger.error("Error parsing sheet '%s': %s", sheet, exc)
            return []

    def _map_columns(self, df: pd.DataFrame) -> dict[str, str]:
        """Return {role → column_name} for columns we can identify."""
        mapping: dict[str, str] = {}
        for col in df.columns:
            role = _detect_column(str(col))
            if role and role not in mapping:
                mapping[role] = col
        return mapping

    def _extract(self, df: pd.DataFrame, mapping: dict[str, str]) -> list[HadafEmployee]:
        employees: list[HadafEmployee] = []

        for _, row in df.iterrows():
            # Serial is mandatory
            serial_val = row.get(mapping.get("serial", "")) if "serial" in mapping else None
            if pd.isna(serial_val) if serial_val is not None else True:
                continue
            try:
                serial = int(serial_val)
            except (ValueError, TypeError):
                continue

            name_val = row.get(mapping["name"], "") if "name" in mapping else ""
            name = str(name_val).strip() if not pd.isna(name_val) else ""
            if not name:
                continue

            nid_raw   = row.get(mapping["nid"],    None) if "nid"    in mapping else None
            iban_raw  = row.get(mapping["iban"],   None) if "iban"   in mapping else None
            iban2_raw = row.get(mapping["iban2"],  None) if "iban2"  in mapping else None
            iban3_raw = row.get(mapping["iban3"],  None) if "iban3"  in mapping else None
            amt_raw   = row.get(mapping["amount"], None) if "amount" in mapping else None

            employees.append(HadafEmployee(
                serial=serial,
                name_arabic=name,
                national_id=_clean_nid(nid_raw),
                iban=_clean_iban(iban_raw),
                iban2=_clean_iban(iban2_raw),
                iban3=_clean_iban(iban3_raw),
                support_amount=_clean_amount(amt_raw),
            ))

        return employees
