#!/usr/bin/env python3
"""
fetch_insider.py — headless insider-transaction fetcher for sarmaaya.pk.

Why this exists: sarmaaya client-loads its `#insider-transactions` table after
hydration from an obfuscated route, so a plain HTTP fetch can't get it (see
DECISIONS.md in the dashboard repo). A real browser engine can, though — verified
2026-06-27 that headless Playwright loads the page (HTTP 200, no Cloudflare block)
and the table renders. This script automates the previously-manual "paste the
rendered DOM" step.

Usage:
    python fetch_insider.py FFC            # -> stocks/FFC/overview/insider.json
    python fetch_insider.py MLCF --out /tmp/x.json

Requires: pip install playwright && python -m playwright install chromium
Writes the same schema the engine's insider.py expects:
    {source, as_of, transactions:[{date(ISO), person, role, action, shares, price, value}]}
On failure (page didn't render / 0 rows) it exits non-zero and writes nothing,
so a flaky fetch never clobbers good data with an empty file.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import sys

from engine.layout import StockPaths

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
ROW_JS = ('els => els.map(tr => Array.from(tr.querySelectorAll("td"))'
          '.map(td => td.innerText.trim()))')


def _to_iso(s: str) -> str | None:
    """'Jun 24, 2026' -> '2026-06-24'. Returns None if unparseable."""
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return dt.datetime.strptime(s.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _num(s: str):
    try:
        return float(str(s).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _rows_to_txns(rows: list[list[str]]) -> list[dict]:
    """Map sarmaaya table rows (Date·Name·Position·Action·Qty·Rate·Attachment)
    to the engine's insider schema, skipping malformed rows."""
    out = []
    for r in rows:
        if len(r) < 6 or not any(c for c in r):
            continue
        date_iso = _to_iso(r[0])
        shares = _num(r[4])
        price = _num(r[5])
        if not date_iso or shares is None or price is None:
            continue
        out.append({
            "date": date_iso,
            "person": r[1].strip(),
            "role": r[2].strip(),
            "action": r[3].strip(),
            "shares": int(shares),
            "price": price,
            "value": round(shares * price),
        })
    return out


def fetch(symbol: str, timeout_ms: int = 45000) -> list[dict]:
    """Render the sarmaaya stock page and extract insider transactions."""
    from playwright.sync_api import sync_playwright  # imported lazily
    url = f"https://sarmaaya.pk/stocks/{symbol.upper()}"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(user_agent=UA)
            page = ctx.new_page()
            resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            status = resp.status if resp else None
            if status and status >= 400:
                raise RuntimeError(f"sarmaaya returned HTTP {status} for {symbol}")
            page.wait_for_selector("#insider-transactions tbody tr", timeout=timeout_ms)
            rows = page.eval_on_selector_all("#insider-transactions tbody tr", ROW_JS)
        finally:
            browser.close()
    return _rows_to_txns(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fetch sarmaaya insider transactions (headless).")
    ap.add_argument("symbol")
    ap.add_argument("--out", help="output path (default: stocks/<SYM>/overview/insider.json)")
    args = ap.parse_args(argv)
    sym = args.symbol.upper()

    try:
        txns = fetch(sym)
    except Exception as e:  # noqa: BLE001 - report cleanly, write nothing
        print(f"fetch_insider {sym}: FAILED — {e!r}", file=sys.stderr)
        return 2
    if not txns:
        print(f"fetch_insider {sym}: no insider rows rendered — writing nothing.", file=sys.stderr)
        return 3

    payload = {
        "source": "sarmaaya.pk (insider transactions, #insider-transactions table)",
        "as_of": dt.date.today().isoformat(),
        "transactions": txns,
    }
    if args.out:
        out_path = args.out
    else:
        overview = StockPaths(sym).overview
        overview.mkdir(parents=True, exist_ok=True)
        out_path = str(overview / "insider.json")
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)
    buys = sum(1 for t in txns if "buy" in t["action"].lower())
    sells = sum(1 for t in txns if "sell" in t["action"].lower())
    print(f"fetch_insider {sym}: wrote {len(txns)} filings ({buys} buys / {sells} sells) "
          f"-> {out_path} (as_of {payload['as_of']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
