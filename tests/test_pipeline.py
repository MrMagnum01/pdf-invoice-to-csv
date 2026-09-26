"""End-to-end tests: generate the synthetic corpus, run the extractor once,
and assert on each edge case the corpus is designed to exercise."""

import csv
import subprocess
import sys
from pathlib import Path

import pytest

from invoice_extract.extractor import process_directory
from invoice_extract.generator import build_invoice_specs, generate_all

SEED = 42

EXPECTED_EDGE_CASES = {
    "multi_page",
    "missing_field",
    "duplicate_invoice_number",
    "total_mismatch",
    "image_only",
}


@pytest.fixture(scope="session")
def specs():
    return build_invoice_specs(SEED)


@pytest.fixture(scope="session")
def corpus_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("pdfs")
    generate_all(out, seed=SEED)
    return out


@pytest.fixture(scope="session")
def extracted(tmp_path_factory, corpus_dir):
    out = tmp_path_factory.mktemp("output")
    process_directory(corpus_dir, out)
    return out


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="session")
def invoices_rows(extracted):
    return {row["source_file"]: row for row in _read_csv(extracted / "invoices.csv")}


@pytest.fixture(scope="session")
def line_items_rows(extracted):
    return _read_csv(extracted / "line_items.csv")


@pytest.fixture(scope="session")
def exceptions_rows(extracted):
    return _read_csv(extracted / "exceptions.csv")


# --- generator -------------------------------------------------------


def test_generator_is_deterministic():
    a = build_invoice_specs(SEED)
    b = build_invoice_specs(SEED)
    assert [s.invoice_number for s in a] == [s.invoice_number for s in b]
    assert [s.total for s in a] == [s.total for s in b]
    assert [s.filename for s in a] == [s.filename for s in b]


def test_generator_produces_about_30_invoices(specs):
    assert 28 <= len(specs) <= 32


def test_generator_covers_all_required_edge_cases(specs):
    seen = {s.edge_case for s in specs if s.edge_case}
    assert seen == EXPECTED_EDGE_CASES


def test_generator_uses_all_three_layouts(specs):
    assert {s.layout for s in specs} == {"classic", "modern", "compact"}


def test_generator_uses_multiple_currencies(specs):
    assert {s.currency for s in specs} >= {"USD", "EUR", "GBP"}


# --- CSV shape ---------------------------------------------------------


def test_csv_headers(extracted):
    assert _header(extracted / "invoices.csv") == [
        "source_file",
        "invoice_number",
        "invoice_date",
        "vendor",
        "currency",
        "subtotal",
        "tax",
        "total",
        "line_item_count",
        "status",
    ]
    assert _header(extracted / "line_items.csv") == [
        "source_file",
        "invoice_number",
        "line_no",
        "description",
        "qty",
        "unit_price",
        "amount",
    ]
    assert _header(extracted / "exceptions.csv") == [
        "source_file",
        "invoice_number",
        "issue_type",
        "detail",
    ]


def _header(path: Path) -> list[str]:
    with path.open(newline="") as f:
        return next(csv.reader(f))


def test_every_pdf_has_an_invoices_row(corpus_dir, invoices_rows):
    pdf_names = {p.name for p in corpus_dir.glob("*.pdf")}
    assert set(invoices_rows.keys()) == pdf_names


# --- ordinary invoices, all three layouts -------------------------------


def test_ordinary_invoice_extracted_correctly(specs, invoices_rows, line_items_rows):
    ordinary = [s for s in specs if not s.edge_case]
    assert ordinary, "need at least one ordinary invoice to test against"
    by_layout = {s.layout: s for s in ordinary}
    assert set(by_layout) == {"classic", "modern", "compact"}

    for layout, spec in by_layout.items():
        row = invoices_rows[spec.filename]
        assert row["status"] == "ok", f"{layout} layout: {row}"
        assert row["invoice_number"] == spec.invoice_number
        assert row["invoice_date"] == spec.invoice_date
        assert row["vendor"] == spec.vendor_name
        assert row["currency"] == spec.currency
        assert float(row["subtotal"]) == pytest.approx(spec.subtotal, abs=0.01)
        assert float(row["tax"]) == pytest.approx(spec.tax_amount, abs=0.01)
        assert float(row["total"]) == pytest.approx(spec.total, abs=0.01)
        assert int(row["line_item_count"]) == len(spec.line_items)

        items = [r for r in line_items_rows if r["source_file"] == spec.filename]
        assert len(items) == len(spec.line_items)
        extracted_amount_sum = sum(float(r["amount"]) for r in items)
        assert extracted_amount_sum == pytest.approx(spec.subtotal, abs=0.01)


# --- multi-page --------------------------------------------------------


def test_multi_page_invoices_extract_all_line_items(specs, invoices_rows, line_items_rows, corpus_dir):
    import pdfplumber

    multi_page_specs = [s for s in specs if s.edge_case == "multi_page"]
    assert len(multi_page_specs) == 2

    for spec in multi_page_specs:
        with pdfplumber.open(corpus_dir / spec.filename) as pdf:
            assert len(pdf.pages) > 1, "fixture should actually span multiple pages"

        row = invoices_rows[spec.filename]
        assert row["status"] == "ok"
        assert int(row["line_item_count"]) == len(spec.line_items)
        items = [r for r in line_items_rows if r["source_file"] == spec.filename]
        assert len(items) == len(spec.line_items)


# --- missing field ------------------------------------------------------


def test_missing_field_invoice_is_flagged(specs, invoices_rows, exceptions_rows):
    spec = next(s for s in specs if s.edge_case == "missing_field")
    row = invoices_rows[spec.filename]
    assert row["status"] == "exception"
    assert row["invoice_date"] == ""
    assert row["invoice_number"] == spec.invoice_number  # everything else still readable

    issues = [e for e in exceptions_rows if e["source_file"] == spec.filename]
    assert any(e["issue_type"] == "missing_field" and "invoice_date" in e["detail"] for e in issues)


# --- duplicate invoice number -------------------------------------------


def test_duplicate_invoice_number_is_flagged_on_both_files(specs, invoices_rows, exceptions_rows):
    dup_specs = [s for s in specs if s.edge_case == "duplicate_invoice_number"]
    assert len(dup_specs) == 2
    assert dup_specs[0].invoice_number == dup_specs[1].invoice_number

    for spec in dup_specs:
        row = invoices_rows[spec.filename]
        assert row["status"] == "exception"
        assert row["invoice_number"] == spec.invoice_number
        issues = [e for e in exceptions_rows if e["source_file"] == spec.filename]
        assert any(e["issue_type"] == "duplicate_invoice_number" for e in issues)

    other_file = dup_specs[1].filename
    this_issue = next(
        e
        for e in exceptions_rows
        if e["source_file"] == dup_specs[0].filename and e["issue_type"] == "duplicate_invoice_number"
    )
    assert other_file in this_issue["detail"]


# --- total mismatch ------------------------------------------------------


def test_total_mismatch_invoice_is_flagged(specs, invoices_rows, exceptions_rows):
    spec = next(s for s in specs if s.edge_case == "total_mismatch")
    row = invoices_rows[spec.filename]
    assert row["status"] == "exception"
    assert float(row["total"]) == pytest.approx(spec.total, abs=0.01)  # printed (wrong) value, unchanged

    issues = [e for e in exceptions_rows if e["source_file"] == spec.filename]
    types = {e["issue_type"] for e in issues}
    assert "total_mismatch" in types
    assert "subtotal_mismatch" not in types  # only the total was tampered with


# --- image-only / scanned ------------------------------------------------


def test_image_only_pdf_is_flagged_unsupported_not_ocrd(specs, invoices_rows, exceptions_rows, line_items_rows):
    spec = next(s for s in specs if s.edge_case == "image_only")
    row = invoices_rows[spec.filename]
    assert row["status"] == "unsupported"
    assert row["invoice_number"] == ""
    assert row["subtotal"] == ""
    assert int(row["line_item_count"]) == 0

    items = [r for r in line_items_rows if r["source_file"] == spec.filename]
    assert items == []

    issues = [e for e in exceptions_rows if e["source_file"] == spec.filename]
    assert len(issues) == 1
    assert issues[0]["issue_type"] == "unsupported_scanned_image"

    assert "pytesseract" not in sys.modules
    assert "ocrmypdf" not in sys.modules


# --- exception count sanity ----------------------------------------------


def test_only_the_designed_edge_cases_have_exceptions(specs, invoices_rows):
    # multi_page is a structural edge case, not a data-quality problem: those
    # invoices are expected to extract cleanly with status "ok".
    data_quality_cases = EXPECTED_EDGE_CASES - {"multi_page"}
    flawed_filenames = {s.filename for s in specs if s.edge_case in data_quality_cases}
    exception_filenames = {fn for fn, row in invoices_rows.items() if row["status"] != "ok"}
    assert exception_filenames == flawed_filenames


# --- CLI smoke test -------------------------------------------------------


def test_cli_generate_and_extract(tmp_path):
    src_root = Path(__file__).resolve().parents[1] / "src"
    pdf_dir = tmp_path / "pdfs"
    out_dir = tmp_path / "out"

    gen = subprocess.run(
        [sys.executable, "-m", "invoice_extract", "generate", "--out", str(pdf_dir), "--seed", "42"],
        cwd=src_root,
        capture_output=True,
        text=True,
    )
    assert gen.returncode == 0, gen.stderr
    assert list(pdf_dir.glob("*.pdf"))

    ext = subprocess.run(
        [sys.executable, "-m", "invoice_extract", "extract", "--input", str(pdf_dir), "--out", str(out_dir)],
        cwd=src_root,
        capture_output=True,
        text=True,
    )
    assert ext.returncode == 0, ext.stderr
    assert (out_dir / "invoices.csv").exists()
    assert (out_dir / "line_items.csv").exists()
    assert (out_dir / "exceptions.csv").exists()
