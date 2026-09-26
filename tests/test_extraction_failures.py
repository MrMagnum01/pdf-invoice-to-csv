"""Extraction failures must come back as categorised exceptions, never "ok".

The two PDF cases are Astra's review probes (vault
40-sessions/2026-09-26-astra-invoice-probes.py): an invoice whose headers and
totals are all present but which has no line-item table, and a ruled table
whose unit price and amount are "NaN".
"""

import math

import pytest
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from invoice_extract.extractor import (
    INVALID_LINE_ITEM_ISSUE,
    MISSING_LINE_ITEMS_ISSUE,
    _parse_amount,
    extract_pdf,
)

HEADERS = [
    "Invoice Number: TEST-001",
    "Invoice Date: 2026-09-26",
    "Vendor: Synthetic Review Vendor",
    "Currency: USD",
    "Subtotal: 10.00",
    "Tax (0%): 0.00",
    "Total: 10.00",
]


def _table_pdf(path, rows):
    styles = getSampleStyleSheet()
    story = [Paragraph(h, styles["Normal"]) for h in HEADERS]
    table = Table([["Description", "Qty", "Unit Price", "Amount"], *rows])
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 1, colors.black)]))
    story += [Spacer(1, 15), table]
    SimpleDocTemplate(str(path)).build(story)
    return path


def test_headers_and_totals_without_item_table_is_an_exception(tmp_path):
    path = tmp_path / "missing-table.pdf"
    canvas = Canvas(str(path))
    for i, text in enumerate(HEADERS):
        canvas.drawString(50, 750 - i * 20, text)
    canvas.save()

    rec = extract_pdf(path)

    assert rec.status == "exception"
    assert rec.line_items == []
    assert [i.issue_type for i in rec.issues] == [MISSING_LINE_ITEMS_ISSUE]


def test_nan_unit_price_and_amount_is_an_exception(tmp_path):
    rec = extract_pdf(_table_pdf(tmp_path / "nan-row.pdf", [["Synthetic", "1", "NaN", "NaN"]]))

    assert rec.status == "exception"
    assert all(math.isfinite(x.unit_price) and math.isfinite(x.amount) for x in rec.line_items)
    types = [i.issue_type for i in rec.issues]
    assert INVALID_LINE_ITEM_ISSUE in types
    assert MISSING_LINE_ITEMS_ISSUE in types


def test_nan_row_beside_valid_row_is_kept_as_exception_not_dropped(tmp_path):
    rows = [["Good", "1", "10.00", "10.00"], ["Bad", "1", "10.00", "NaN"]]
    rec = extract_pdf(_table_pdf(tmp_path / "mixed.pdf", rows))

    assert rec.status == "exception"
    assert [x.description for x in rec.line_items] == ["Good"]
    assert [i.issue_type for i in rec.issues] == [INVALID_LINE_ITEM_ISSUE]


@pytest.mark.parametrize("raw", ["NaN", "nan", "inf", "-inf", "Infinity"])
def test_parse_amount_rejects_non_finite(raw):
    with pytest.raises(ValueError):
        _parse_amount(raw)
