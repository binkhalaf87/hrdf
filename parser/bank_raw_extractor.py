"""
Direct extractor for the bank payroll PDF.

Produces raw BankRawRecord objects that preserve ALL original columns
(serial, reference, name, bank_code, iban, amount) without any header-based
column detection — uses pdfplumber table extraction directly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from io import BytesIO
from typing import Optional

import pdfplumber

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class BankRawRecord:
    bank_serial: str        # م column (1, 2, 3 … per bank group)
    reference: str          # Payment Reference
    name: str               # Employee Name
    bank_code: str          # INMASARIXXX, NCBKSAJEXXX, …
    iban: str               # SA…
    amount_str: str         # SAR 6,301.00  (original string)
    amount: float = 0.0     # parsed float
    bank_label: str = ""    # friendly bank name / group heading


def _parse_amount(s: str) -> float:
    """'SAR 6,301.00' → 6301.0"""
    cleaned = re.sub(r"[^\d.]", "", s)
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _is_employee_table(tbl: list[list]) -> bool:
    """
    Return True when the table contains employee salary rows.
    We expect exactly 6 columns and the second row to contain 'Amount' and 'Employee Name'.
    """
    if not tbl or len(tbl) < 2 or len(tbl[0]) != 6:
        return False
    row1_text = " ".join(str(c) for c in tbl[1] if c)
    return "Amount" in row1_text and "Employee" in row1_text


class BankRawExtractor:
    """
    Extract every salary record from the bank PDF, preserving all 6 columns
    and the bank-group label (bank name) for each section.
    """

    def extract(self, pdf_bytes: bytes) -> list[BankRawRecord]:
        records: list[BankRawRecord] = []
        buf = BytesIO(pdf_bytes)

        with pdfplumber.open(buf) as pdf:
            current_bank_label = ""

            for page_num, page in enumerate(pdf.pages, start=1):
                # Extract the bank label from this page (if any)
                label = self._detect_bank_label(page)
                if label:
                    current_bank_label = label

                for tbl in page.extract_tables():
                    if not _is_employee_table(tbl):
                        continue

                    # cols: Amount | Account Number | Bank Code | Employee Name | Payment Reference | S
                    for row in tbl[2:]:   # skip 2 header rows
                        if not row or not any(row):
                            continue

                        amount_str = str(row[0] or "").strip()
                        iban       = str(row[1] or "").strip()
                        bank_code  = str(row[2] or "").strip()
                        name       = str(row[3] or "").strip().replace("\n", " ")
                        reference  = str(row[4] or "").strip()
                        b_serial   = str(row[5] or "").strip()

                        # Skip summary / total rows
                        if not name or not amount_str.startswith("SAR"):
                            continue

                        records.append(BankRawRecord(
                            bank_serial=b_serial,
                            reference=reference,
                            name=name,
                            bank_code=bank_code,
                            iban=iban,
                            amount_str=amount_str,
                            amount=_parse_amount(amount_str),
                            bank_label=current_bank_label,
                        ))

        logger.info("BankRawExtractor: %d records from %d pages", len(records), len(pdf.pages))
        return records

    @staticmethod
    def _detect_bank_label(page) -> str:
        """
        Look for a 3-row summary table that contains 'Bank name' to capture
        the bank group label for the records on this page.
        """
        for tbl in page.extract_tables():
            if not tbl:
                continue
            for row in tbl:
                row_text = " ".join(str(c) for c in row if c)
                if "Bank name" in row_text:
                    # The bank name cell is beside 'Bank name'
                    for cell in row:
                        s = str(cell or "")
                        if s and "Bank name" not in s and len(s) > 2:
                            # strip Arabic reversed text artefacts
                            return s.strip()
        return ""
