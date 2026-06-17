from __future__ import annotations

import io
from typing import Optional

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils.dataframe import dataframe_to_rows

from models import BankEmployee, HadafEmployee, MatchResult, ProcessingSummary
from utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
_GREEN = "C6EFCE"
_YELLOW = "FFEB9C"
_RED = "FFC7CE"
_BLUE = "BDD7EE"
_HEADER_FILL = "2E75B6"
_HEADER_FONT_COLOR = "FFFFFF"


def _apply_header_style(ws, row_num: int = 1) -> None:
    for cell in ws[row_num]:
        cell.font = Font(bold=True, color=_HEADER_FONT_COLOR)
        cell.fill = PatternFill("solid", fgColor=_HEADER_FILL)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _set_column_widths(ws, min_width: int = 12, max_width: int = 40) -> None:
    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(max_len + 2, min_width), max_width)


def _df_to_sheet(
    ws,
    df: pd.DataFrame,
    fill_color: Optional[str] = None,
    rtl: bool = True,
) -> None:
    """Write DataFrame to an openpyxl worksheet with styling."""
    for r_idx, row in enumerate(dataframe_to_rows(df, index=False, header=True), start=1):
        for c_idx, value in enumerate(row, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=value)
            if r_idx == 1:
                pass  # header styled separately
            elif fill_color:
                cell.fill = PatternFill("solid", fgColor=fill_color)
            cell.alignment = Alignment(
                horizontal="right" if rtl else "left",
                vertical="center",
            )

    _apply_header_style(ws)
    _set_column_widths(ws)
    if rtl:
        ws.sheet_view.rightToLeft = True


class ExcelWriter:
    """Generates Excel output files from matching results."""

    def build_matched_excel(self, results: list[MatchResult]) -> bytes:
        df = pd.DataFrame(
            [
                {
                    "الرقم التسلسلي": r.hadaf_serial,
                    "اسم هدف": r.hadaf_name,
                    "اسم البنك": r.bank_name,
                    "الآيبان": r.iban or "",
                    "المبلغ": r.amount,
                    "طريقة المطابقة": r.match_method,
                    "نسبة الثقة %": r.confidence,
                }
                for r in results
            ]
        )
        return self._write_single_sheet(df, "المطابقات", fill_color=_GREEN)

    def build_review_excel(self, results: list[MatchResult]) -> bytes:
        df = pd.DataFrame(
            [
                {
                    "اسم البنك": r.bank_name,
                    "الآيبان": r.iban or "",
                    "المبلغ": r.amount,
                    "الاسم المقترح (هدف)": r.hadaf_name,
                    "الرقم التسلسلي المقترح": r.hadaf_serial,
                    "طريقة المطابقة": r.match_method,
                    "نسبة الثقة %": r.confidence,
                }
                for r in results
            ]
        )
        return self._write_single_sheet(df, "للمراجعة", fill_color=_YELLOW)

    def build_unmatched_excel(self, unmatched: list[BankEmployee]) -> bytes:
        df = pd.DataFrame(
            [
                {
                    "اسم البنك": e.name,
                    "الآيبان": e.iban or "",
                    "المبلغ": e.amount,
                    "رقم المرجع": e.reference or "",
                }
                for e in unmatched
            ]
        )
        return self._write_single_sheet(df, "غير مطابق", fill_color=_RED)

    def build_summary_excel(
        self,
        summary: ProcessingSummary,
        hadaf_employees: list[HadafEmployee],
        bank_employees: list[BankEmployee],
        matched: list[MatchResult],
        review: list[MatchResult],
        unmatched_bank: list[BankEmployee],
    ) -> bytes:
        wb = Workbook()
        wb.remove(wb.active)  # remove default sheet

        # ---- Summary sheet ----
        ws_summary = wb.create_sheet("ملخص")
        ws_summary.sheet_view.rightToLeft = True

        summary_data = [
            ("البيان", "القيمة"),
            ("إجمالي موظفي هدف", summary.total_hadaf),
            ("إجمالي موظفي البنك", summary.total_bank),
            ("المطابقات الناجحة", summary.matched),
            ("تحتاج مراجعة", summary.review_required),
            ("غير مطابق", summary.unmatched),
            ("نسبة النجاح %", f"{summary.success_rate:.2f}%"),
        ]
        fills = [_HEADER_FILL, _GREEN, _BLUE, _GREEN, _YELLOW, _RED, _GREEN]
        for row_idx, (label, value) in enumerate(summary_data, start=1):
            cell_a = ws_summary.cell(row=row_idx, column=1, value=label)
            cell_b = ws_summary.cell(row=row_idx, column=2, value=value)
            if row_idx == 1:
                for cell in (cell_a, cell_b):
                    cell.font = Font(bold=True, color=_HEADER_FONT_COLOR)
                    cell.fill = PatternFill("solid", fgColor=_HEADER_FILL)
            else:
                for cell in (cell_a, cell_b):
                    cell.fill = PatternFill("solid", fgColor=fills[row_idx - 1])
            for cell in (cell_a, cell_b):
                cell.alignment = Alignment(horizontal="right", vertical="center")

        ws_summary.column_dimensions["A"].width = 30
        ws_summary.column_dimensions["B"].width = 20

        # ---- Method breakdown ----
        ws_methods = wb.create_sheet("طرق المطابقة")
        ws_methods.sheet_view.rightToLeft = True
        all_results = matched + review
        if all_results:
            method_counts = (
                pd.DataFrame([{"method": r.match_method} for r in all_results])
                .groupby("method")
                .size()
                .reset_index(name="count")
            )
            method_counts.columns = ["طريقة المطابقة", "العدد"]
            _df_to_sheet(ws_methods, method_counts, fill_color=_BLUE)

        buffer = io.BytesIO()
        wb.save(buffer)
        return buffer.getvalue()

    @staticmethod
    def _write_single_sheet(df: pd.DataFrame, sheet_name: str, fill_color: str) -> bytes:
        wb = Workbook()
        wb.remove(wb.active)
        ws = wb.create_sheet(sheet_name)
        _df_to_sheet(ws, df, fill_color=fill_color)
        buffer = io.BytesIO()
        wb.save(buffer)
        return buffer.getvalue()
