"""
PDF Overlay — adds Hadaf serial number to the original bank PDF.

Strategy:
  1. Open the original PDF with PyMuPDF (fitz).
  2. On each employee-data page, locate every IBAN string (SA + 22 digits).
  3. For each IBAN row, look up the Hadaf serial via the IBAN lookup dict.
  4. Overlay the serial number in the RIGHT MARGIN (x ≈ 548–588) at the
     same vertical centre as the IBAN text — no existing content is touched.
  5. On the first employee row of each page-section, also overlay a small
     "هدف#" header in the same margin column.

The original PDF structure, fonts, and layout are 100% preserved.
"""
from __future__ import annotations

import re
from io import BytesIO
from typing import Optional

import fitz   # PyMuPDF

from utils.logger import get_logger

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
_IBAN_RE      = re.compile(r"SA\d{22}")
_OVERLAY_X0   = 548.0   # right of the existing "م" column
_OVERLAY_X1   = 590.0
_FONT         = "helv"  # built-in Helvetica (numbers only — no Arabic needed)
_TEXT_COLOR   = (0.78, 0.0, 0.0)   # red — distinguishes the added Hadaf serial


class PDFOverlayWriter:
    """
    Overlays Hadaf serial numbers onto the original bank PDF without
    rebuilding any page content.
    """

    def overlay(
        self,
        pdf_bytes: bytes,
        hadaf_by_iban: dict[str, int],   # IBAN.upper() → hadaf_serial
    ) -> bytes:
        """
        Parameters
        ----------
        pdf_bytes       Original bank PDF bytes.
        hadaf_by_iban   {IBAN.upper() → hadaf_serial} lookup.

        Returns
        -------
        Modified PDF bytes with Hadaf serials overlaid in the right margin.
        """
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        total_overlaid = 0

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            n = self._overlay_page(page, hadaf_by_iban)
            total_overlaid += n

        logger.info("PDFOverlayWriter: overlaid %d serial numbers", total_overlaid)

        buf = BytesIO()
        doc.save(buf, garbage=4, deflate=True)
        doc.close()
        return buf.getvalue()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _overlay_page(
        self,
        page: fitz.Page,
        hadaf_by_iban: dict[str, int],
    ) -> int:
        """
        Scan the page for IBAN text, match with Hadaf data, overlay serial.
        Returns the number of serials overlaid on this page.
        Plain text only — no header, no colours, no boxes.
        """
        # Extract all words with their bounding boxes
        words = page.get_text("words")   # (x0, y0, x1, y1, text, ...)

        # Collect IBAN words on this page with the row's font height
        iban_rows: list[tuple[float, float, str]] = []   # (y_mid, row_height, iban)
        for w in words:
            x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4]
            if _IBAN_RE.fullmatch(text.strip()):
                y_mid = (y0 + y1) / 2
                row_h = y1 - y0
                iban_rows.append((y_mid, row_h, text.strip()))

        if not iban_rows:
            return 0

        overlaid = 0
        for y_mid, row_h, iban in iban_rows:
            serial = hadaf_by_iban.get(iban.upper())
            if serial is None:
                continue
            self._draw_serial(page, y_mid, row_h, str(serial))
            overlaid += 1

        return overlaid

    # ── Drawing helper ──────────────────────────────────────────────────────

    def _draw_serial(
        self,
        page: fitz.Page,
        y_mid: float,
        row_h: float,
        text: str,
    ) -> None:
        """
        Overlay the Hadaf serial as plain black text in the right margin,
        font size scaled to the row height, vertically centred — matching
        the look of the existing row text. No header, no colour, no box.
        """
        # Scale the font to the row height (existing rows ≈ 8pt for ~8px height)
        font_size = max(6.0, min(9.0, row_h))
        # Baseline ≈ vertical centre + ~⅓ of font size
        baseline_y = y_mid + font_size * 0.35
        page.insert_text(
            fitz.Point(_OVERLAY_X0 + 2, baseline_y),
            text,
            fontname=_FONT, fontsize=font_size,
            color=_TEXT_COLOR,
        )
