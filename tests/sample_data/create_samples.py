"""
Generate sample PDF files for testing the matching system.
Uses reportlab for proper Arabic Unicode support.

Usage:
    python tests/sample_data/create_samples.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

SAMPLE_HADAF = [
    (1,  "عساف عبدالرحمن الرشيدي",    "1234567890"),
    (2,  "محمد أحمد الزهراني",          "1098765432"),
    (3,  "خالد عبدالله السبيعي",        "1122334455"),
    (4,  "سعد بن سلمان العتيبي",        "1566778899"),
    (5,  "عبدالعزيز محمد القحطاني",     "1987654321"),
    (6,  "فيصل عمر البقمي",             "1234509876"),
    (7,  "عمر سعيد الغامدي",            "1098712345"),
    (8,  "نواف حسن الشمري",             "1112233445"),
    (9,  "طارق ابن عبدالله الحربي",     "1556677889"),
    (10, "يوسف إبراهيم الدوسري",        "1999888777"),
]

# Tuple: (name, iban, amount, ref, national_id_for_bank)
# NIDs for first 4 employees match Hadaf → triggers Stage 1 (100% confidence)
# Employees 5-6 have Arabic names → Stage 3 exact match
# Employees 7-9 English names only → Stage 5 transliteration (review)
# Employee 10 → unmatched
SAMPLE_BANK = [
    ("ASSAF ABDULRAHMAN ALRASHIDI",   "SA1234567890123456789012", 6121.00, "REF001", "1234567890"),
    ("MOHAMMED AHMED ALZAHRANI",       "SA0987654321098765432109", 6500.00, "REF002", "1098765432"),
    ("KHALED ABDALLAH ALSUBAIEE",      "SA1122334455112233445511", 7200.00, "REF003", "1122334455"),
    ("SAAD BIN SALMAN ALOTAIBI",       "SA5566778899556677889955", 5800.00, "REF004", "1566778899"),
    ("عبدالعزيز محمد القحطاني",        "SA9876543219876543219876", 8100.00, "REF005", ""),
    ("فيصل عمر البقمي",                "SA2345098762345098762345", 6300.00, "REF006", ""),
    ("OMAR SAEED ALGHAMDI",            "SA0987123450987123450987", 7500.00, "REF007", ""),
    ("NAWAF HASSAN ALSHAMMARI",        "SA1122334451122334451122", 6900.00, "REF008", ""),
    ("TARIQ ABDALLAH ALHARBI",         "SA5566778855566778855566", 7100.00, "REF009", ""),
    # Intentionally unmatched — should appear in unmatched.xlsx
    ("AHMED UNKNOWN EMPLOYEE",         "SA0000000000000000000000", 5000.00, "REF010", ""),
]


def _find_arabic_font() -> str | None:
    """Find an Arabic-capable TTF font on the system."""
    candidates = [
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\tahoma.ttf",
        r"C:\Windows\Fonts\times.ttf",
        r"C:\Windows\Fonts\calibri.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    return None


def create_hadaf_pdf(output_path: Path) -> None:
    """Create Hadaf PDF with Arabic employee data using reportlab."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT

    # Register Arabic font
    font_path = _find_arabic_font()
    arabic_font = "Helvetica"
    if font_path:
        try:
            pdfmetrics.registerFont(TTFont("Arabic", font_path))
            arabic_font = "Arabic"
        except Exception:
            pass

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "title",
        parent=styles["Normal"],
        fontName=arabic_font,
        fontSize=14,
        alignment=TA_CENTER,
        spaceAfter=12,
    )
    cell_style = ParagraphStyle(
        "cell",
        parent=styles["Normal"],
        fontName=arabic_font,
        fontSize=10,
        alignment=TA_RIGHT,
    )

    elements = [
        Paragraph("قائمة موظفي برنامج هدف - Hadaf Employee List", title_style),
        Spacer(1, 0.3 * cm),
    ]

    # Table header + data
    table_data = [["م", "اسم الموظف", "رقم الهوية"]]
    for serial, name, nid in SAMPLE_HADAF:
        table_data.append([str(serial), name, nid])

    col_widths = [2 * cm, 11 * cm, 5 * cm]
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E75B6")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, -1), arabic_font),
            ("FONTSIZE", (0, 0), (-1, 0), 11),
            ("FONTSIZE", (0, 1), (-1, -1), 10),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("ALIGN", (1, 1), (1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EEF3F9")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ])
    )
    elements.append(table)

    doc.build(elements)
    print(f"✅ Hadaf PDF created: {output_path}")


def create_bank_pdf(output_path: Path) -> None:
    """Create Bank payroll PDF using reportlab."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT

    font_path = _find_arabic_font()
    arabic_font = "Helvetica"
    if font_path:
        try:
            pdfmetrics.registerFont(TTFont("ArabicBank", font_path))
            arabic_font = "ArabicBank"
        except Exception:
            pass

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=landscape(A4),
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "title",
        parent=styles["Normal"],
        fontName=arabic_font,
        fontSize=13,
        alignment=TA_CENTER,
        spaceAfter=12,
    )

    elements = [
        Paragraph("Bank Payroll Statement - Monthly Salary Transfer / كشف رواتب البنك", title_style),
        Spacer(1, 0.3 * cm),
    ]

    headers = ["Employee Name / اسم الموظف", "IBAN / الآيبان", "Amount SAR / المبلغ", "Reference / المرجع", "National ID / رقم الهوية"]
    table_data = [headers]
    for name, iban, amount, ref, nid in SAMPLE_BANK:
        table_data.append([name, iban, f"{amount:,.2f}", ref, nid or "N/A"])

    col_widths = [6.5 * cm, 6.5 * cm, 3 * cm, 2.5 * cm, 4 * cm]
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, -1), arabic_font),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#DEEAF1")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ])
    )
    elements.append(table)
    doc.build(elements)
    print(f"✅ Bank PDF created: {output_path}")


if __name__ == "__main__":
    out_dir = Path(__file__).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Generating sample PDF files...")
    create_hadaf_pdf(out_dir / "sample_hadaf.pdf")
    create_bank_pdf(out_dir / "sample_bank.pdf")
    print(f"\nDone! Files are in: {out_dir}")
    print("Use these files to test the Streamlit app at: streamlit run app.py")
