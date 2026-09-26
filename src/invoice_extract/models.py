"""Plain data models shared by the generator and the extractor."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LineItem:
    description: str
    qty: int
    unit_price: float

    @property
    def amount(self) -> float:
        return round(self.qty * self.unit_price, 2)


@dataclass
class InvoiceSpec:
    """The ground-truth record used to render one invoice PDF.

    `edge_case` documents which scenario this invoice exercises (empty
    string for an ordinary invoice); it is metadata for the generator/tests,
    not something printed on the PDF itself.
    """

    invoice_number: str
    invoice_date: str  # ISO YYYY-MM-DD
    vendor_name: str
    currency: str
    line_items: list[LineItem]
    tax_rate: float  # e.g. 0.08 for 8%
    layout: str  # "classic" | "modern" | "compact"
    filename: str
    edge_case: str = ""
    omit_field: str | None = None  # field name to leave off the rendered PDF
    printed_total_override: float | None = None  # force a wrong total on the PDF
    image_only: bool = False

    @property
    def subtotal(self) -> float:
        return round(sum(item.amount for item in self.line_items), 2)

    @property
    def tax_amount(self) -> float:
        return round(self.subtotal * self.tax_rate, 2)

    @property
    def total(self) -> float:
        if self.printed_total_override is not None:
            return self.printed_total_override
        return round(self.subtotal + self.tax_amount, 2)
