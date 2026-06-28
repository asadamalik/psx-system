"""
fundamentals.py
---------------
Merges the individually-extracted section JSON files in fundamentals/ (and
overview/) into a single fundamentals.json with the project's frozen schema.

Reads whatever exists; missing sections become empty objects. Each section is
schema-validated on the way in, and validation issues are returned so the
orchestrator can surface them.
"""

from __future__ import annotations
import json

from .layout import StockPaths
from . import schema

# section name -> directory ("fundamentals" or "overview")
SECTION_LOCATION = {
    "income_statement_annual": "fundamentals",
    "income_statement_quarterly": "fundamentals",
    "balance_sheet_annual": "fundamentals",
    "balance_sheet_quarterly": "fundamentals",
    "cashflow_annual": "fundamentals",
    "cashflow_quarterly": "fundamentals",
    "ratio": "fundamentals",
    "earnings": "fundamentals",
    "dividends": "fundamentals",
    "overview": "overview",
    "profile": "overview",
    "ownership": "overview",
    "announcements": "overview",
    "insider": "overview",
    "shareholding": "overview",
    "fipi": "overview",
    "monthly_sales": "overview",
}


def _read_json(path):
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def merge(symbol: str):
    """
    Build fundamentals.json. Returns (fundamentals_dict, validation_report).
    validation_report = {section: {"present": bool, "ok": bool, "errors": [...], "warnings": [...]}}
    """
    p = StockPaths(symbol).ensure()
    report = {}
    loaded = {}

    for section, where in SECTION_LOCATION.items():
        base = p.fundamentals if where == "fundamentals" else p.overview
        data = _read_json(base / f"{section}.json")
        if data is None:
            report[section] = {"present": False, "ok": False, "errors": [], "warnings": []}
            continue
        ok, errs, warns = schema.validate(section, data)
        report[section] = {"present": True, "ok": ok, "errors": errs, "warnings": warns}
        loaded[section] = data

    fundamentals = {
        "symbol": p.symbol,
        "income_statement_annual": loaded.get("income_statement_annual", {}),
        "balance_sheet_annual": loaded.get("balance_sheet_annual", {}),
        "cashflow_annual": loaded.get("cashflow_annual", {}),
        "income_statement_quarterly": loaded.get("income_statement_quarterly", {}),
        "balance_sheet_quarterly": loaded.get("balance_sheet_quarterly", {}),
        "cashflow_quarterly": loaded.get("cashflow_quarterly", {}),
        "ratios": loaded.get("ratio", {}),
        "earnings": loaded.get("earnings", {}),
        "dividends": loaded.get("dividends", {}),
        "overview": loaded.get("overview", {}),
        "profile": loaded.get("profile", {}),
        "ownership": loaded.get("ownership", {}),
        "announcements": loaded.get("announcements", {}),
        "insider": loaded.get("insider", {}),
        "shareholding": loaded.get("shareholding", {}),
        "fipi": loaded.get("fipi", {}),
        "monthly_sales": loaded.get("monthly_sales", {}),
    }

    with open(p.fundamentals_json, "w") as f:
        json.dump(fundamentals, f, indent=2)

    return fundamentals, report
