"""
layout.py
---------
The FROZEN folder structure. Every path the engine touches is resolved here,
so the layout can never drift.

stocks/<SYMBOL>/
    raw/          source-of-truth .txt copied from Investing.com (never modified)
    fundamentals/ structured JSON extracted from raw/  + merged fundamentals.json
    technical/    historical.csv/json/xlsx + indicators.json
    analysis/     company_analysis.json
    overview/     overview.json, profile.json, ownership.json
    reports/      <SYMBOL>_report.md / .json
"""

from __future__ import annotations
from pathlib import Path

# Project root = parent of the engine/ package
ROOT = Path(__file__).resolve().parent.parent
STOCKS_DIR = ROOT / "stocks"

SUBDIRS = ["raw", "fundamentals", "technical", "analysis", "overview", "reports"]


class StockPaths:
    """Resolves and (optionally) creates all paths for one symbol."""

    def __init__(self, symbol: str):
        self.symbol = symbol.upper()
        self.base = STOCKS_DIR / self.symbol

    # directories -----------------------------------------------------------
    @property
    def raw(self): return self.base / "raw"
    @property
    def fundamentals(self): return self.base / "fundamentals"
    @property
    def technical(self): return self.base / "technical"
    @property
    def analysis(self): return self.base / "analysis"
    @property
    def overview(self): return self.base / "overview"
    @property
    def reports(self): return self.base / "reports"

    # key files -------------------------------------------------------------
    @property
    def historical_csv(self): return self.technical / "historical.csv"
    @property
    def historical_json(self): return self.technical / "historical.json"
    @property
    def indicators_json(self): return self.technical / "indicators.json"
    @property
    def fundamentals_json(self): return self.fundamentals / "fundamentals.json"
    @property
    def company_analysis(self): return self.analysis / "company_analysis.json"
    @property
    def report_md(self): return self.reports / f"{self.symbol}_report.md"
    @property
    def report_html(self): return self.reports / f"{self.symbol}_report.html"
    @property
    def report_json(self): return self.reports / f"{self.symbol}_report.json"

    def raw_file(self, section: str) -> Path:
        return self.raw / f"{section}.txt"

    def section_json(self, section: str) -> Path:
        return self.fundamentals / f"{section}.json"

    def ensure(self):
        """Create the frozen subdirectory tree for this symbol."""
        for d in SUBDIRS:
            (self.base / d).mkdir(parents=True, exist_ok=True)
        return self


def list_symbols() -> list[str]:
    """Stock symbols under stocks/, excluding internal dirs (e.g. _market)."""
    if not STOCKS_DIR.exists():
        return []
    return sorted(p.name for p in STOCKS_DIR.iterdir()
                  if p.is_dir() and not p.name.startswith("_") and not p.name.startswith("."))
