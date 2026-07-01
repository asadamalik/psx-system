#!/usr/bin/env python3
"""
ohlc_store.py — persistent per-symbol OHLC history for the PSX dashboard.

The daily market-watch scrape (`psx_auto.fetch_marketwatch`) already captures full
Open/High/Low/Close/Volume for every symbol, but until now only Close/Volume survived
into the charts (the EOD timeseries endpoint has no intraday high/low). This module
persists the real OHLC each run into `psx_data/ohlc.json` so we accumulate a true-H/L
history going forward — for all fetched symbols, not just the top-30.

Store shape (compact, committed between runs):
    { "MLCF": [ {"d":"2026-06-26","o":..,"h":..,"l":..,"c":..,"v":..}, ... ], ... }
bars sorted ascending by date, one per trading day, de-duped by date (re-running a day
overwrites that day — idempotent, matching snapshots.json semantics).
"""
import os
import json

OHLC = "ohlc.json"


def _path(state_dir: str) -> str:
    return os.path.join(state_dir, OHLC)


def load(state_dir: str) -> dict:
    p = _path(state_dir)
    if not os.path.exists(p):
        return {}
    try:
        return json.load(open(p, encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def save(state_dir: str, store: dict) -> None:
    os.makedirs(state_dir, exist_ok=True)
    json.dump(store, open(_path(state_dir), "w", encoding="utf-8"), separators=(",", ":"))


def _put(store: dict, sym: str, bar: dict, overwrite: bool) -> None:
    """Insert/replace one day's bar for a symbol, keeping the series date-sorted."""
    series = store.setdefault(sym, [])
    for i, b in enumerate(series):
        if b["d"] == bar["d"]:
            if overwrite:
                series[i] = bar
            return
    series.append(bar)
    series.sort(key=lambda b: b["d"])


def _bar(date_iso: str, o, h, l, c, v) -> dict | None:
    if c is None:
        return None
    out = {"d": date_iso, "o": o, "h": h, "l": l, "c": c}
    if v is not None:
        try:
            out["v"] = int(v)
        except (TypeError, ValueError):
            pass
    return out


def update_from_rows(store: dict, date_iso: str, rows: list) -> dict:
    """Append today's real OHLC from market-watch rows. Today's bar overwrites
    (idempotent re-runs). `rows` are the dicts from fetch_marketwatch (o,h,l,c,vol)."""
    for r in rows:
        bar = _bar(date_iso, r.get("o"), r.get("h"), r.get("l"), r.get("c"), r.get("vol"))
        if bar:
            _put(store, r["symbol"], bar, overwrite=True)
    return store


def backfill_from_snapshots(store: dict, snaps: list) -> dict:
    """Seed history from past snapshots (each top entry carries o/h/l/c/vol). Only
    fills dates not already present — never clobbers a live-captured bar."""
    for snap in snaps:
        d = snap.get("date")
        if not d:
            continue
        for r in snap.get("top", []):
            bar = _bar(d, r.get("o"), r.get("h"), r.get("l"), r.get("c"), r.get("vol"))
            if bar:
                _put(store, r["symbol"], bar, overwrite=False)
    return store


def _ymd_int(date_iso: str) -> int:
    return int(date_iso.replace("-", ""))


def attach_external_charts(charts: dict, external: dict | None = None) -> dict:
    """Build a chart from an engine export's true OHLC for engine symbols.

    Used for symbols with no dashboard chart (never in the tracked top-30) AND to REPLACE
    a shallow windowed chart when the engine export carries deeper history — the export now
    holds the full stockanalysis series (thousands of real-H/L bars), so we prefer it over
    the ~180-day DPS window whenever it's longer. Non-engine symbols are left untouched."""
    for sym, ext in (external or {}).items():
        bars = ext.get("ohlc") or []
        if not bars:
            continue
        existing = charts.get(sym)
        if existing is not None and len(bars) <= len(existing.get("c") or []):
            continue  # keep the existing chart when it's already at least as deep
        charts[sym] = dict(
            d=[int(b["date"].replace("-", "")) for b in bars],
            o=[b.get("open") for b in bars],
            c=[b.get("close") for b in bars],
            v=[int(b.get("volume") or 0) for b in bars],
            h=[b.get("high") for b in bars],
            l=[b.get("low") for b in bars],
            realHL=True)
    return charts


def merge_into_charts(charts: dict, store: dict, external: dict | None = None) -> dict:
    """Attach real high/low arrays (aligned to each chart's existing `d` YYYYMMDD)
    to `charts[sym]`, so the page can use true H/L instead of synthesising it.

    Priority per symbol: engine export OHLC (true full-history H/L) > persisted store.
    Sets `ch.h`, `ch.l` (None where unknown) and `ch.realHL=True` when at least one
    real bar was matched, so the front-end knows the H/L is genuine for that symbol.
    """
    external = external or {}
    for sym, ch in charts.items():
        dates = ch.get("d") or []
        if not dates:
            continue
        hl: dict[int, tuple] = {}
        # engine export wins — it carries true OHLC for the full series
        ext = external.get(sym.upper())
        for bar in (ext or {}).get("ohlc", []) if ext else []:
            hl[_ymd_int(bar["date"])] = (bar.get("high"), bar.get("low"))
        # fill remaining days from the persisted store
        for bar in store.get(sym, []):
            key = _ymd_int(bar["d"])
            if key not in hl:
                hl[key] = (bar.get("h"), bar.get("l"))
        h_arr, l_arr, matched = [], [], 0
        for dd in dates:
            hi, lo = hl.get(dd, (None, None))
            if hi is not None and lo is not None:
                matched += 1
            h_arr.append(hi)
            l_arr.append(lo)
        if matched:
            ch["h"] = h_arr
            ch["l"] = l_arr
            ch["realHL"] = True
    return charts
