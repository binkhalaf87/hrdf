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
_HDR_COLOR    = (0.12, 0.31, 0.47)   # #1F4E79 dark blue
_MATCH_COLOR  = (0.44, 0.68, 0.28)   # #70AD47 green
_FONT         = "helv"               # built-in Helvetica (no Arabic needed — numbers only)
_FONT_SIZE    = 8.0
_HDR_SIZE     = 7.5


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
        """
        # Extract all words with their bounding boxes
        words = page.get_text("words")   # (x0, y0, x1, y1, text, ...)

        # Collect IBAN words on this page
        iban_rows: list[tuple[float, float, str]] = []   # (y_mid, x0, iban)
        for w in words:
            x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4]
            if _IBAN_RE.fullmatch(text.strip()):
                y_mid = (y0 + y1) / 2
                iban_rows.append((y_mid, x0, text.strip()))

        if not iban_rows:
            return 0

        # Sort top-to-bottom
        iban_rows.sort(key=lambda r: r[0])

        # Detect header rows to add column header "هدف#" above first data row
        # We add it once per table section (when we see the first IBAN row
        # following the column headers "م"/"S")
        header_y_positions = set()
        for w in words:
            text = w[4].strip()
            if text in ("S", "ﻡ", "م"):
                header_y_positions.add(round(w[1], 1))   # y0 of "S"/"م" header

        overlaid = 0
        header_drawn: set[float] = set()

        for y_mid, x0, iban in iban_rows:
            serial = hadaf_by_iban.get(iban.upper())

            # Draw column header "هدف" the first time we see an IBAN row
            # below a known header row
            for hy in header_y_positions:
                if y_mid > hy and round(hy, 0) not in header_drawn:
                    self._draw_header(page, hy)
                    header_drawn.add(round(hy, 0))

            if serial is None:
                # Draw a thin placeholder so the column is visually complete
                self._draw_cell(page, y_mid, text="", matched=False)
            else:
                self._draw_cell(page, y_mid, text=str(serial), matched=True)
                overlaid += 1

        return overlaid

    # ── Drawing helpers ───────────────────────────────────────────────────────

    def _draw_header(self, page: fitz.Page, header_y: float) -> None:
        """Draw the 'هدف#' column header at header_y in the right margin."""
        # Two-line header like the existing ones
        rect_ar = fitz.Rect(_OVERLAY_X0, header_y, _OVERLAY_X1, header_y + 10)
        rect_en = fitz.Rect(_OVERLAY_X0, header_y + 10, _OVERLAY_X1, header_y + 20)

        # Blue background
        page.draw_rect(
            fitz.Rect(_OVERLAY_X0, header_y, _OVERLAY_X1, header_y + 20),
            color=None, fill=_HDR_COLOR,
        )
        page.insert_text(
            rect_ar.tl + fitz.Point(2, 8),
            "رقم هدف",
            fontname=_FONT, fontsize=_HDR_SIZE - 1,
            color=(1, 1, 1),
        )
        page.insert_text(
            rect_en.tl + fitz.Point(2, 7),
            "Hadaf#",
            fontname=_FONT, fontsize=_HDR_SIZE - 1,
            color=(1, 1, 1),
        )

    def _draw_cell(
        self,
        page: fitz.Page,
        y_mid: float,
        text: str,
        matched: bool,
    ) -> None:
        """Draw the Hadaf serial cell in the right margin at vertical position y_mid."""
        cell_h = 8.0
        y0 = y_mid - cell_h / 2
        y1 = y_mid + cell_h / 2
        rect = fitz.Rect(_OVERLAY_X0, y0, _OVERLAY_X1, y1)

        if matched:
            # Green background for matched rows
            page.draw_rect(rect, color=None, fill=_MATCH_COLOR)
            page.insert_text(
                fitz.Point(_OVERLAY_X0 + 2, y_mid + 3),
                text,
                fontname=_FONT, fontsize=_FONT_SIZE,
                color=(1, 1, 1),
            )
        else:
            # Light grey border for unmatched rows — no text
            page.draw_rect(rect, color=(0.8, 0.8, 0.8), fill=(0.97, 0.97, 0.97), width=0.3)
