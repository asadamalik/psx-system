#!/usr/bin/env python3
"""
update_prices.py — append daily OHLCV to a stock's price history
================================================================
Source: PSX DPS company page (https://dps.psx.com.pk/company/<SYM>), which
publishes the latest trading day's full Open / High / Low / Close / Volume.

Because the fetch runs through Claude's web tool (the sandbox is firewalled),
the daily flow is:

  1. Claude fetches https://dps.psx.com.pk/company/<SYM> (in a chat or a
     scheduled task) and reads the QUOTE block: the "As of <date>" line and
     Open / High / Low / Volume, plus the headline price (= close).
  2. Claude calls this script with those values; it appends one row to
     stocks/<SYM>/technical/historical.csv, de-duplicating by date and
     keeping the file sorted (newest first, matching the Investing.com export).
  3. `python run.py <SYM>` recomputes indicators + score.

USAGE
  python update_prices.py MLCF --date "Jun 18, 2026" \
      --open 100.01 --high 103.19 --low 100.01 --close 102.47 --volume 32650385

Dates are normalized, so "Jun 18, 2026" / "2026-06-18" / "18/06/2026" all work.
Re-running for a date that already exists overwrites that row (idempotent).
"""

from __future__ import annotations
import argparse
import sys

import pandas as pd

from engine.layout import StockPaths

COLUMNS = ["date", "close", "open", "high", "low", "volume", "change_pct"]


def _norm_date(s: str) -> pd.Timestamp:
    d = pd.to_datetime(s, errors="coerce")
    if pd.isna(d):
        raise ValueError(f"unparseable date: {s!r}")
    return d.normalize()


def append_row(symbol: str, date: str, open_, high, low, close, volume,
               change_pct: str | None = None) -> dict:
    p = StockPaths(symbol).ensure()
    csv = p.historical_csv

    if csv.exists():
        df = pd.read_csv(csv)
        date_col = next((c for c in df.columns if c.lower() in
                         ("date", "datetime", "time")), df.columns[0])
        df["_d"] = pd.to_datetime(df[date_col], errors="coerce").dt.normalize()
    else:
        df = pd.DataFrame(columns=COLUMNS)
        df["_d"] = pd.to_datetime([])
        date_col = "date"

    d = _norm_date(date)
    # build the new row using the existing column names where possible
    row = {date_col: d.strftime("%b %d, %Y"),
           "close": close, "open": open_, "high": high, "low": low,
           "volume": int(volume) if volume not in (None, "") else None}
    if "change_pct" in df.columns and change_pct is not None:
        row["change_pct"] = change_pct
    row["_d"] = d

    df = df[df["_d"] != d]                      # drop existing same-date row
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df = df.sort_values("_d", ascending=False)  # newest first
    n = len(df)
    df = df.drop(columns=["_d"])
    df.to_csv(csv, index=False)
    return {"symbol": p.symbol, "rows": n, "added": d.strftime("%Y-%m-%d"),
            "path": str(csv)}


def main():
    ap = argparse.ArgumentParser(description="Append a daily OHLCV row from PSX DPS")
    ap.add_argument("symbol")
    ap.add_argument("--date", required=True, help='e.g. "Jun 18, 2026"')
    ap.add_argument("--open", type=float, required=True, dest="open_")
    ap.add_argument("--high", type=float, required=True)
    ap.add_argument("--low", type=float, required=True)
    ap.add_argument("--close", type=float, required=True)
    ap.add_argument("--volume", type=float, required=True)
    ap.add_argument("--change-pct", default=None)
    args = ap.parse_args()

    info = append_row(args.symbol.upper(), args.date, args.open_, args.high,
                      args.low, args.close, args.volume, args.change_pct)
    print(f"{info['symbol']}: appended {info['added']} -> {info['rows']} rows total")
    print(f"  {info['path']}")
    print(f"  next: python run.py {info['symbol']}")


if __name__ == "__main__":
    main()
