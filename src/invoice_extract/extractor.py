"""Extracts structured invoice data from the PDFs the generator produces.

Pulls invoice number, date, vendor, currency, line items, subtotal, tax and
total via label-based text matching (works across all three layouts because
the label text is identical; only the surrounding styling differs) plus
pdfplumber's line-based table detection for the line-item grid. Validates
the printed totals against the line items and against each other, and
flags a PDF with no extractable text layer as unsupported rather than
attempting OCR.
"""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

_LABEL_PATTERNS = {
    "invoice_number": re.compile(r"Invoice Number:\s*(\S+)"),
    "invoice_date": re.compile(r"Invoice Date:\s*(\S+)"),
    "vendor": re.compile(r"Vendor:\s*([^\n|]+)"),
    "currency": re.compile(r"Currency:\s*(\S+)"),
    "subtotal": re.compile(r"Subtotal:\s*([\d,]+\.\d{2})"),
    "tax": re.compile(r"Tax\s*\([^)]*\):\s*([\d,]+\.\d{2})"),
    "total": re.compile(r"Total:\s*([\d,]+\.\d{2})"),
}

_TABLE_HEADER = ["Description", "Qty", "Unit Price", "Amount"]

_AMOUNT_FIELDS = ("subtotal", "tax", "total")

UNSUPPORTED_ISSUE = "unsupported_scanned_image"
INVALID_LINE_ITEM_ISSUE = "invalid_line_item"
MISSING_LINE_ITEMS_ISSUE = "missing_line_items"


@dataclass
class LineItemRecord:
    source_file: str
    invoice_number: str
    line_no: int
    description: str
    qty: int
    unit_price: float
    amount: float


@dataclass
class Issue:
    source_file: str
    invoice_number: str
    issue_type: str
    detail: str


@dataclass
class InvoiceRecord:
    source_file: str
    invoice_number: str | None = None
    invoice_date: str | None = None
    vendor: str | None = None
    currency: str | None = None
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None
    line_items: list[LineItemRecord] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    unsupported: bool = False

    @property
    def status(self) -> str:
        if self.unsupported:
            return "unsupported"
        return "exception" if self.issues else "ok"


def _parse_amount(raw: str) -> float:
    value = float(raw.replace(",", ""))
    # float() accepts "NaN" and "inf"; neither is a real amount, and NaN
    # compares false against everything, so it would slip past validation.
    if not math.isfinite(value):
        raise ValueError(f"non-finite amount: {raw!r}")
    return value


def _extract_fields(text: str, source_file: str) -> tuple[dict, list[Issue]]:
    fields_out: dict = {}
    issues: list[Issue] = []
    inv_num_match = _LABEL_PATTERNS["invoice_number"].search(text)
    inv_num = inv_num_match.group(1) if inv_num_match else None

    for key, pattern in _LABEL_PATTERNS.items():
        match = pattern.search(text)
        if match is None:
            fields_out[key] = None
            issues.append(
                Issue(
                    source_file=source_file,
                    invoice_number=inv_num or "",
                    issue_type="missing_field",
                    detail=f"Could not find a value for '{key}' on this invoice.",
                )
            )
            continue
        value = match.group(1)
        if key in _AMOUNT_FIELDS:
            value = _parse_amount(value)
        fields_out[key] = value
    return fields_out, issues


def _extract_line_items(
    pdf: pdfplumber.PDF, source_file: str, invoice_number: str
) -> tuple[list[LineItemRecord], list[Issue]]:
    items: list[LineItemRecord] = []
    issues: list[Issue] = []
    line_no = 0
    for page in pdf.pages:
        for table in page.extract_tables():
            for row in table:
                if row == _TABLE_HEADER:
                    continue
                if len(row) != 4 or row[0] is None:
                    continue
                description, qty_raw, unit_price_raw, amount_raw = row
                try:
                    qty = int(qty_raw)
                    unit_price = _parse_amount(unit_price_raw)
                    amount = _parse_amount(amount_raw)
                except (TypeError, ValueError):
                    # Keep the row as a categorised exception rather than
                    # dropping it: a silently skipped row would let the
                    # invoice pass as "ok" with items missing.
                    issues.append(
                        Issue(
                            source_file=source_file,
                            invoice_number=invoice_number,
                            issue_type=INVALID_LINE_ITEM_ISSUE,
                            detail=(
                                f"Line-item row {description!r} has an unreadable qty, "
                                f"unit price or amount ({qty_raw!r}, {unit_price_raw!r}, "
                                f"{amount_raw!r}); row not extracted."
                            ),
                        )
                    )
                    continue
                line_no += 1
                items.append(
                    LineItemRecord(
                        source_file=source_file,
                        invoice_number=invoice_number,
                        line_no=line_no,
                        description=description.strip(),
                        qty=qty,
                        unit_price=unit_price,
                        amount=amount,
                    )
                )
    return items, issues


def _validate_totals(record: InvoiceRecord) -> list[Issue]:
    issues: list[Issue] = []
    inv_num = record.invoice_number or ""

    if not record.line_items:
        issues.append(
            Issue(
                source_file=record.source_file,
                invoice_number=inv_num,
                issue_type=MISSING_LINE_ITEMS_ISSUE,
                detail=(
                    "No valid line items could be extracted, so the printed "
                    "subtotal cannot be checked against them."
                ),
            )
        )

    if record.subtotal is not None and record.line_items:
        computed_subtotal = round(sum(item.amount for item in record.line_items), 2)
        if abs(computed_subtotal - record.subtotal) > 0.01:
            issues.append(
                Issue(
                    source_file=record.source_file,
                    invoice_number=inv_num,
                    issue_type="subtotal_mismatch",
                    detail=(
                        f"Printed subtotal {record.subtotal:.2f} does not match "
                        f"the sum of line items {computed_subtotal:.2f}."
                    ),
                )
            )

    if record.subtotal is not None and record.tax is not None and record.total is not None:
        expected_total = round(record.subtotal + record.tax, 2)
        if abs(expected_total - record.total) > 0.01:
            issues.append(
                Issue(
                    source_file=record.source_file,
                    invoice_number=inv_num,
                    issue_type="total_mismatch",
                    detail=(
                        f"Printed total {record.total:.2f} does not equal "
                        f"subtotal + tax {expected_total:.2f}."
                    ),
                )
            )

    return issues


def extract_pdf(path: Path) -> InvoiceRecord:
    source_file = path.name
    with pdfplumber.open(path) as pdf:
        full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

        if not full_text.strip():
            record = InvoiceRecord(source_file=source_file, unsupported=True)
            record.issues.append(
                Issue(
                    source_file=source_file,
                    invoice_number="",
                    issue_type=UNSUPPORTED_ISSUE,
                    detail=(
                        "No extractable text layer found (looks like a scanned "
                        "image). Not OCR'd; flagged for manual handling."
                    ),
                )
            )
            return record

        fields_out, missing_issues = _extract_fields(full_text, source_file)
        record = InvoiceRecord(
            source_file=source_file,
            invoice_number=fields_out.get("invoice_number"),
            invoice_date=fields_out.get("invoice_date"),
            vendor=fields_out.get("vendor").strip() if fields_out.get("vendor") else None,
            currency=fields_out.get("currency"),
            subtotal=fields_out.get("subtotal"),
            tax=fields_out.get("tax"),
            total=fields_out.get("total"),
        )
        record.issues.extend(missing_issues)
        record.line_items, item_issues = _extract_line_items(pdf, source_file, record.invoice_number or "")
        record.issues.extend(item_issues)
        record.issues.extend(_validate_totals(record))

    return record


def _flag_duplicate_invoice_numbers(records: list[InvoiceRecord]) -> None:
    by_number: dict[str, list[InvoiceRecord]] = {}
    for rec in records:
        if not rec.invoice_number or rec.unsupported:
            continue
        by_number.setdefault(rec.invoice_number, []).append(rec)

    for number, group in by_number.items():
        if len(group) < 2:
            continue
        for rec in group:
            others = ", ".join(sorted(r.source_file for r in group if r is not rec))
            rec.issues.append(
                Issue(
                    source_file=rec.source_file,
                    invoice_number=number,
                    issue_type="duplicate_invoice_number",
                    detail=f"Invoice number '{number}' also appears in: {others}.",
                )
            )


def process_directory(input_dir: Path, output_dir: Path) -> list[InvoiceRecord]:
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_paths = sorted(input_dir.glob("*.pdf"))
    records = [extract_pdf(p) for p in pdf_paths]
    _flag_duplicate_invoice_numbers(records)

    _write_invoices_csv(records, output_dir / "invoices.csv")
    _write_line_items_csv(records, output_dir / "line_items.csv")
    _write_exceptions_csv(records, output_dir / "exceptions.csv")
    return records


def _write_invoices_csv(records: list[InvoiceRecord], path: Path) -> None:
    fieldnames = [
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
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in records:
            writer.writerow(
                {
                    "source_file": rec.source_file,
                    "invoice_number": rec.invoice_number or "",
                    "invoice_date": rec.invoice_date or "",
                    "vendor": rec.vendor or "",
                    "currency": rec.currency or "",
                    "subtotal": f"{rec.subtotal:.2f}" if rec.subtotal is not None else "",
                    "tax": f"{rec.tax:.2f}" if rec.tax is not None else "",
                    "total": f"{rec.total:.2f}" if rec.total is not None else "",
                    "line_item_count": len(rec.line_items),
                    "status": rec.status,
                }
            )


def _write_line_items_csv(records: list[InvoiceRecord], path: Path) -> None:
    fieldnames = ["source_file", "invoice_number", "line_no", "description", "qty", "unit_price", "amount"]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in records:
            for item in rec.line_items:
                writer.writerow(
                    {
                        "source_file": item.source_file,
                        "invoice_number": item.invoice_number,
                        "line_no": item.line_no,
                        "description": item.description,
                        "qty": item.qty,
                        "unit_price": f"{item.unit_price:.2f}",
                        "amount": f"{item.amount:.2f}",
                    }
                )


def _write_exceptions_csv(records: list[InvoiceRecord], path: Path) -> None:
    fieldnames = ["source_file", "invoice_number", "issue_type", "detail"]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in records:
            for issue in rec.issues:
                writer.writerow(
                    {
                        "source_file": issue.source_file,
                        "invoice_number": issue.invoice_number,
                        "issue_type": issue.issue_type,
                        "detail": issue.detail,
                    }
                )
