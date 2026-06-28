#!/usr/bin/env python3
"""
export_external.py — one file per symbol for the PSX Volume Monitor dashboard
=============================================================================
Emits a single self-contained JSON per symbol that the dashboard's
external_fundamentals.py drop-folder ingests (psx_data/external/). It carries
both the rich DATA and THIS engine's SCORES, so the dashboard renders our
conviction verdict (not its own 35/30/35).

Field names follow the handoff doc §8 (pb, debt_to_equity, roe_pct, roa_pct,
current_ratio, dividend_yield_pct, dividend_history, cash_mn/debt_mn/equity_mn,
op_cashflow_mn/free_cashflow_mn, insider_tx with real shares/price, true OHLC).

USAGE
  python export_external.py MLCF                 # -> exports/<ts>_MLCF.json
  python export_external.py MLCF FFC --all
  python export_external.py MLCF --out /path/to/psx_data/external

Drop the file into the dashboard's psx_data/external/ and rebuild.
"""

from __future__ import annotations
import os
import sys
import json
import time
import argparse
from pathlib import Path

from engine.layout import StockPaths, list_symbols
from engine import fundamentals as fund_mod
from engine import analysis as analysis_mod
from engine import technical as tech_mod
from engine import scoring as scoring_mod
from engine import psx as psx_mod
from engine import relative_strength as rs_mod
from engine import insider as insider_mod


def _ohlc(symbol):
    p = StockPaths(symbol)
    if not p.historical_csv.exists():
        return []
    df = tech_mod.load_historical(p.historical_csv)
    out = []
    for t, row in df.iterrows():
        rec = {"date": str(t.date()),
               "open": round(float(row["open"]), 2),
               "high": round(float(row["high"]), 2),
               "low": round(float(row["low"]), 2),
               "close": round(float(row["close"]), 2)}
        if "volume" in df.columns and not (row.get("volume") != row.get("volume")):
            try:
                rec["volume"] = int(row["volume"])
            except (TypeError, ValueError):
                pass
        out.append(rec)
    return out


def _pct(x):
    return round(x * 100, 2) if isinstance(x, (int, float)) else None


def build_export(symbol: str, ts: int | None = None) -> dict:
    symbol = symbol.upper()
    fundamentals, _ = fund_mod.merge(symbol)

    tech_snapshot = technical = None
    p = StockPaths(symbol)
    if p.historical_csv.exists():
        tech_snapshot = tech_mod.build_indicators(symbol)
        technical = tech_mod.score_technical(tech_snapshot)

    ca = analysis_mod.analyze(symbol, fundamentals, tech_snapshot)
    m = ca["metrics"]; ext = ca.get("extended", {}); latest = ca["latest"]; g = ca["growth"]
    scores = scoring_mod.final_score(m, technical, tech_snapshot)
    div = psx_mod.divergence(symbol, fundamentals)
    rs = rs_mod.relative_strength(symbol)
    insider = insider_mod.sentiment(symbol)
    # sentiment() caps its transaction list at 8 (a preview for the report); the
    # dashboard wants every filing, so pull the full list straight from the raw file.
    insider_all = insider_mod.load(symbol) or {}

    ov = fundamentals.get("overview", {})
    bsa = fundamentals.get("balance_sheet_annual", {})
    cfa = fundamentals.get("cashflow_annual", {})
    isa = fundamentals.get("income_statement_annual", {})
    isq = fundamentals.get("income_statement_quarterly", {})
    bsq = fundamentals.get("balance_sheet_quarterly", {})
    cfq = fundamentals.get("cashflow_quarterly", {})
    divd = fundamentals.get("dividends", {})

    # "Limited data": no consolidated balance-sheet / cash-flow source exists for this stock
    # (DPS-only small caps, plus insurers / takaful / REITs whose statements omit those rows).
    # Income + price + valuation are still present, but the balance-sheet and cash-flow cards
    # render "—" and the fundamental score runs on thin inputs — so the dashboard flags it.
    limited_data = not bool(bsa) and not bool(cfa)

    # free-cash-flow series (per fiscal year) for the dashboard
    ocf_map = cfa.get("cash_from_operations", {})
    capex_map = cfa.get("capex", {})
    fcf_mn = {y: ocf_map[y] - abs(capex_map[y])
              for y in ocf_map if ocf_map.get(y) is not None and capex_map.get(y) is not None}

    # 52-week range from the last ~252 trading bars; free float from PSX DPS (psx_official.json).
    # These let an engine-only symbol (not in the dashboard's scraped top-30) fill the
    # Company-profile / Ownership cards instead of showing "—".
    ohlc = _ohlc(symbol)
    _recent = ohlc[-252:] if len(ohlc) > 252 else ohlc
    high52 = round(max((b["high"] for b in _recent), default=0.0), 2) if _recent else None
    low52 = round(min((b["low"] for b in _recent), default=0.0), 2) if _recent else None
    dps_off = psx_mod.load_dps(symbol) or {}
    _ff = dps_off.get("free_float_pct")
    free_float_pct = round(_ff * 100, 1) if isinstance(_ff, (int, float)) else None

    export = {
        "symbol": symbol,
        "name": ov.get("company_name") or symbol,
        "sector": ov.get("sector"),
        "currency": ov.get("currency", "PKR"),
        "as_of": (tech_snapshot or {}).get("as_of"),
        "generated_ts": ts or int(time.time()),
        "source": "stock-agent-claude (Investing.com + PSX DPS)",
        "limited_data": limited_data,

        # ---- price (true OHLC, source of truth) ----
        "ohlc": ohlc,

        # ---- valuation / ratios (handoff §8 names) ----
        "pe": m.get("pe_ratio"),
        "pb": m.get("price_to_book"),
        "peg": m.get("peg"),
        "ps": ext.get("ps_ratio"),
        "ev_ebitda": ext.get("ev_ebitda"),
        "debt_to_equity": m.get("debt_to_equity"),
        "current_ratio": m.get("current_ratio"),
        "quick_ratio": ext.get("quick_ratio"),
        "roe_pct": _pct(m.get("roe")),
        "roa_pct": _pct(m.get("roa")),
        "roic_pct": _pct(ext.get("roic")),
        "gross_margin_pct": _pct(m.get("gross_margin")),
        "operating_margin_pct": _pct(m.get("operating_margin")),
        "net_margin_pct": _pct(m.get("net_margin")),
        "market_cap": ca["derived"].get("market_cap"),
        "shares_outstanding": ov.get("shares_outstanding"),
        "free_float_pct": free_float_pct,
        "high52": high52,
        "low52": low52,

        # ---- statement series (in millions) ----
        "eps_history": isa.get("eps", {}),
        "revenue_mn": isa.get("revenue", {}),
        "gross_profit_mn": isa.get("gross_profit", {}),
        "operating_income_mn": isa.get("operating_income", {}),
        "net_income_mn": isa.get("net_income", {}),
        "interest_expense_mn": isa.get("interest_expense", {}),
        "current_assets_mn": bsa.get("current_assets", {}),
        "cash_mn": bsa.get("cash_and_equivalents", {}),
        "inventory_mn": bsa.get("inventory", {}),
        "total_assets_mn": bsa.get("total_assets", {}),
        "current_liabilities_mn": bsa.get("current_liabilities", {}),
        "total_liabilities_mn": bsa.get("total_liabilities", {}),
        "debt_mn": bsa.get("total_debt", {}),
        "equity_mn": bsa.get("total_equity", {}),
        "op_cashflow_mn": ocf_map,
        "cf_investing_mn": cfa.get("cash_from_investing", {}),
        "cf_financing_mn": cfa.get("cash_from_financing", {}),
        "capex_mn": capex_map,
        "free_cashflow_mn": fcf_mn,

        # ---- quarterly statement series (period-end YYYY-MM keys, millions) ----
        "quarterly": {
            "revenue_mn": isq.get("revenue", {}),
            "gross_profit_mn": isq.get("gross_profit", {}),
            "operating_income_mn": isq.get("operating_income", {}),
            "net_income_mn": isq.get("net_income", {}),
            "eps_history": isq.get("eps", {}),
            "interest_expense_mn": isq.get("interest_expense", {}),
            "current_assets_mn": bsq.get("current_assets", {}),
            "cash_mn": bsq.get("cash_and_equivalents", {}),
            "inventory_mn": bsq.get("inventory", {}),
            "total_assets_mn": bsq.get("total_assets", {}),
            "current_liabilities_mn": bsq.get("current_liabilities", {}),
            "total_liabilities_mn": bsq.get("total_liabilities", {}),
            "debt_mn": bsq.get("total_debt", {}),
            "equity_mn": bsq.get("total_equity", {}),
            "op_cashflow_mn": cfq.get("cash_from_operations", {}),
            "cf_investing_mn": cfq.get("cash_from_investing", {}),
            "cf_financing_mn": cfq.get("cash_from_financing", {}),
            "capex_mn": cfq.get("capex", {}),
        },
        "revenue_qoq_pct": _pct(ext.get("revenue_qoq")),
        "revenue_yoy_pct": _pct(ext.get("revenue_yoy")),
        "eps_qoq_pct": _pct(ext.get("eps_qoq")),
        "eps_yoy_pct": _pct(ext.get("eps_yoy")),
        "ttm_revenue_mn": ext.get("ttm_revenue"),
        "ttm_net_income_mn": ext.get("ttm_net_income"),

        # ---- growth ----
        "revenue_cagr_5y_pct": _pct(g.get("revenue_growth_5y")),
        "revenue_cagr_3y_pct": _pct(ext.get("revenue_cagr_3y")),
        "eps_cagr_3y_pct": _pct(ext.get("eps_cagr_3y")),

        # ---- valuation extras ----
        "industry_pe": fundamentals.get("ratios", {}).get("industry_pe"),

        # ---- dividends ----
        "dividend_yield_pct": _pct(divd.get("yield")),
        "dividend_per_share_ttm": divd.get("per_share_ttm"),
        "dividend_history": divd.get("history", []),

        # ---- earnings ----
        "earnings": fundamentals.get("earnings", {}),

        # ---- real insider transactions (shares + price) ----
        "insider_tx": insider_all.get("transactions", []),
        "insider_sentiment": (insider or {}).get("sentiment"),
        # last time the insider filings were captured (drives the dashboard's
        # "Nd old — refresh suggested" staleness hint); from insider.json's as_of.
        "insider_as_of": insider_all.get("as_of"),

        # ---- THIS engine's scores / verdict (dashboard renders these) ----
        "scores": {
            "fundamental_score": scores["fundamental_score"],
            "technical_score": scores["technical_score"],
            "overall_score": scores["overall_score"],
            "rating": scores["rating"],
            "risk": scores["risk"],
            "pillars": scores["fundamental_detail"]["pillars"],
            "weights": scores["weights"],
        },
        "technical_snapshot": tech_snapshot,
        "technical_read": technical,
        "earnings_basis_divergence": div,
        "relative_strength": rs,
    }
    return export


def main():
    ap = argparse.ArgumentParser(description="Export per-symbol JSON for the PSX dashboard")
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default=os.environ.get("PSX_EXTERNAL_DIR", "exports"),
                    help="output dir; defaults to $PSX_EXTERNAL_DIR (set this to the dashboard's psx_data/external)")
    ap.add_argument("--clean", action="store_true",
                    help="remove prior *_<SYM>.json exports first (keeps the folder tidy on full re-exports)")
    args = ap.parse_args()

    symbols = list_symbols() if args.all else [s.upper() for s in args.symbols]
    if not symbols:
        ap.error("give symbols or --all")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.clean:
        for f in out_dir.glob("*.json"):
            try:
                f.unlink()
            except OSError as e:
                print(f"[clean] could not remove {f.name}: {e}")

    ts = int(time.time())          # one shared prefix for the whole batch run
    manifest = []
    for sym in symbols:
        try:
            data = build_export(sym, ts)
        except Exception as e:
            print(f"{sym}: SKIPPED ({e})")
            continue
        path = out_dir / f"{ts}_{sym}.json"
        path.write_text(json.dumps(data, indent=2))
        manifest.append({
            "symbol": sym, "file": path.name, "as_of": data["as_of"],
            "overall_score": data["scores"]["overall_score"],
            "rating": data["scores"]["rating"], "risk": data["scores"]["risk"],
            "ohlc_bars": len(data["ohlc"]),
        })
        print(f"{sym}: {path.name}  ({len(data['ohlc'])} bars, "
              f"score {data['scores']['overall_score']} {data['scores']['rating']})")

    # universe manifest/index — lets the dashboard list & rank all exported symbols
    (out_dir / "manifest.json").write_text(json.dumps(
        {"generated_ts": ts, "count": len(manifest), "symbols": manifest}, indent=2))
    print(f"\nmanifest: {out_dir/'manifest.json'}  ({len(manifest)} symbols)")


if __name__ == "__main__":
    main()
