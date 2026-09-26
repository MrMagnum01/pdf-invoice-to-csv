"""Unit tests for the totals-validation logic, isolated from PDF parsing."""

from invoice_extract.extractor import InvoiceRecord, LineItemRecord, _validate_totals


def _record(**overrides) -> InvoiceRecord:
    defaults = dict(
        source_file="x.pdf",
        invoice_number="INV-1",
        subtotal=100.0,
        tax=8.0,
        total=108.0,
        line_items=[
            LineItemRecord("x.pdf", "INV-1", 1, "Widget", 2, 50.0, 100.0),
        ],
    )
    defaults.update(overrides)
    return InvoiceRecord(**defaults)


def test_consistent_invoice_has_no_issues():
    rec = _record()
    assert _validate_totals(rec) == []


def test_subtotal_not_matching_line_items_is_flagged():
    rec = _record(subtotal=999.0, total=1007.0)
    issues = _validate_totals(rec)
    types = {i.issue_type for i in issues}
    assert "subtotal_mismatch" in types


def test_total_not_matching_subtotal_plus_tax_is_flagged():
    rec = _record(total=500.0)
    issues = _validate_totals(rec)
    types = {i.issue_type for i in issues}
    assert "total_mismatch" in types
    assert "subtotal_mismatch" not in types


def test_missing_amount_fields_skip_that_check_without_crashing():
    rec = _record(subtotal=None, tax=None, total=None)
    assert _validate_totals(rec) == []


def test_rounding_within_a_cent_is_not_flagged():
    rec = _record(subtotal=100.004, total=108.004)
    assert _validate_totals(rec) == []
