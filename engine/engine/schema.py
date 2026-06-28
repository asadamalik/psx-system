"""
schema.py
---------
Lightweight, dependency-free schemas for every structured JSON file the
engine consumes. Because extraction is done by an LLM (Claude in Cowork),
validation here is the safety net: it confirms the extracted JSON has the
right shape before any analysis runs.

Schema field types:
    "year_map"  -> dict mapping period label (e.g. "2024", "Q1 2025") to number
    "number"    -> int/float (or null)
    "string"    -> str (or null)
    "list"      -> list
    "object"    -> dict

validate(section, data) -> (ok: bool, errors: list[str], warnings: list[str])
"""

from __future__ import annotations
from numbers import Number


# Each schema: {field: {"type": ..., "required": bool}}
SECTION_SCHEMAS: dict[str, dict] = {
    # ---- Financial statements (period-keyed maps) ----
    "income_statement_annual": {
        "revenue":          {"type": "year_map", "required": True},
        "gross_profit":     {"type": "year_map", "required": False},
        "operating_income": {"type": "year_map", "required": False},
        "net_income":       {"type": "year_map", "required": True},
        "eps":              {"type": "year_map", "required": False},
        "interest_expense": {"type": "year_map", "required": False},
        "cost_of_revenue":  {"type": "year_map", "required": False},
        "ebitda":           {"type": "year_map", "required": False},
        "income_tax":       {"type": "year_map", "required": False},
        "ebt":              {"type": "year_map", "required": False},
    },
    "balance_sheet_annual": {
        "total_assets":        {"type": "year_map", "required": True},
        "total_liabilities":   {"type": "year_map", "required": False},
        "total_equity":        {"type": "year_map", "required": True},
        "current_assets":      {"type": "year_map", "required": False},
        "current_liabilities": {"type": "year_map", "required": False},
        "inventory":           {"type": "year_map", "required": False},
        "cash_and_equivalents":{"type": "year_map", "required": False},
        "total_debt":          {"type": "year_map", "required": False},
        "total_receivables":   {"type": "year_map", "required": False},
    },
    "cashflow_annual": {
        "cash_from_operations": {"type": "year_map", "required": True},
        "cash_from_investing":  {"type": "year_map", "required": False},
        "cash_from_financing":  {"type": "year_map", "required": False},
        "capex":                {"type": "year_map", "required": False},
        "net_change_in_cash":   {"type": "year_map", "required": False},
    },
    # ---- Ratios (flat) ----
    "ratio": {
        "pe_ratio":        {"type": "number", "required": False},
        "price_to_book":   {"type": "number", "required": False},
        "roe":             {"type": "number", "required": False},
        "roa":             {"type": "number", "required": False},
        "debt_to_equity":  {"type": "number", "required": False},
        "current_ratio":   {"type": "number", "required": False},
        "gross_margin":    {"type": "number", "required": False},
        "operating_margin":{"type": "number", "required": False},
        "net_margin":      {"type": "number", "required": False},
        "eps_growth_5y":   {"type": "number", "required": False},
        "sales_growth_5y": {"type": "number", "required": False},
        "interest_coverage":{"type": "number", "required": False},
        "peg":             {"type": "number", "required": False},
    },
    # ---- Earnings ----
    "earnings": {
        "latest_eps":       {"type": "number", "required": False},
        "forecast_eps":     {"type": "number", "required": False},
        "earnings_surprise":{"type": "number", "required": False},
        "history":          {"type": "list",   "required": False},
    },
    # ---- Dividends ----
    "dividends": {
        "yield":             {"type": "number", "required": False},
        "payout_ratio":      {"type": "number", "required": False},
        "history":           {"type": "list",   "required": False},
        "last_dividend_year":{"type": "number", "required": False},
        "note":              {"type": "string", "required": False},
    },
    # ---- Overview ----
    "overview": {
        "company_name":       {"type": "string", "required": False},
        "sector":             {"type": "string", "required": False},
        "industry":           {"type": "string", "required": False},
        "market_cap":         {"type": "number", "required": False},
        "shares_outstanding": {"type": "number", "required": False},
        "current_price":      {"type": "number", "required": False},
        "currency":           {"type": "string", "required": False},
    },
    # ---- Profile ----
    "profile": {
        "description":       {"type": "string", "required": False},
        "business_segments": {"type": "list",   "required": False},
        "products":          {"type": "list",   "required": False},
        "website":           {"type": "string", "required": False},
        "fiscal_year_end":   {"type": "string", "required": False},
        "auditor":           {"type": "string", "required": False},
        "registrar":         {"type": "string", "required": False},
        "address":           {"type": "string", "required": False},
        "key_people":        {"type": "object", "required": False},
        "holding_company":   {"type": "string", "required": False},
        "source":            {"type": "string", "required": False},
    },
    # ---- Ownership ----
    "ownership": {
        "insiders":           {"type": "object", "required": False},
        "institutions":       {"type": "object", "required": False},
        "free_float":         {"type": "number", "required": False},
        "free_float_shares":  {"type": "number", "required": False},
        "shares_outstanding": {"type": "number", "required": False},
        "sponsors":           {"type": "object", "required": False},
        "note":               {"type": "string", "required": False},
        "source":             {"type": "string", "required": False},
    },
    # ---- Shareholding pattern ----
    "shareholding": {
        "categories": {"type": "object", "required": False},
        "as_of":      {"type": "string", "required": False},
        "source":     {"type": "string", "required": False},
    },
    # ---- Smart money / FIPI flows ----
    "fipi": {
        "flows":        {"type": "object", "required": False},
        "block_trades": {"type": "list",   "required": False},
        "period":       {"type": "string", "required": False},
        "as_of":        {"type": "string", "required": False},
        "source":       {"type": "string", "required": False},
    },
    # ---- Monthly sales ----
    "monthly_sales": {
        "months": {"type": "list",   "required": False},
        "unit":   {"type": "string", "required": False},
        "as_of":  {"type": "string", "required": False},
        "source": {"type": "string", "required": False},
    },
    # ---- Insider transactions ----
    "insider": {
        "transactions": {"type": "list",   "required": False},
        "as_of":        {"type": "string", "required": False},
        "source":       {"type": "string", "required": False},
    },
    # ---- Announcements ----
    "announcements": {
        "financial_results": {"type": "list", "required": False},
        "board_meetings":    {"type": "list", "required": False},
        "other":             {"type": "list", "required": False},
        "as_of":             {"type": "string", "required": False},
        "source":            {"type": "string", "required": False},
    },
}

# Quarterly statements reuse the annual schema shape
SECTION_SCHEMAS["income_statement_quarterly"] = SECTION_SCHEMAS["income_statement_annual"]
SECTION_SCHEMAS["balance_sheet_quarterly"] = SECTION_SCHEMAS["balance_sheet_annual"]
SECTION_SCHEMAS["cashflow_quarterly"] = SECTION_SCHEMAS["cashflow_annual"]


def _is_number(x):
    return x is None or (isinstance(x, Number) and not isinstance(x, bool))


def _check_year_map(field, value, errors, warnings):
    if not isinstance(value, dict):
        errors.append(f"{field}: expected period->number map, got {type(value).__name__}")
        return
    if not value:
        warnings.append(f"{field}: empty map")
    for k, v in value.items():
        if not isinstance(k, str):
            warnings.append(f"{field}: period key '{k}' is not a string")
        if not _is_number(v):
            errors.append(f"{field}['{k}']: expected number, got {type(v).__name__}")


def validate(section: str, data: dict):
    """Returns (ok, errors, warnings)."""
    errors, warnings = [], []
    schema = SECTION_SCHEMAS.get(section)
    if schema is None:
        return True, [], [f"no schema for section '{section}' (skipping validation)"]
    if not isinstance(data, dict):
        return False, [f"{section}: top-level must be an object"], []

    for field, spec in schema.items():
        present = field in data and data[field] not in (None, {}, [])
        if not present:
            if spec["required"]:
                errors.append(f"{section}: required field '{field}' missing/empty")
            continue
        value = data[field]
        t = spec["type"]
        if t == "year_map":
            _check_year_map(f"{section}.{field}", value, errors, warnings)
        elif t == "number":
            if not _is_number(value):
                errors.append(f"{section}.{field}: expected number")
        elif t == "string":
            if not isinstance(value, str):
                errors.append(f"{section}.{field}: expected string")
        elif t == "list":
            if not isinstance(value, list):
                errors.append(f"{section}.{field}: expected list")
        elif t == "object":
            if not isinstance(value, dict):
                errors.append(f"{section}.{field}: expected object")

    # Flag unknown fields (non-fatal)
    for field in data:
        if field not in schema:
            warnings.append(f"{section}: unexpected field '{field}' (kept, not validated)")

    return (len(errors) == 0), errors, warnings
