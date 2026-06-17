"""
PDF report generator — produces a bank-style payroll PDF
with the Hadaf serial number added as the first column.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

from models import BankReportRow
from utils.logger import get_logger

logger = get_logger(__name__)

# ── Arabic text helpers ───────────────────────────────────────────────────────

def _ar(text) -> str:
    """Reshape + bidi Arabic text so reportlab renders it correctly RTL."""
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
    """Return path to first available Arabic-capable TTF on this system."""
    candidates = [
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\tahoma.ttf",
        r"C:\Windows\Fonts\calibri.ttf",
        r"C:\Windows\Fonts\times.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    return None


# ── Colours ───────────────────────────────────────────────────────────────────
_C_HEADER_DARK  = "#1F4E79"   # عمود رقم هدف
_C_HEADER_MAIN  = "#2E75B6"   # باقي الأعمدة
_C_GREEN        = "#C6EFCE"
_C_YELLOW       = "#FFEB9C"
_C_RED          = "#FFC7CE"
_C_WHITE        = "#FFFFFF"


class PDFWriter:
    """Generates a styled PDF payroll report with Hadaf serial as first column."""

    def __init__(self) -> None:
        self._font = self._register_font()

    def _register_font(self) -> str:
        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont

            path = _find_font()
            if path:
                pdfmetrics.registerFont(TTFont("ArFont", path))
                logger.info("PDF font registered: %s", path)
                return "ArFont"
        except Exception as exc:
            logger.warning("Font registration failed: %s — using Helvetica", exc)
        return "Helvetica"

    # ── Public API ────────────────────────────────────────────────────────────

    def build_bank_report_pdf(
        self,
        rows: list[BankReportRow],
        title: str = "كشف الرواتب المُحدَّث",
        month: str = "",
    ) -> bytes:
        """
        Return PDF bytes.

        Layout:
          Col 0 : رقم هدف   ← العمود المضاف (أزرق داكن)
          Col 1 : اسم الموظف
          Col 2 : الآيبان
          Col 3 : المبلغ
          Col 4 : رقم المرجع

        Row colours:
          أخضر  = مطابق تام
          أصفر  = يحتاج مراجعة (رقم هدف + علامة ؟)
          أحمر  = غير مطابق (خلية رقم هدف فارغة)
        """
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle,
            Paragraph, Spacer, HRFlowable,
        )
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=landscape(A4),
            rightMargin=1.5 * cm,
            leftMargin=1.5 * cm,
            topMargin=2 * cm,
            bottomMargin=1.5 * cm,
            title=title,
        )

        f = self._font

        title_style = ParagraphStyle(
            "title", fontName=f, fontSize=14,
            alignment=TA_CENTER, spaceAfter=4,
        )
        sub_style = ParagraphStyle(
            "sub", fontName=f, fontSize=9,
            alignment=TA_CENTER, spaceAfter=10, textColor=colors.HexColor("#555555"),
        )

        # ── Build table rows ──────────────────────────────────────────────────
        col_headers = [
            _ar("رقم هدف"),
            _ar("اسم الموظف"),
            _ar("الآيبان"),
            _ar("المبلغ"),
            _ar("رقم المرجع"),
        ]
        table_data = [col_headers]
        row_statuses: list[str] = []

        for row in rows:
            if row.status == "matched":
                serial_cell = str(row.hadaf_serial)
            elif row.status == "review":
                serial_cell = f"{row.hadaf_serial} ؟"
            else:
                serial_cell = ""

            table_data.append([
                serial_cell,
                _ar(row.bank_name),
                row.iban or "",
                f"{row.bank_amount:,.2f}" if row.bank_amount else "",
                row.reference or "",
            ])
            row_statuses.append(row.status)

        # ── Column widths (landscape A4 ≈ 27.7 cm usable) ───────────────────
        col_widths = [2.5 * cm, 9 * cm, 6.5 * cm, 3.5 * cm, 4 * cm]

        # ── Table styles ──────────────────────────────────────────────────────
        style_cmds = [
            # Header row
            ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor(_C_HEADER_MAIN)),
            ("BACKGROUND",   (0, 0), (0, 0),  colors.HexColor(_C_HEADER_DARK)),
            ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
            ("FONTNAME",     (0, 0), (-1, 0), f),
            ("FONTSIZE",     (0, 0), (-1, 0), 10),
            ("FONTNAME",     (0, 1), (-1, -1), f),
            ("FONTSIZE",     (0, 1), (-1, -1), 9),
            ("ALIGN",        (0, 0), (-1, -1), "RIGHT"),
            ("ALIGN",        (0, 0), (0, -1),  "CENTER"),   # عمود رقم هدف وسط
            ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
            ("GRID",         (0, 0), (-1, -1), 0.4, colors.HexColor("#AAAAAA")),
            ("LINEBELOW",    (0, 0), (-1, 0),  1.2, colors.white),
            ("TOPPADDING",   (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
            ("LEFTPADDING",  (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            # Zebra rows (light grey for even data rows)
            *[
                ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F5F5F5"))
                for i in range(2, len(table_data), 2)
            ],
        ]

        # Row colour by match status
        _fill = {
            "matched":   colors.HexColor(_C_GREEN),
            "review":    colors.HexColor(_C_YELLOW),
            "bank_only": colors.HexColor(_C_RED),
        }
        for i, status in enumerate(row_statuses, start=1):
            fill = _fill.get(status)
            if fill:
                style_cmds.append(("BACKGROUND", (0, i), (-1, i), fill))
            # رقم هدف column always slightly darker tint when matched
            if status == "matched":
                style_cmds.append(
                    ("BACKGROUND", (0, i), (0, i), colors.HexColor("#70AD47"))
                )
                style_cmds.append(
                    ("TEXTCOLOR",  (0, i), (0, i), colors.white)
                )
                style_cmds.append(
                    ("FONTNAME",   (0, i), (0, i), f)
                )

        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle(style_cmds))

        # ── Legend ────────────────────────────────────────────────────────────
        legend_data = [[
            "",
            _ar("■ مطابق تام"),
            _ar("■ يحتاج مراجعة"),
            _ar("■ غير مطابق"),
        ]]
        legend = Table(legend_data, colWidths=[3*cm, 4*cm, 4.5*cm, 4*cm])
        legend.setStyle(TableStyle([
            ("FONTNAME",   (0, 0), (-1, -1), f),
            ("FONTSIZE",   (0, 0), (-1, -1), 8),
            ("ALIGN",      (0, 0), (-1, -1), "RIGHT"),
            ("TEXTCOLOR",  (1, 0), (1, 0), colors.HexColor("#375623")),
            ("TEXTCOLOR",  (2, 0), (2, 0), colors.HexColor("#7D6608")),
            ("TEXTCOLOR",  (3, 0), (3, 0), colors.HexColor("#9C0006")),
        ]))

        subtitle = f"{month}  |  إجمالي السجلات: {len(rows)}" if month else f"إجمالي السجلات: {len(rows)}"

        elements = [
            Paragraph(_ar(title), title_style),
            Paragraph(_ar(subtitle), sub_style),
            legend,
            Spacer(1, 0.3 * cm),
            table,
        ]

        doc.build(elements)
        return buf.getvalue()
