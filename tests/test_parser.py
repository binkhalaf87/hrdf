"""Unit tests for PDF parsers using synthetic data."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from parser.pdf_utils import detect_pdf_type, clean_cell
from parser.hadaf_parser import _parse_table as hadaf_parse_table, _parse_from_text as hadaf_parse_text
from parser.bank_parser import _parse_table as bank_parse_table, _parse_from_text as bank_parse_text


SAMPLE_HADAF_TABLE = [
    ["م", "اسم الموظف", "رقم الهوية"],
    ["1", "عساف عبدالرحمن الرشيدي", "1234567890"],
    ["2", "محمد أحمد الزهراني", "1098765432"],
    ["3", "خالد عبدالله السبيعي", "1122334455"],
    ["", "", ""],  # empty row — should be skipped
]

SAMPLE_BANK_TABLE = [
    ["Employee Name", "IBAN", "Amount", "Reference", "Serial"],
    ["ASSAF ABDULRAHMAN ALRASHIDI", "SA1234567890123456789012", "6121.00", "REF001", "N/A"],
    ["MOHAMMED AHMED ALZAHRANI", "SA0987654321098765432109", "6500.00", "REF002", ""],
    ["عبدالعزيز محمد القحطاني", "SA9876543219876543219876", "8100.00", "REF003", "5"],
]

SAMPLE_HADAF_TEXT = """
Hadaf Report
1 عساف عبدالرحمن الرشيدي 1234567890
2 محمد أحمد الزهراني 1098765432
3 خالد عبدالله السبيعي
"""

SAMPLE_BANK_TEXT = """
Bank Payroll
ASSAF ABDULRAHMAN ALRASHIDI SA1234567890123456789012 6121.00 REF001
UNKNOWN EMPLOYEE SA9999999999999999999999 5000.00 REF999
"""


class TestHadafParser:
    def test_parse_table_basic(self):
        employees = hadaf_parse_table(SAMPLE_HADAF_TABLE)
        assert len(employees) == 3

    def test_parse_table_serials(self):
        employees = hadaf_parse_table(SAMPLE_HADAF_TABLE)
        serials = [e.serial for e in employees]
        assert serials == [1, 2, 3]

    def test_parse_table_names(self):
        employees = hadaf_parse_table(SAMPLE_HADAF_TABLE)
        assert employees[0].name_arabic == "عساف عبدالرحمن الرشيدي"

    def test_parse_table_national_ids(self):
        employees = hadaf_parse_table(SAMPLE_HADAF_TABLE)
        assert employees[0].national_id == "1234567890"
        assert employees[1].national_id == "1098765432"

    def test_parse_table_empty_row_skipped(self):
        employees = hadaf_parse_table(SAMPLE_HADAF_TABLE)
        assert len(employees) == 3  # empty row skipped

    def test_parse_from_text(self):
        employees = hadaf_parse_text(SAMPLE_HADAF_TEXT.strip())
        assert len(employees) >= 2

    def test_parse_from_text_nid_extracted(self):
        employees = hadaf_parse_text(SAMPLE_HADAF_TEXT.strip())
        emp_with_nid = [e for e in employees if e.national_id]
        assert len(emp_with_nid) >= 2

    def test_empty_table_returns_empty(self):
        assert hadaf_parse_table([]) == []
        assert hadaf_parse_table([["م", "اسم الموظف"]]) == []


class TestBankParser:
    def test_parse_table_basic(self):
        employees = bank_parse_table(SAMPLE_BANK_TABLE)
        assert len(employees) == 3

    def test_parse_table_iban_extracted(self):
        employees = bank_parse_table(SAMPLE_BANK_TABLE)
        assert employees[0].iban == "SA1234567890123456789012"

    def test_parse_table_amount_parsed(self):
        employees = bank_parse_table(SAMPLE_BANK_TABLE)
        assert employees[0].amount == 6121.0
        assert employees[1].amount == 6500.0

    def test_parse_table_serial_extracted(self):
        employees = bank_parse_table(SAMPLE_BANK_TABLE)
        assert employees[2].serial == 5

    def test_parse_table_na_serial_is_none(self):
        employees = bank_parse_table(SAMPLE_BANK_TABLE)
        assert employees[0].serial is None

    def test_parse_from_text_iban(self):
        employees = bank_parse_text(SAMPLE_BANK_TEXT.strip())
        assert len(employees) >= 1
        ibans = [e.iban for e in employees]
        assert "SA1234567890123456789012" in ibans

    def test_empty_table_returns_empty(self):
        assert bank_parse_table([]) == []


class TestPdfUtils:
    def test_clean_cell_strips_whitespace(self):
        assert clean_cell("  hello  ") == "hello"

    def test_clean_cell_collapses_spaces(self):
        assert clean_cell("hello   world") == "hello world"

    def test_clean_cell_none_returns_empty(self):
        assert clean_cell(None) == ""

    def test_clean_cell_empty_string(self):
        assert clean_cell("") == ""
