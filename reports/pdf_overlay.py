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
_BORDER_COLOR = (0.0, 0.0, 0.0)    # thin black cell border (matches table grid)


class PDFOverlayWriter:
    """
    Overlays Hadaf serial numbers onto the original bank PDF without
    rebuilding any page content.
    """

    def overlay(
        self,
        pdf_bytes: bytes,
        hadaf_by_iban: dict[str, int],   # IBAN.upper() → hadaf_serial
    ) -> tuple[bytes, set[int]]:
        """
        Parameters
        ----------
        pdf_bytes       Original bank PDF bytes.
        hadaf_by_iban   {IBAN.upper() → hadaf_serial} lookup.

        Returns
        -------
        (modified_pdf_bytes, matched_serials_set)
        matched_serials_set — Hadaf serial numbers actually overlaid in the PDF.
        """
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        matched_serials: set[int] = set()

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            page_serials = self._overlay_page(page, hadaf_by_iban)
            matched_serials.update(page_serials)

        logger.info("PDFOverlayWriter: overlaid %d serial numbers", len(matched_serials))

        buf = BytesIO()
        doc.save(buf, garbage=4, deflate=True)
        doc.close()
        return buf.getvalue(), matched_serials

    # ── Internal ──────────────────────────────────────────────────────────────

    def _overlay_page(
        self,
        page: fitz.Page,
        hadaf_by_iban: dict[str, int],
    ) -> set[int]:
        """
        Scan the page for IBAN text, match with Hadaf data, overlay serial.
        Returns the set of Hadaf serial numbers overlaid on this page.
        """
        words = page.get_text("words")   # (x0, y0, x1, y1, text, ...)

        iban_rows: list[tuple[float, float, str]] = []   # (y_mid, row_height, iban)
        for w in words:
            x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4]
            if _IBAN_RE.fullmatch(text.strip()):
                y_mid = (y0 + y1) / 2
                row_h = y1 - y0
                iban_rows.append((y_mid, row_h, text.strip()))

        if not iban_rows:
            return set()

        overlaid_serials: set[int] = set()
        for y_mid, row_h, iban in iban_rows:
            serial = hadaf_by_iban.get(iban.upper())
            self._draw_cell(page, y_mid, row_h,
                            text=str(serial) if serial is not None else "")
            if serial is not None:
                overlaid_serials.add(serial)

        return overlaid_serials

    # ── Drawing helper ──────────────────────────────────────────────────────

    def _draw_cell(
        self,
        page: fitz.Page,
        y_mid: float,
        row_h: float,
        text: str,
    ) -> None:
        """
        Draw an empty bordered cell in the right margin (border only — no fill),
        and overlay the Hadaf serial as red text when matched. The cell height
        matches the row, vertically centred to line up with the row text.
        """
        # Cell rectangle — height matches the row, aligned to its vertical centre
        cell_h = max(row_h, 8.0)
        rect = fitz.Rect(
            _OVERLAY_X0, y_mid - cell_h / 2,
            _OVERLAY_X1, y_mid + cell_h / 2,
        )
        # Border only — no fill (matches the table grid, thin black line)
        page.draw_rect(rect, color=_BORDER_COLOR, fill=None, width=0.4)

        if text:
            font_size = max(6.0, min(9.0, row_h))
            baseline_y = y_mid + font_size * 0.35
            page.insert_text(
                fitz.Point(_OVERLAY_X0 + 2, baseline_y),
                text,
                fontname=_FONT, fontsize=font_size,
                color=_TEXT_COLOR,
            )
