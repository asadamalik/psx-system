"""
analysis.py
-----------
Turns merged fundamentals.json into analysis/company_analysis.json:
  - 5-year growth (revenue, net income, equity) and debt change
  - latest snapshot values
  - a normalized metric dictionary (keyed to config.FUND_THRESHOLDS) that
    prefers extracted ratios and derives the rest from the statements

The normalized "metrics" block is what the scoring engine consumes, so all
metric sourcing/derivation logic lives here.
"""

from __future__ import annotations
import re
import json
import math

from .layout import StockPaths


# ---------------------------------------------------------------------------
# period-map helpers
# ---------------------------------------------------------------------------
def _year_of(label: str):
    m = re.search(r"(19|20)\d{2}", str(label))
    return int(m.group()) if m else None


def _sorted_series(year_map: dict):
    """Return list of (year:int, value:float) sorted ascending; skips junk."""
    if not isinstance(year_map, dict):
        return []
    items = []
    for k, v in year_map.items():
        y = _year_of(k)
        if y is None or v is None:
            continue
        try:
            items.append((y, float(v)))
        except (TypeError, ValueError):
            continue
    items.sort(key=lambda t: t[0])
    return items


def _latest(year_map: dict):
    s = _sorted_series(year_map)
    return s[-1][1] if s else None


def _cagr(year_map: dict, max_years: int = 5):
    """CAGR between earliest (within window) and latest. None if not computable."""
    s = _sorted_series(year_map)
    if len(s) < 2:
        return None
    window = s[-(max_years + 1):] if len(s) > max_years + 1 else s
    (y0, v0), (y1, v1) = window[0], window[-1]
    span = y1 - y0
    if span <= 0 or v0 is None or v1 is None:
        return None
    if v0 > 0 and v1 > 0:
        return (v1 / v0) ** (1.0 / span) - 1.0
    # negative/zero base: fall back to total simple change annualized sign-wise
    if v0 != 0:
        return (v1 - v0) / abs(v0) / span
    return None


def _safe_div(a, b):
    try:
        if a is None or b in (None, 0):
            return None
        return a / b
    except (TypeError, ZeroDivisionError):
        return None


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def analyze(symbol: str, fundamentals: dict, tech_snapshot: dict | None = None) -> dict:
    p = StockPaths(symbol).ensure()
    isa = fundamentals.get("income_statement_annual", {})
    bsa = fundamentals.get("balance_sheet_annual", {})
    cfa = fundamentals.get("cashflow_annual", {})
    ratios = fundamentals.get("ratios", {})
    overview = fundamentals.get("overview", {})

    # ---- growth ----
    growth = {
        "revenue_growth_5y": _cagr(isa.get("revenue", {})),
        "net_income_growth_5y": _cagr(isa.get("net_income", {})),
        "equity_growth_5y": _cagr(bsa.get("total_equity", {})),
    }
    debt_series = _sorted_series(bsa.get("total_debt", {}))
    if len(debt_series) >= 2 and debt_series[0][1]:
        growth["debt_change_5y"] = (debt_series[-1][1] - debt_series[0][1]) / abs(debt_series[0][1])
    else:
        growth["debt_change_5y"] = None

    # ---- latest snapshot ----
    latest = {
        "revenue": _latest(isa.get("revenue", {})),
        "net_income": _latest(isa.get("net_income", {})),
        "equity": _latest(bsa.get("total_equity", {})),
        "total_assets": _latest(bsa.get("total_assets", {})),
        "total_debt": _latest(bsa.get("total_debt", {})),
        "operating_cash_flow": _latest(cfa.get("cash_from_operations", {})),
        "capex": _latest(cfa.get("capex", {})),
    }

    # ---- normalized metrics (prefer extracted ratios, derive otherwise) ----
    rev = latest["revenue"]
    ni = latest["net_income"]
    eq = latest["equity"]
    ta = latest["total_assets"]
    debt = latest["total_debt"]
    gp = _latest(isa.get("gross_profit", {}))
    oi = _latest(isa.get("operating_income", {}))
    ie = _latest(isa.get("interest_expense", {}))
    ca = _latest(bsa.get("current_assets", {}))
    cl = _latest(bsa.get("current_liabilities", {}))
    ocf = latest["operating_cash_flow"]
    capex = latest["capex"]
    fcf = (ocf - abs(capex)) if (ocf is not None and capex is not None) else None

    def pick(ratio_key, derived):
        v = ratios.get(ratio_key)
        return v if isinstance(v, (int, float)) else derived

    metrics = {
        # growth
        "revenue_growth_5y": growth["revenue_growth_5y"],
        "net_income_growth_5y": growth["net_income_growth_5y"],
        "eps_growth": ratios.get("eps_growth_5y"),
        "sales_growth": ratios.get("sales_growth_5y", growth["revenue_growth_5y"]),
        # profitability
        "roe": pick("roe", _safe_div(ni, eq)),
        "roa": pick("roa", _safe_div(ni, ta)),
        "gross_margin": pick("gross_margin", _safe_div(gp, rev)),
        "operating_margin": pick("operating_margin", _safe_div(oi, rev)),
        "net_margin": pick("net_margin", _safe_div(ni, rev)),
        # financial strength
        "debt_to_equity": pick("debt_to_equity", _safe_div(debt, eq)),
        "current_ratio": pick("current_ratio", _safe_div(ca, cl)),
        "interest_coverage": pick("interest_coverage", _safe_div(oi, abs(ie)) if ie else None),
        "fcf_margin": _safe_div(fcf, rev),
        # valuation
        "pe_ratio": ratios.get("pe_ratio"),
        "price_to_book": ratios.get("price_to_book"),
        "peg": ratios.get("peg"),
    }

    # TTM-ish free cash flow value kept for the report
    price = (tech_snapshot or {}).get("close") or overview.get("current_price")
    shares = overview.get("shares_outstanding")
    mktcap = overview.get("market_cap") or (
        price * shares if (price and shares) else None)
    derived = {
        "free_cash_flow": fcf,
        "market_cap": mktcap,
        "current_price": price,
    }

    # ---- extended metrics (all from data already on disk) ----
    isq = fundamentals.get("income_statement_quarterly", {})
    cfq = fundamentals.get("cashflow_quarterly", {})
    inv = _latest(bsa.get("inventory", {}))
    cash = _latest(bsa.get("cash_and_equivalents", {}))
    ebitda = _latest(isa.get("ebitda", {}))
    tax = _latest(isa.get("income_tax", {}))
    ebt = _latest(isa.get("ebt", {}))

    eff_tax = _safe_div(tax, ebt)
    if eff_tax is None or not (0 <= eff_tax <= 0.6):
        eff_tax = 0.29  # PK corporate default when unusual items distort the ratio
    nopat = oi * (1 - eff_tax) if oi is not None else None
    invested_capital = (debt + eq) if (debt is not None and eq is not None) else None

    def _q_sorted(m):
        items = [(k, v) for k, v in (m or {}).items() if v is not None]
        return sorted(items, key=lambda t: str(t[0]))

    def _ttm(m):
        s = _q_sorted(m)
        return sum(v for _, v in s[-4:]) if len(s) >= 4 else None

    def _qoq(m):
        s = _q_sorted(m)
        if len(s) >= 2 and s[-2][1]:
            return (s[-1][1] - s[-2][1]) / abs(s[-2][1])
        return None

    def _yoy_q(m):
        s = _q_sorted(m)
        if len(s) >= 5 and s[-5][1]:
            return (s[-1][1] - s[-5][1]) / abs(s[-5][1])
        return None

    rev_ttm = _ttm(isq.get("revenue", {})) or rev
    ni_ttm = _ttm(isq.get("net_income", {})) or ni
    ocf_ttm = _ttm(cfq.get("cash_from_operations", {})) or ocf

    # free cash flow series for growth
    ocf_map = cfa.get("cash_from_operations", {})
    capex_map = cfa.get("capex", {})
    fcf_map = {}
    for k in ocf_map:
        if ocf_map.get(k) is not None and capex_map.get(k) is not None:
            fcf_map[k] = ocf_map[k] - abs(capex_map[k])

    # dividends
    div = fundamentals.get("dividends", {})
    div_hist = div.get("history", []) or []
    div_by_year = {}
    for d in div_hist:
        y = _year_of(d.get("ex_date", ""))
        amt = d.get("amount")
        if y and amt is not None:
            div_by_year[y] = div_by_year.get(y, 0) + amt

    extended = {
        "effective_tax_rate": eff_tax,
        "roic": _safe_div(nopat, invested_capital),
        "quick_ratio": _safe_div((ca - inv) if (ca is not None and inv is not None) else None, cl),
        "ps_ratio": _safe_div(mktcap, rev_ttm),
        "ev_ebitda": _safe_div((mktcap + debt - cash)
                               if (mktcap is not None and debt is not None and cash is not None) else None,
                               ebitda),
        "peg": _safe_div(metrics.get("pe_ratio"),
                         (metrics.get("eps_growth") or 0) * 100 or None),
        "revenue_cagr_3y": _cagr(isa.get("revenue", {}), 3),
        "net_income_cagr_3y": _cagr(isa.get("net_income", {}), 3),
        "eps_cagr_3y": _cagr(isa.get("eps", {}), 3),
        "revenue_qoq": _qoq(isq.get("revenue", {})),
        "revenue_yoy": _yoy_q(isq.get("revenue", {})),
        "eps_qoq": _qoq(isq.get("eps", {})),
        "eps_yoy": _yoy_q(isq.get("eps", {})),
        "ocf_cagr_5y": _cagr(ocf_map, 5),
        "fcf_cagr_5y": _cagr(fcf_map, 5),
        "cash_conversion": _safe_div(ocf, ni),  # latest annual OCF / net income (TTM distorted by M&A quarters)
        "ttm_revenue": rev_ttm,
        "ttm_net_income": ni_ttm,
        "dividend_last_year": div.get("last_dividend_year"),
        "dividend_latest_annual": (max(div_by_year.items())[1] if div_by_year else None),
    }
    # fill PEG/PS back into the scored metrics if not already provided
    if metrics.get("peg") is None:
        metrics["peg"] = extended["peg"]

    company_analysis = {
        "symbol": p.symbol,
        "growth": growth,
        "latest": latest,
        "metrics": metrics,
        "extended": extended,
        "derived": derived,
    }

    with open(p.company_analysis, "w") as f:
        json.dump(company_analysis, f, indent=2)

    return company_analysis
