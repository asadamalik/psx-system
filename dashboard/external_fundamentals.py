#!/usr/bin/env python3
"""
external_fundamentals.py — consumer for the stock-agent engine's per-symbol exports.

The PSX Stock Analysis Engine (a separate repo) runs `export_external.py` and drops
one JSON per symbol into this dashboard's `psx_data/external/` folder, plus a
`manifest.json`. Each file carries true OHLC, full fundamentals (P/B, D/E, ROE/ROA/
ROIC, EV/EBITDA, FCF, dividend history…), real insider transactions (shares + price),
and the ENGINE's own Fund-70/Tech-30 scores + verdict.

This module loads those files into a {SYMBOL: payload} dict that `psx_auto.py` bakes
into the dashboard as `embed["external"]`. The dashboard renders engine data for any
symbol present here and falls back to its own scraped/computed analysis otherwise — so
symbols without an export (FFC, PAKQATAR, …) are completely unaffected.

The export folder is a drop-folder: filenames are `<generated_ts>_<SYMBOL>.json`, so a
symbol may have more than one file across re-exports. We keep the newest per symbol.
"""
import os
import json
import glob


def load(state_dir: str) -> dict:
    """Return {SYMBOL: export_payload}, newest export per symbol.

    Never raises on a single bad file — a malformed export is skipped (and logged)
    so one broken symbol can't blank the whole bridge. Returns {} if the folder is
    absent (the dashboard then behaves exactly as before).
    """
    ext_dir = os.path.join(state_dir, "external")
    if not os.path.isdir(ext_dir):
        return {}

    by_symbol: dict[str, dict] = {}
    for path in glob.glob(os.path.join(ext_dir, "*.json")):
        if os.path.basename(path) == "manifest.json":
            continue
        try:
            payload = json.load(open(path, encoding="utf-8"))
        except (ValueError, OSError) as e:
            print(f"  [external] skipped {os.path.basename(path)}: {e}")
            continue
        sym = (payload.get("symbol") or "").upper()
        if not sym:
            continue
        prev = by_symbol.get(sym)
        if prev is None or (payload.get("generated_ts") or 0) >= (prev.get("generated_ts") or 0):
            by_symbol[sym] = payload

    if by_symbol:
        print(f"External engine data: {len(by_symbol)} symbol(s) — {', '.join(sorted(by_symbol))}")
    return by_symbol
