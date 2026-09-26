# pdf-invoice-to-csv

Extracts structured data from PDF invoices into CSV: invoice number, date,
vendor, currency, line items, subtotal, tax and total. Validates the
printed totals against the line items and flags anything it can't trust —
a missing field, a duplicate invoice number, a totals mismatch, or a
scanned/image-only page with no text layer — into `exceptions.csv` instead
of silently guessing.

**Everything in this repo is synthetic.** The included generator produces
~30 fake invoices from fictional vendors with a fixed random seed, so the
whole pipeline can be demoed and tested without any real client data. No
code, data, or invoice layout here is copied from any client or employer
project.

## What it does

1. `generate` — builds a deterministic corpus of synthetic invoice PDFs
   across 3 visual layouts ("classic", "modern", "compact"), multiple
   currencies (USD/EUR/GBP), and a handful of deliberate edge cases:
   - two multi-page invoices (line items overflow onto a second page),
   - one invoice missing a required field (invoice date never printed),
   - two invoices that share the same invoice number,
   - one invoice whose printed total doesn't match its line items,
   - one scanned-looking, image-only PDF with no extractable text.
2. `extract` — reads every PDF in a directory and writes:
   - `invoices.csv` — one row per PDF: invoice number, date, vendor,
     currency, subtotal, tax, total, line item count, and a `status`
     (`ok` / `exception` / `unsupported`).
   - `line_items.csv` — one row per extracted line item.
   - `exceptions.csv` — one row per problem found: missing field, duplicate
     invoice number, subtotal/total not adding up, or an unsupported
     (image-only) PDF.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## One-command run

```bash
./run_demo.sh
```

This generates the synthetic PDFs into `data/pdfs/` and writes the three
CSVs to `data/output/`. Both directories are git-ignored (they're
generated, not source).

## CLI, step by step

```bash
export PYTHONPATH=src   # or: pip install -e . once a pyproject is added

python -m invoice_extract generate --out data/pdfs --seed 42
python -m invoice_extract extract  --input data/pdfs --out data/output
```

## Tests

```bash
source .venv/bin/activate
export PYTHONPATH=src
pytest tests -v
```

The suite generates the same fixed-seed corpus and asserts, for each layout
and each edge case above, that the extractor produces the correct row (or
correctly flags the exception) — plus a few unit tests on the totals
-validation logic in isolation and a subprocess smoke test of the CLI
itself.

## How extraction works

- **Header fields** (invoice number, date, vendor, currency) are pulled by
  matching label text ("Invoice Number:", "Invoice Date:", "Vendor:",
  "Currency:") anywhere in the page text via `pdfplumber`. The three
  layouts differ in fonts, colors, and box placement, but use the same
  label text, so one set of patterns covers all three.
- **Line items** are pulled from the ruled table `pdfplumber` detects on
  each page (its default line-based table strategy); a multi-page invoice's
  table is simply read across all of that PDF's pages and concatenated.
- **Validation**: subtotal is checked against the sum of extracted line
  items, and total is checked against subtotal + tax; either check failing
  writes a row to `exceptions.csv` without dropping the rest of that
  invoice's data.
- **Image-only pages**: if a PDF's combined page text is empty, it's
  flagged `unsupported` (`unsupported_scanned_image` in
  `exceptions.csv`) and skipped — this project does not do OCR. Reading a
  scanned invoice would need an OCR step (e.g. Tesseract), which is out of
  scope here; flagging it for manual handling is the correct behaviour, not
  a shortcut.

## Limits

- Extraction is label/text based, not a general-purpose PDF-layout parser.
  A real client's invoice PDFs would need their own label patterns (or a
  from-scratch layout study) added to `extractor.py`; the three layouts
  here demonstrate the approach, not a universal parser.
- No OCR. Scanned/image-only invoices are detected and reported, never
  guessed at.
- Currency is read as the printed 3-letter code; there is no FX
  conversion or cross-currency aggregation anywhere in this project.
- Duplicate-invoice-number detection is corpus-wide (across whatever
  directory you point `extract` at in one run), not global across every
  invoice a vendor has ever sent.

## Project layout

```
src/invoice_extract/
  vendors.py     fictional vendor/product name pools
  models.py      LineItem / InvoiceSpec dataclasses shared by generator+tests
  generator.py   builds the deterministic invoice corpus and renders the PDFs
  extractor.py   parses PDFs, validates totals, writes the three CSVs
  cli.py         `generate` / `extract` subcommands
tests/           pytest suite (generator determinism, all 3 layouts, all
                 edge cases, CLI subprocess smoke test)
LICENSES.md      every open-source library used and its licence
```
