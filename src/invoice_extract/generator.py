"""Generates synthetic PDF invoices for the extractor to be tested against.

Everything here is invented for this demo: fictional vendors and products,
made-up invoice numbers, made-up amounts. Nothing is copied from any real
client or employer project. Deterministic given a seed, so the same seed
always produces byte-identical invoice data (PDF bytes may still vary run to
run because reportlab embeds a creation timestamp, but the extracted
content never does).
"""

from __future__ import annotations

import random
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import InvoiceSpec, LineItem
from .vendors import CURRENCIES, PRODUCTS, VENDORS

LAYOUTS = ["classic", "modern", "compact"]

_STYLES = getSampleStyleSheet()


def _make_line_items(rng: random.Random, count: int) -> list[LineItem]:
    items = []
    for _ in range(count):
        desc = rng.choice(PRODUCTS)
        qty = rng.randint(1, 12)
        unit_price = round(rng.uniform(4.0, 450.0), 2)
        items.append(LineItem(description=desc, qty=qty, unit_price=unit_price))
    return items


def build_invoice_specs(seed: int = 42) -> list[InvoiceSpec]:
    """Build the full deterministic set of ~30 synthetic invoice specs."""
    rng = random.Random(seed)
    specs: list[InvoiceSpec] = []
    seq = 1

    def next_number(vendor_idx: int) -> str:
        nonlocal seq
        n = f"INV-{vendor_idx:02d}-{seq:04d}"
        seq += 1
        return n

    def base_date() -> str:
        month = rng.randint(1, 9)
        day = rng.randint(1, 28)
        return f"2026-{month:02d}-{day:02d}"

    # 24 ordinary invoices, spread across vendors/layouts/currencies.
    for i in range(24):
        vendor_idx = i % len(VENDORS)
        vendor = VENDORS[vendor_idx]
        layout = LAYOUTS[i % len(LAYOUTS)]
        currency = CURRENCIES[i % len(CURRENCIES)]
        items = _make_line_items(rng, rng.randint(1, 6))
        num = next_number(vendor_idx)
        specs.append(
            InvoiceSpec(
                invoice_number=num,
                invoice_date=base_date(),
                vendor_name=vendor,
                currency=currency,
                line_items=items,
                tax_rate=rng.choice([0.0, 0.05, 0.07, 0.08, 0.20]),
                layout=layout,
                filename=f"{num}.pdf",
            )
        )

    # 2 multi-page invoices: enough line items to overflow a letter page.
    for i in range(2):
        vendor_idx = (24 + i) % len(VENDORS)
        vendor = VENDORS[vendor_idx]
        layout = LAYOUTS[i % len(LAYOUTS)]
        currency = CURRENCIES[i % len(CURRENCIES)]
        items = _make_line_items(rng, 32)
        num = next_number(vendor_idx)
        specs.append(
            InvoiceSpec(
                invoice_number=num,
                invoice_date=base_date(),
                vendor_name=vendor,
                currency=currency,
                line_items=items,
                tax_rate=0.08,
                layout=layout,
                filename=f"{num}.pdf",
                edge_case="multi_page",
            )
        )

    # 1 invoice missing a required field (invoice date never printed).
    vendor_idx = 3
    num = next_number(vendor_idx)
    specs.append(
        InvoiceSpec(
            invoice_number=num,
            invoice_date=base_date(),
            vendor_name=VENDORS[vendor_idx],
            currency="USD",
            line_items=_make_line_items(rng, 3),
            tax_rate=0.08,
            layout="classic",
            filename=f"{num}.pdf",
            edge_case="missing_field",
            omit_field="invoice_date",
        )
    )

    # 2 invoices sharing the same invoice number (duplicate across the batch).
    dup_vendor_a, dup_vendor_b = 5, 6
    dup_number = f"INV-{dup_vendor_a:02d}-9999"
    specs.append(
        InvoiceSpec(
            invoice_number=dup_number,
            invoice_date=base_date(),
            vendor_name=VENDORS[dup_vendor_a],
            currency="USD",
            line_items=_make_line_items(rng, 4),
            tax_rate=0.08,
            layout="modern",
            filename=f"{dup_number}-a.pdf",
            edge_case="duplicate_invoice_number",
        )
    )
    specs.append(
        InvoiceSpec(
            invoice_number=dup_number,
            invoice_date=base_date(),
            vendor_name=VENDORS[dup_vendor_b],
            currency="EUR",
            line_items=_make_line_items(rng, 2),
            tax_rate=0.05,
            layout="compact",
            filename=f"{dup_number}-b.pdf",
            edge_case="duplicate_invoice_number",
        )
    )

    # 1 invoice whose printed total does not match its line items.
    vendor_idx = 8
    items = _make_line_items(rng, 3)
    num = next_number(vendor_idx)
    subtotal = round(sum(i.amount for i in items), 2)
    wrong_total = round(subtotal + 500.00, 2)  # deliberately wrong
    specs.append(
        InvoiceSpec(
            invoice_number=num,
            invoice_date=base_date(),
            vendor_name=VENDORS[vendor_idx],
            currency="GBP",
            line_items=items,
            tax_rate=0.08,
            layout="classic",
            filename=f"{num}.pdf",
            edge_case="total_mismatch",
            printed_total_override=wrong_total,
        )
    )

    # 1 scanned-looking, image-only PDF (no text layer at all).
    vendor_idx = 9
    num = next_number(vendor_idx)
    specs.append(
        InvoiceSpec(
            invoice_number=num,
            invoice_date=base_date(),
            vendor_name=VENDORS[vendor_idx],
            currency="USD",
            line_items=_make_line_items(rng, 3),
            tax_rate=0.08,
            layout="classic",
            filename=f"{num}-scanned.pdf",
            edge_case="image_only",
            image_only=True,
        )
    )

    return specs


def _money(value: float) -> str:
    return f"{value:,.2f}"


def _header_lines(spec: InvoiceSpec) -> list[tuple[str, str]]:
    fields = [
        ("invoice_number", f"Invoice Number: {spec.invoice_number}"),
        ("invoice_date", f"Invoice Date: {spec.invoice_date}"),
        ("vendor", f"Vendor: {spec.vendor_name}"),
        ("currency", f"Currency: {spec.currency}"),
    ]
    return [(key, text) for key, text in fields if key != spec.omit_field]


def _footer_lines(spec: InvoiceSpec) -> list[str]:
    return [
        f"Subtotal: {_money(spec.subtotal)}",
        f"Tax ({spec.tax_rate * 100:.2f}%): {_money(spec.tax_amount)}",
        f"Total: {_money(spec.total)}",
    ]


def _line_items_table(spec: InvoiceSpec, header_bg: colors.Color) -> Table:
    header = ["Description", "Qty", "Unit Price", "Amount"]
    rows = [header]
    for item in spec.line_items:
        rows.append(
            [
                item.description,
                str(item.qty),
                _money(item.unit_price),
                _money(item.amount),
            ]
        )
    table = Table(rows, colWidths=[3.0 * inch, 0.7 * inch, 1.1 * inch, 1.1 * inch], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), header_bg),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.whitesmoke]),
            ]
        )
    )
    return table


def _flowables_classic(spec: InvoiceSpec) -> list:
    title_style = ParagraphStyle("classic-title", parent=_STYLES["Title"], fontSize=20, textColor=colors.HexColor("#1a3a5c"))
    vendor_style = ParagraphStyle("classic-vendor", parent=_STYLES["Normal"], fontSize=13, fontName="Helvetica-Bold")
    meta_style = ParagraphStyle("classic-meta", parent=_STYLES["Normal"], fontSize=10)

    flow = [
        Paragraph("INVOICE", title_style),
        Spacer(1, 6),
        Paragraph(spec.vendor_name, vendor_style),
        Spacer(1, 4),
    ]
    for _, text in _header_lines(spec):
        flow.append(Paragraph(text, meta_style))
    flow.append(Spacer(1, 14))
    flow.append(_line_items_table(spec, colors.HexColor("#1a3a5c")))
    flow.append(Spacer(1, 10))
    for line in _footer_lines(spec):
        flow.append(Paragraph(line, ParagraphStyle("classic-footer", parent=_STYLES["Normal"], fontSize=11, alignment=2)))
    return flow


def _flowables_modern(spec: InvoiceSpec) -> list:
    banner_style = ParagraphStyle(
        "modern-banner",
        parent=_STYLES["Normal"],
        fontSize=16,
        fontName="Helvetica-Bold",
        textColor=colors.white,
        backColor=colors.HexColor("#2e7d32"),
        borderPadding=8,
    )
    meta_style = ParagraphStyle("modern-meta", parent=_STYLES["Normal"], fontSize=10, borderColor=colors.grey, borderWidth=0.5, borderPadding=6)

    meta_text = "<br/>".join(text for _, text in _header_lines(spec))
    flow = [
        Paragraph(f"{spec.vendor_name} &mdash; INVOICE", banner_style),
        Spacer(1, 10),
        Paragraph(meta_text, meta_style),
        Spacer(1, 14),
        _line_items_table(spec, colors.HexColor("#2e7d32")),
        Spacer(1, 10),
    ]
    for line in _footer_lines(spec):
        flow.append(Paragraph(line, ParagraphStyle("modern-footer", parent=_STYLES["Normal"], fontSize=11, alignment=2)))
    return flow


def _flowables_compact(spec: InvoiceSpec) -> list:
    line_style = ParagraphStyle("compact-line", parent=_STYLES["Normal"], fontSize=8.5, leading=11)
    header_text = f"<b>{spec.vendor_name}</b> | " + " | ".join(text for _, text in _header_lines(spec))
    flow = [
        Paragraph(header_text, line_style),
        Spacer(1, 8),
        _line_items_table(spec, colors.HexColor("#5d4037")),
        Spacer(1, 6),
    ]
    footer_text = " | ".join(_footer_lines(spec))
    flow.append(Paragraph(footer_text, ParagraphStyle("compact-footer", parent=_STYLES["Normal"], fontSize=9, alignment=2)))
    return flow


_LAYOUT_BUILDERS = {
    "classic": _flowables_classic,
    "modern": _flowables_modern,
    "compact": _flowables_compact,
}


def _render_text_pdf(spec: InvoiceSpec, path: Path) -> None:
    doc = SimpleDocTemplate(
        str(path),
        pagesize=letter,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
    )
    flowables = _LAYOUT_BUILDERS[spec.layout](spec)
    doc.build(flowables)


def _render_image_only_pdf(spec: InvoiceSpec, path: Path, tmp_dir: Path) -> None:
    """Render a page as a single raster image, with no text layer at all.

    Simulates a scanned paper invoice photographed or scanned into a PDF.
    The extractor must detect the absence of a text layer and flag it as
    unsupported rather than attempting OCR.
    """
    width_px, height_px = 850, 1100
    img = Image.new("RGB", (width_px, height_px), color=(250, 248, 240))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    lines = [
        "INVOICE (scanned copy)",
        spec.vendor_name,
        f"Invoice Number: {spec.invoice_number}",
        f"Invoice Date: {spec.invoice_date}",
        f"Currency: {spec.currency}",
        "",
        "Line items omitted from this scan preview.",
        f"Total: {_money(spec.total)}",
    ]
    y = 60
    for line in lines:
        draw.text((60, y), line, fill=(40, 40, 40), font=font)
        y += 30

    # Slight noise so this is unambiguously a raster, not vector text.
    rng = random.Random(hash(spec.invoice_number) & 0xFFFFFFFF)
    for _ in range(400):
        x = rng.randint(0, width_px - 1)
        y2 = rng.randint(0, height_px - 1)
        draw.point((x, y2), fill=(200, 200, 200))

    img_path = tmp_dir / f"{spec.invoice_number}-raster.png"
    img.save(img_path)

    c = canvas.Canvas(str(path), pagesize=letter)
    page_w, page_h = letter
    c.drawImage(str(img_path), 0, 0, width=page_w, height=page_h)
    c.showPage()
    c.save()


def render_invoice_pdf(spec: InvoiceSpec, out_dir: Path, tmp_dir: Path | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / spec.filename
    if spec.image_only:
        render_tmp = tmp_dir if tmp_dir is not None else out_dir
        _render_image_only_pdf(spec, path, render_tmp)
    else:
        _render_text_pdf(spec, path)
    return path


def generate_all(out_dir: Path, seed: int = 42) -> list[InvoiceSpec]:
    """Build the deterministic invoice set and render every PDF to out_dir."""
    out_dir = Path(out_dir)
    specs = build_invoice_specs(seed)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for spec in specs:
            render_invoice_pdf(spec, out_dir, tmp_dir=tmp_dir)
    return specs
