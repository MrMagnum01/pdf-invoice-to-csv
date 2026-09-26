"""Command-line entry point.

    python -m invoice_extract generate --out data/pdfs [--seed 42]
    python -m invoice_extract extract  --input data/pdfs --out data/output
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .extractor import process_directory
from .generator import generate_all


def _cmd_generate(args: argparse.Namespace) -> None:
    specs = generate_all(Path(args.out), seed=args.seed)
    print(f"Generated {len(specs)} synthetic invoice PDFs in {args.out} (seed={args.seed}).")


def _cmd_extract(args: argparse.Namespace) -> None:
    records = process_directory(Path(args.input), Path(args.out))
    ok = sum(1 for r in records if r.status == "ok")
    exceptions = sum(1 for r in records if r.status == "exception")
    unsupported = sum(1 for r in records if r.status == "unsupported")
    print(
        f"Processed {len(records)} PDFs from {args.input}: "
        f"{ok} ok, {exceptions} with exceptions, {unsupported} unsupported."
    )
    print(f"Wrote invoices.csv, line_items.csv, exceptions.csv to {args.out}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="invoice_extract", description="Synthetic PDF invoice generator/extractor demo.")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Generate the synthetic invoice PDF corpus.")
    gen.add_argument("--out", required=True, help="Output directory for generated PDFs.")
    gen.add_argument("--seed", type=int, default=42, help="Random seed (default: 42).")
    gen.set_defaults(func=_cmd_generate)

    ext = sub.add_parser("extract", help="Extract structured data from a directory of invoice PDFs.")
    ext.add_argument("--input", required=True, help="Directory containing invoice PDFs.")
    ext.add_argument("--out", required=True, help="Output directory for the CSV files.")
    ext.set_defaults(func=_cmd_extract)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
