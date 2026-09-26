#!/usr/bin/env bash
# One-command demo run: generate the synthetic invoice PDFs, then extract
# them into CSVs. Assumes the venv is already created and activated (see
# README "Setup"), or falls back to the system python3 if not.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"

OUT_PDFS="${1:-data/pdfs}"
OUT_CSVS="${2:-data/output}"

python3 -m invoice_extract generate --out "$OUT_PDFS" --seed 42
python3 -m invoice_extract extract --input "$OUT_PDFS" --out "$OUT_CSVS"

echo
echo "Done. CSVs written to $OUT_CSVS/ (invoices.csv, line_items.csv, exceptions.csv)."
