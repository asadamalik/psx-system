#!/usr/bin/env python3
"""
parse_raw.py — deterministic raw -> JSON for fetched Investing.com pages
=======================================================================
Reads fetched markdown pages saved in stocks/<SYM>/raw/ and writes the
structured JSON the engine consumes, using engine/parse_investing.py
(no LLM). Then validates each output against the schema.

Expected raw markdown filenames (saved by the Cowork fetch step):
    income_statement.md   -> fundamentals/income_statement_annual.json
    balance_sheet.md      -> fundamentals/balance_sheet_annual.json
    cash_flow.md          -> fundamentals/cashflow_annual.json
    ratios.md             -> fundamentals/ratio.json

USAGE
    python parse_raw.py MLCF
    python parse_raw.py MLCF --quiet

After this, run:  python run.py MLCF
"""

from __future__ import annotations
import sys
import json
import argparse

from engine.layout import StockPaths
from engine import parse_investing as P
from engine import schema

# raw markdown file (in raw/) -> (parser, output section name)
STATEMENT_JOBS = [
    ("income_statement.md", "income", "income_statement_annual"),
    ("balance_sheet.md", "balance", "balance_sheet_annual"),
    ("cash_flow.md", "cashflow", "cashflow_annual"),
]


def _read(path):
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else None


def parse_symbol(symbol: str, quiet=False) -> dict:
    def log(*a):
        if not quiet:
            print(*a)

    p = StockPaths(symbol).ensure()
    log(f"\n=== parsing {p.symbol} ===")
    written = {}

    # statements
    for fname, kind, out_section in STATEMENT_JOBS:
        md = _read(p.raw / fname)
        if md is None:
            log(f"  {fname:22} : not found (skip)")
            continue
        data = P.parse_statement(md, kind)
        if not data:
            log(f"  {fname:22} : no table parsed")
            continue
        out_path = p.section_json(out_section)
        out_path.write_text(json.dumps(data, indent=2))
        ok, errs, warns = schema.validate(out_section, data)
        flag = "ok" if ok else f"SCHEMA FAIL {errs}"
        log(f"  {fname:22} -> {out_section}.json  ({len(data)} fields, {flag})")
        written[out_section] = data

    # ratios
    md = _read(p.raw / "ratios.md")
    if md is not None:
        ratios = P.parse_ratios(md)
        if ratios:
            p.section_json("ratio").write_text(json.dumps(ratios, indent=2))
            ok, errs, warns = schema.validate("ratio", ratios)
            log(f"  {'ratios.md':22} -> ratio.json  ({len(ratios)} ratios, "
                f"{'ok' if ok else 'SCHEMA FAIL'})")
            written["ratio"] = ratios
        else:
            log("  ratios.md              : no ratios parsed")
    else:
        log("  ratios.md              : not found (skip)")

    return written


def main():
    ap = argparse.ArgumentParser(description="Parse fetched Investing.com markdown -> JSON")
    ap.add_argument("symbols", nargs="+")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    for sym in args.symbols:
        parse_symbol(sym.upper(), quiet=args.quiet)


if __name__ == "__main__":
    main()
