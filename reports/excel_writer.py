from __future__ import annotations

import io

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils.dataframe import dataframe_to_rows

from models import BankEmployee, BankReportRow, HadafEmployee, MatchResult, ProcessingSummary
from utils.logger import get_logger

logger = get_logger(__name__)

_GREEN  = "C6EFCE"
_YELLOW = "FFEB9C"
_RED    = "FFC7CE"
_BLUE   = "BDD7EE"
_ORANGE = "FCE4D6"
_HEADER_BG    = "2E75B6"
_HEADER_FONT  = "FFFFFF"


def _style_header(ws, row: int = 1) -> None:
    for cell in ws[row]:
        cell.font = Font(bold=True, color=_HEADER_FONT)
        cell.fill = PatternFill("solid", fgColor=_HEADER_BG)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _col_widths(ws, mn: int = 10, mx: int = 40) -> None:
    for col in ws.columns:
        w = max(len(str(c.value or "")) for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(w + 2, mn), mx)


def _write_df(ws, df: pd.DataFrame, fill: str = "", rtl: bool = True) -> None:
    for r, row in enumerate(dataframe_to_rows(df, index=False, header=True), start=1):
        for c, val in enumerate(row, start=1):
            cell = ws.cell(row=r, column=c, value=val)
            cell.alignment = Alignment(horizontal="right" if rtl else "left", vertical="center")
            if r > 1 and fill:
                cell.fill = PatternFill("solid", fgColor=fill)
    _style_header(ws)
    _col_widths(ws)
    if rtl:
        ws.sheet_view.rightToLeft = True


def _to_bytes(wb: Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class ExcelWriter:

    # ------------------------------------------------------------------ #
    #  تقرير البنك المُحدَّث — الأهم                                      #
    # ------------------------------------------------------------------ #
    def build_bank_report_excel(self, rows: list[BankReportRow]) -> bytes:
        """
        تقرير البنك الكامل:
        - كل سجلات البنك
        - مع الرقم التسلسلي لهدف لكل موظف مطابق
        - مقارنة المبالغ
        ملوّن حسب الحالة: أخضر=مطابق، أصفر=مراجعة، أحمر=غير مطابق
        """
        wb = Workbook()
        wb.remove(wb.active)
        ws = wb.create_sheet("تقرير البنك المُحدَّث")
        ws.sheet_view.rightToLeft = True

        headers = [
            "اسم الموظف (البنك)",
            "الرقم التسلسلي (هدف)",
            "اسم الموظف (هدف)",
            "الآيبان",
            "المبلغ المحوَّل (البنك)",
            "مبلغ هدف",
            "الفرق",
            "طريقة المطابقة",
            "نسبة الثقة %",
            "الحالة",
            "رقم المرجع",
        ]

        status_fill = {
            "matched":   _GREEN,
            "review":    _YELLOW,
            "bank_only": _RED,
        }

        for r_idx, row in enumerate([headers] + [None] * len(rows), start=1):
            if r_idx == 1:
                for c_idx, h in enumerate(headers, start=1):
                    cell = ws.cell(row=1, column=c_idx, value=h)
                    cell.font = Font(bold=True, color=_HEADER_FONT)
                    cell.fill = PatternFill("solid", fgColor=_HEADER_BG)
                    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            else:
                brow = rows[r_idx - 2]
                fill = PatternFill("solid", fgColor=status_fill.get(brow.status, "FFFFFF"))
                values = [
                    brow.bank_name,
                    brow.hadaf_serial,
                    brow.hadaf_name or "",
                    brow.iban or "",
                    brow.bank_amount,
                    brow.hadaf_support_amount if brow.hadaf_support_amount is not None else "",
                    brow.amount_diff if brow.amount_diff is not None else "",
                    brow.match_method or "",
                    f"{brow.confidence:.1f}%" if brow.confidence is not None else "",
                    self._status_label(brow.status),
                    brow.reference or "",
                ]
                for c_idx, val in enumerate(values, start=1):
                    cell = ws.cell(row=r_idx, column=c_idx, value=val)
                    cell.fill = fill
                    cell.alignment = Alignment(horizontal="right", vertical="center")

        _col_widths(ws)
        return _to_bytes(wb)

    # ------------------------------------------------------------------ #
    #  ملفات المطابقة التفصيلية                                           #
    # ------------------------------------------------------------------ #
    def build_matched_excel(self, results: list[MatchResult]) -> bytes:
        df = pd.DataFrame([{
            "الرقم التسلسلي (هدف)": r.hadaf_serial,
            "اسم هدف": r.hadaf_name,
            "اسم البنك": r.bank_name,
            "الآيبان": r.iban or "",
            "المبلغ (البنك)": r.bank_amount,
            "مبلغ هدف": r.hadaf_support_amount if r.hadaf_support_amount else "",
            "الفرق": r.amount_diff if r.amount_diff is not None else "",
            "طريقة المطابقة": r.match_method,
            "نسبة الثقة %": r.confidence,
        } for r in results])
        return self._single(df, "المطابقات", _GREEN)

    def build_review_excel(self, results: list[MatchResult]) -> bytes:
        df = pd.DataFrame([{
            "اسم البنك": r.bank_name,
            "الاسم المقترح (هدف)": r.hadaf_name,
            "الرقم التسلسلي المقترح": r.hadaf_serial,
            "الآيبان": r.iban or "",
            "المبلغ (البنك)": r.bank_amount,
            "مبلغ هدف": r.hadaf_support_amount if r.hadaf_support_amount else "",
            "الفرق": r.amount_diff if r.amount_diff is not None else "",
            "طريقة المطابقة": r.match_method,
            "نسبة الثقة %": r.confidence,
        } for r in results])
        return self._single(df, "للمراجعة", _YELLOW)

    def build_unmatched_excel(self, unmatched: list[BankEmployee]) -> bytes:
        df = pd.DataFrame([{
            "اسم البنك": e.name,
            "الآيبان": e.iban or "",
            "المبلغ": e.amount,
            "رقم المرجع": e.reference or "",
        } for e in unmatched])
        return self._single(df, "غير مطابق", _RED)

    def build_hadaf_not_in_bank_excel(self, employees: list[HadafEmployee]) -> bytes:
        """موظفو هدف الذين لم ينزل راتبهم."""
        df = pd.DataFrame([{
            "الرقم التسلسلي": e.serial,
            "اسم الموظف": e.name_arabic,
            "رقم الهوية": e.national_id or "",
            "الآيبان": e.iban or "",
            "مبلغ هدف": e.support_amount if e.support_amount else "",
        } for e in employees])
        return self._single(df, "هدف غير موجود بالبنك", _ORANGE)

    def build_summary_excel(
        self,
        summary: ProcessingSummary,
        matched: list[MatchResult],
        review: list[MatchResult],
    ) -> bytes:
        wb = Workbook()
        wb.remove(wb.active)

        # Sheet 1: ملخص أرقام
        ws = wb.create_sheet("ملخص")
        ws.sheet_view.rightToLeft = True
        rows = [
            ("البيان", "القيمة"),
            ("إجمالي موظفي هدف", summary.total_hadaf),
            ("إجمالي سجلات البنك", summary.total_bank),
            ("مطابق بنجاح ✅", summary.matched),
            ("تحتاج مراجعة ⚠️", summary.review_required),
            ("غير مطابق ❌", summary.unmatched),
            ("موظفو هدف لم ينزل راتبهم", summary.hadaf_not_in_bank),
            ("نسبة النجاح", f"{summary.success_rate:.1f}%"),
        ]
        fills_by_row = {
            1: _HEADER_BG,
            3: _GREEN, 4: _GREEN,
            5: _YELLOW,
            6: _RED,
            7: _ORANGE,
            8: _GREEN,
        }
        for r, (label, val) in enumerate(rows, start=1):
            ca = ws.cell(row=r, column=1, value=label)
            cb = ws.cell(row=r, column=2, value=val)
            bg = fills_by_row.get(r, "FFFFFF")
            for cell in (ca, cb):
                cell.fill = PatternFill("solid", fgColor=bg)
                cell.alignment = Alignment(horizontal="right", vertical="center")
                if r == 1:
                    cell.font = Font(bold=True, color=_HEADER_FONT)
        ws.column_dimensions["A"].width = 35
        ws.column_dimensions["B"].width = 20

        # Sheet 2: طرق المطابقة
        if matched or review:
            ws2 = wb.create_sheet("طرق المطابقة")
            ws2.sheet_view.rightToLeft = True
            all_r = matched + review
            df = (pd.DataFrame([{"method": r.match_method} for r in all_r])
                  .groupby("method").size().reset_index(name="count"))
            df.columns = ["طريقة المطابقة", "العدد"]
            _write_df(ws2, df, fill=_BLUE)

        return _to_bytes(wb)

    @staticmethod
    def _status_label(status: str) -> str:
        return {"matched": "مطابق ✅", "review": "يحتاج مراجعة ⚠️",
                "bank_only": "غير مطابق ❌"}.get(status, status)

    @staticmethod
    def _single(df: pd.DataFrame, sheet: str, fill: str) -> bytes:
        wb = Workbook()
        wb.remove(wb.active)
        ws = wb.create_sheet(sheet)
        _write_df(ws, df, fill=fill)
        return _to_bytes(wb)
