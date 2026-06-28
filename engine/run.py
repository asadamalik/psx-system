#!/usr/bin/env python3
"""
run.py — PSX Stock Analysis Orchestrator
========================================
Pipeline (everything downstream of structured JSON is automated):

    raw/*.txt  --(Claude extraction)-->  fundamentals/*.json + overview/*.json
                                              |
                                              v
    historical.csv --> technical/indicators.json --> technical score
                                              |
              fundamentals.json (merge) ------+
                       |
                       v
            analysis/company_analysis.json
                       |
                       v
                  scoring  -->  reports/<SYM>_report.md + .json

USAGE
-----
    python run.py MLCF                 # one symbol
    python run.py MLCF FFC LUCK        # several
    python run.py --all                # every symbol under stocks/
    python run.py MLCF --quiet

Extraction (raw .txt -> JSON) is done by Claude in Cowork, not by this script.
run.py reports which sections are still missing so you know what to extract.
"""

from __future__ import annotations
import sys
import argparse
import traceback

from engine.layout import StockPaths, list_symbols
from engine import fundamentals as fund_mod
from engine import analysis as analysis_mod
from engine import technical as tech_mod
from engine import scoring as scoring_mod
from engine import report as report_mod
from engine import report_html as report_html_mod
from engine import psx as psx_mod
from engine import relative_strength as rs_mod
from engine import insider as insider_mod


def _list_raw_files(p: StockPaths):
    """List raw source files actually present (any format: fetched .md or
    manually-pasted .txt), so the report reflects reality regardless of how
    the data was sourced."""
    if not p.raw.exists():
        return []
    return sorted(f.name for f in p.raw.iterdir()
                  if f.is_file() and not f.name.startswith("."))


def run_symbol(symbol: str, quiet=False) -> dict:
    def log(*a):
        if not quiet:
            print(*a)

    p = StockPaths(symbol).ensure()
    log(f"\n=== {p.symbol} ===")

    raw_files = _list_raw_files(p)
    log(f"  raw files   : {', '.join(raw_files) or '(none)'}")

    # --- technical ---
    tech_snapshot, technical = None, None
    if p.historical_csv.exists():
        try:
            tech_snapshot = tech_mod.build_indicators(symbol)
            technical = tech_mod.score_technical(tech_snapshot)
            log(f"  technical   : score {technical['technical_score']} "
                f"({technical['trend']}, {technical['momentum']})")
        except Exception as e:
            log(f"  technical   : ERROR {e}")
    else:
        log("  technical   : no historical.csv")

    # --- fundamentals merge + validation ---
    fundamentals, val_report = fund_mod.merge(symbol)
    extracted = [s for s, r in val_report.items() if r["present"]]
    not_extracted = [s for s, r in val_report.items()
                     if not r["present"] and p.raw_file(s).exists()]
    bad = {s: r["errors"] for s, r in val_report.items() if r["present"] and not r["ok"]}
    log(f"  extracted   : {', '.join(extracted) or '(none)'}")
    if not_extracted:
        log(f"  NEEDS EXTRACTION (raw exists, no JSON yet): {', '.join(not_extracted)}")
    for s, errs in bad.items():
        log(f"  SCHEMA FAIL [{s}]: {errs}")

    # --- analysis ---
    company_analysis = analysis_mod.analyze(symbol, fundamentals, tech_snapshot)

    # --- scoring ---
    scores = scoring_mod.final_score(company_analysis["metrics"], technical, tech_snapshot)
    log(f"  scores      : F={scores['fundamental_score']} T={scores['technical_score']} "
        f"-> overall {scores['overall_score']} | {scores['rating']} | risk {scores['risk']}")

    # --- dual-source divergence (DPS vs Investing), if DPS data present ---
    div = psx_mod.divergence(symbol, fundamentals)
    if div and div["flagged"]:
        log(f"  divergence  : FLAGGED  EPS {div['eps_divergence']*100:+.0f}% "
            f"(unconsolidated vs consolidated, FY{div['year']})")

    # --- relative strength vs KSE100 (if index data present) ---
    rs = rs_mod.relative_strength(symbol)
    if rs:
        log(f"  rel strength: {rs['rating']} (avg outperf "
            f"{(rs['avg_outperformance'] or 0)*100:+.1f}% vs KSE100, as of {rs['as_of']})")

    # --- insider sentiment (if insider.json present) ---
    insider = insider_mod.sentiment(symbol)
    if insider:
        log(f"  insider     : {insider['sentiment']} "
            f"({insider['buys']} buys / {insider['sells']} sells)")

    # --- reports (markdown + color-coded HTML) ---
    report_path = report_mod.build(symbol, fundamentals, company_analysis,
                                   tech_snapshot, technical, scores)
    html_path = report_html_mod.build(symbol, fundamentals, company_analysis,
                                      tech_snapshot, technical, scores, div, rs, insider)
    log(f"  report      : {report_path}")
    log(f"  report(html): {html_path}")

    return {
        "symbol": symbol,
        "scores": scores,
        "needs_extraction": not_extracted,
        "schema_failures": bad,
        "report": str(report_path),
    }


def main():
    ap = argparse.ArgumentParser(description="PSX stock analysis orchestrator")
    ap.add_argument("symbols", nargs="*", help="Ticker symbols (e.g. MLCF FFC)")
    ap.add_argument("--all", action="store_true", help="Process every symbol under stocks/")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    symbols = list_symbols() if args.all else [s.upper() for s in args.symbols]
    if not symbols:
        ap.error("Give symbols (e.g. `python run.py MLCF`) or use --all.")

    results = []
    for sym in symbols:
        try:
            results.append(run_symbol(sym, quiet=args.quiet))
        except Exception as e:
            print(f"\n[{sym}] FAILED: {e}")
            traceback.print_exc()

    if len(results) > 1:
        print("\n=== SUMMARY ===")
        print(f"{'Symbol':<8}{'Overall':>8}{'Rating':>14}{'Risk':>10}")
        for r in results:
            s = r["scores"]
            print(f"{r['symbol']:<8}{str(s['overall_score']):>8}{s['rating']:>14}{s['risk']:>10}")


if __name__ == "__main__":
    main()
