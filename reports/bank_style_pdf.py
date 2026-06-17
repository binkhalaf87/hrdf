"""
Generates a bank-style payroll PDF that reproduces the original bank report layout
but adds the Hadaf serial number as the FIRST column.

Output columns (matches the bank PDF column order + new Hadaf column):
  رقم هدف | م | اسم الموظف | رقم المرجع | رقم الحساب (IBAN) | رمز البنك | المبلغ
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

from parser.bank_raw_extractor import BankRawRecord
from utils.logger import get_logger

logger = get_logger(__name__)


# ── Arabic text helper ─────────────────────────────────────────────────────────

def _ar(text) -> str:
    if not text:
        return ""
    s = str(text)
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(s))
    except Exception:
        return s


def _find_font() -> Optional[str]:
    candidates = [
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\tahoma.ttf",
        r"C:\Windows\Fonts\calibri.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    return None


# ── Colours ───────────────────────────────────────────────────────────────────
_HADAF_HEADER  = "#1F4E79"   # dark blue — Hadaf serial column header
_BANK_HEADER   = "#2E75B6"   # standard blue — rest of headers
_GREEN_BG      = "#C6EFCE"   # matched row
_WHITE_BG      = "#FFFFFF"   # non-Hadaf bank employee
_GREY_ALT      = "#F5F5F5"   # zebra stripe
_HADAF_CELL    = "#70AD47"   # Hadaf serial cell when matched (green)
_GROUP_HDR     = "#D6E4F0"   # bank-group divider row


class BankStylePDFWriter:
    """
    Produces a payroll PDF that mirrors the bank's own table structure but
    adds 'رقم هدف' as the first column before the bank's 'م' column.
    """

    def __init__(self) -> None:
        self._font = self._register_font()

    def _register_font(self) -> str:
        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            p = _find_font()
            if p:
                pdfmetrics.registerFont(TTFont("BFont", p))
                return "BFont"
        except Exception:
            pass
        return "Helvetica"

    # ── Public API ────────────────────────────────────────────────────────────

    def build(
        self,
        bank_records: list[BankRawRecord],
        hadaf_by_iban: dict[str, int],   # IBAN.upper() → Hadaf serial
        company_name: str = "AL BAWANI CO LTD",
        month: str = "أغسطس 2025",
    ) -> bytes:
        """
        Parameters
        ----------
        bank_records    All rows extracted from the bank PDF.
        hadaf_by_iban   Lookup dict {IBAN.upper() → hadaf_serial}.
        company_name    Shown in the PDF title.
        month           Month label shown in the sub-header.

        Returns
        -------
        PDF bytes.
        """
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle,
            Paragraph, Spacer, HRFlowable,
        )

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=landscape(A4),
            rightMargin=1.2 * cm,
            leftMargin=1.2 * cm,
            topMargin=1.8 * cm,
            bottomMargin=1.2 * cm,
        )

        f = self._font

        title_style = ParagraphStyle("T", fontName=f, fontSize=13, alignment=TA_CENTER, spaceAfter=3)
        sub_style   = ParagraphStyle("S", fontName=f, fontSize=9,  alignment=TA_CENTER, spaceAfter=8,
                                     textColor=colors.HexColor("#555555"))
        grp_style   = ParagraphStyle("G", fontName=f, fontSize=9,  alignment=TA_RIGHT)

        # ── Group records by bank ─────────────────────────────────────────────
        groups: dict[str, list[BankRawRecord]] = {}
        for rec in bank_records:
            key = rec.bank_label or rec.bank_code or "Other"
            groups.setdefault(key, []).append(rec)

        # ── Column widths (landscape A4 ≈ 27.7 cm usable) ────────────────────
        # رقم هدف | م | اسم الموظف | رقم المرجع | رقم الحساب | رمز البنك | المبلغ
        col_widths = [2 * cm, 1.5 * cm, 7 * cm, 4.5 * cm, 6.5 * cm, 3.5 * cm, 2.7 * cm]

        total_hadaf = sum(1 for r in bank_records if r.iban and r.iban.upper() in hadaf_by_iban)

        # ── Build elements ────────────────────────────────────────────────────
        elements = [
            Paragraph(_ar(f"كشف الرواتب المُحدَّث — {company_name}"), title_style),
            Paragraph(
                _ar(f"شهر {month}  |  إجمالي سجلات البنك: {len(bank_records)}"
                    f"  |  موظفو هدف المطابَقون: {total_hadaf}"),
                sub_style,
            ),
        ]

        col_headers = [
            _ar("رقم هدف"),
            _ar("م"),
            "Employee Name",
            "Payment Reference",
            "Account Number",
            "Bank Code",
            "Amount",
        ]

        for bank_label, recs in groups.items():
            # ── Bank group divider ────────────────────────────────────────────
            elements.append(Spacer(1, 0.25 * cm))
            elements.append(HRFlowable(width="100%", thickness=0.5,
                                        color=colors.HexColor("#AAAAAA")))
            elements.append(Paragraph(f"  {bank_label}", grp_style))
            elements.append(Spacer(1, 0.15 * cm))

            # ── Table rows ────────────────────────────────────────────────────
            table_data = [col_headers]
            row_meta: list[tuple[bool, int | None]] = []  # (is_hadaf, hadaf_serial)

            for rec in recs:
                iban_up = rec.iban.upper() if rec.iban else ""
                hadaf_serial = hadaf_by_iban.get(iban_up)
                is_hadaf = hadaf_serial is not None

                hadaf_cell = str(hadaf_serial) if is_hadaf else ""

                table_data.append([
                    hadaf_cell,
                    rec.bank_serial,
                    rec.name,
                    rec.reference,
                    rec.iban,
                    rec.bank_code,
                    rec.amount_str,
                ])
                row_meta.append((is_hadaf, hadaf_serial))

            # ── Style commands ────────────────────────────────────────────────
            style_cmds = [
                # Header
                ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor(_BANK_HEADER)),
                ("BACKGROUND",    (0, 0), (0, 0),  colors.HexColor(_HADAF_HEADER)),
                ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
                ("FONTNAME",      (0, 0), (-1, 0), f),
                ("FONTSIZE",      (0, 0), (-1, 0), 9),
                ("FONTNAME",      (0, 1), (-1, -1), f),
                ("FONTSIZE",      (0, 1), (-1, -1), 8),
                ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
                ("ALIGN",         (2, 1), (5, -1),  "LEFT"),    # name/ref/iban/bankcode left
                ("ALIGN",         (-1, 1), (-1, -1), "RIGHT"),  # amount right
                ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#CCCCCC")),
                ("LINEBELOW",     (0, 0), (-1, 0),  1.0, colors.white),
                ("TOPPADDING",    (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING",   (0, 0), (-1, -1), 3),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 3),
                # Zebra for non-Hadaf rows
                *[
                    ("BACKGROUND", (1, i), (-1, i), colors.HexColor(_GREY_ALT))
                    for i in range(2, len(table_data), 2)
                ],
            ]

            for i, (is_hadaf, h_serial) in enumerate(row_meta, start=1):
                if is_hadaf:
                    # Whole row green
                    style_cmds.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor(_GREEN_BG)))
                    # Hadaf serial cell deeper green
                    style_cmds.append(("BACKGROUND", (0, i), (0, i), colors.HexColor(_HADAF_CELL)))
                    style_cmds.append(("TEXTCOLOR",  (0, i), (0, i), colors.white))
                    style_cmds.append(("FONTNAME",   (0, i), (0, i), f))

            tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
            tbl.setStyle(TableStyle(style_cmds))
            elements.append(tbl)

        # ── Legend ────────────────────────────────────────────────────────────
        elements.append(Spacer(1, 0.4 * cm))
        legend = Table([[
            "",
            _ar("■ موظف هدف مطابَق"),
            _ar("□ موظف بنك فقط"),
        ]], colWidths=[3 * cm, 5 * cm, 4 * cm])
        legend.setStyle(TableStyle([
            ("FONTNAME",  (0, 0), (-1, -1), f),
            ("FONTSIZE",  (0, 0), (-1, -1), 8),
            ("ALIGN",     (0, 0), (-1, -1), "RIGHT"),
            ("TEXTCOLOR", (1, 0), (1, 0), colors.HexColor("#375623")),
            ("TEXTCOLOR", (2, 0), (2, 0), colors.HexColor("#555555")),
        ]))
        elements.append(legend)

        doc.build(elements)
        return buf.getvalue()
