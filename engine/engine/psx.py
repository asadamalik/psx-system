"""
psx.py
------
Loads the optional PSX DPS official (unconsolidated) dataset and computes the
divergence vs the Investing.com (consolidated) figures the model scores on.

The divergence is a *signal*, not a verdict: a large or one-sided gap between
unconsolidated (standalone, what PSX/dividends use) and consolidated (group)
earnings usually flags a non-recurring item or a meaningful subsidiary/associate
contribution. We surface it; we don't silently mix the two bases.
"""

from __future__ import annotations
import json
import re

from .layout import StockPaths

FLAG_THRESHOLD = 0.15  # |divergence| above this gets flagged in the report


def _year_of(label):
    m = re.search(r"(19|20)\d{2}", str(label))
    return int(m.group()) if m else None


def _latest(year_map: dict):
    best = None
    for k, v in (year_map or {}).items():
        y = _year_of(k)
        if y is not None and v is not None:
            if best is None or y > best[0]:
                best = (y, v)
    return best  # (year, value) or None


def load_dps(symbol: str) -> dict | None:
    p = StockPaths(symbol)
    path = p.overview / "psx_official.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _div(unc, con):
    if unc is None or con in (None, 0):
        return None
    return (unc - con) / abs(con)


def divergence(symbol: str, fundamentals: dict) -> dict | None:
    """Compare DPS unconsolidated vs Investing consolidated for the latest
    common year. Returns a dict the report can render, or None if no DPS data."""
    dps = load_dps(symbol)
    if not dps:
        return None

    isa = fundamentals.get("income_statement_annual", {})
    con_eps = _latest(isa.get("eps", {}))
    con_pat = _latest(isa.get("net_income", {}))

    unc_eps = _latest(dps.get("annual", {}).get("eps", {}))
    unc_pat = _latest(dps.get("annual", {}).get("profit_after_tax", {}))

    # align on the same year where possible
    def value_for(series, year):
        for k, v in (series or {}).items():
            if _year_of(k) == year:
                return v
        return None

    year = None
    if con_eps and unc_eps:
        year = min(con_eps[0], unc_eps[0])  # latest common-ish
        # prefer exact same latest year present in both
        common = [y for y in
                  {(_year_of(k)) for k in isa.get("eps", {})} &
                  {(_year_of(k)) for k in dps.get("annual", {}).get("eps", {})}
                  if y]
        if common:
            year = max(common)

    c_eps = value_for(isa.get("eps", {}), year) if year else (con_eps[1] if con_eps else None)
    u_eps = value_for(dps.get("annual", {}).get("eps", {}), year) if year else (unc_eps[1] if unc_eps else None)
    c_pat = value_for(isa.get("net_income", {}), year) if year else (con_pat[1] if con_pat else None)
    u_pat = value_for(dps.get("annual", {}).get("profit_after_tax", {}), year) if year else (unc_pat[1] if unc_pat else None)

    eps_div = _div(u_eps, c_eps)
    pat_div = _div(u_pat, c_pat)
    worst = max([abs(x) for x in (eps_div, pat_div) if x is not None], default=None)
    flagged = worst is not None and worst >= FLAG_THRESHOLD

    # ---- per-year series (EPS + PAT across every common year) ----
    # The dashboard renders this as a multi-year table. EPS is only comparable when
    # both bases use the same share count, so years before `eps_comparable_from`
    # (e.g. pre-split standalone EPS) get a null EPS divergence. PAT is split-independent
    # and computed for every year.
    con_eps_map = isa.get("eps", {})
    con_pat_map = isa.get("net_income", {})
    unc_eps_map = dps.get("annual", {}).get("eps", {})
    unc_pat_map = dps.get("annual", {}).get("profit_after_tax", {})
    eps_comparable_from = dps.get("eps_comparable_from")

    def _by_year(series):
        out = {}
        for k, v in (series or {}).items():
            y = _year_of(k)
            if y is not None and v is not None:
                out[y] = v
        return out

    ce, cp = _by_year(con_eps_map), _by_year(con_pat_map)
    ue, up = _by_year(unc_eps_map), _by_year(unc_pat_map)
    yec = _by_year(dps.get("yearend_close", {}))  # FY-end close per year (market price)
    years = sorted(set(ce) & set(ue) | set(cp) & set(up))
    series = {"eps": {"con": {}, "unc": {}, "div": {}},
              "pat": {"con": {}, "unc": {}, "div": {}},
              "pe": {"con": {}}}  # derived FY-end P/E (close / consolidated EPS); split-invariant
    for y in years:
        sy = str(y)
        eps_ok = eps_comparable_from is None or y >= eps_comparable_from
        series["eps"]["con"][sy] = ce.get(y)
        series["eps"]["unc"][sy] = ue.get(y) if eps_ok else None
        series["eps"]["div"][sy] = _div(ue.get(y), ce.get(y)) if eps_ok else None
        series["pat"]["con"][sy] = cp.get(y)
        series["pat"]["unc"][sy] = up.get(y)
        series["pat"]["div"][sy] = _div(up.get(y), cp.get(y))
        series["pe"]["con"][sy] = (round(yec[y] / ce[y], 2)
                                   if yec.get(y) and ce.get(y) else None)

    interpretation = None
    if flagged and eps_div is not None:
        if eps_div > 0:
            interpretation = (
                f"Standalone (unconsolidated) EPS for {year} is "
                f"{eps_div*100:.0f}% ABOVE the consolidated figure — typically a "
                f"non-recurring parent-level gain or subsidiary dividends. Treat the "
                f"unconsolidated EPS and any P/E derived from it with caution; the "
                f"consolidated basis is more conservative.")
        else:
            interpretation = (
                f"Standalone (unconsolidated) EPS for {year} is "
                f"{abs(eps_div)*100:.0f}% BELOW the consolidated figure — "
                f"subsidiaries/associates are contributing earnings the parent-only "
                f"accounts don't show; the group is worth more than the standalone.")

    return {
        "year": year,
        "consolidated": {"eps": c_eps, "pat": c_pat, "source": "Investing.com"},
        "unconsolidated": {"eps": u_eps, "pat": u_pat, "source": "PSX DPS"},
        "eps_divergence": eps_div,
        "pat_divergence": pat_div,
        "flagged": flagged,
        "threshold": FLAG_THRESHOLD,
        "interpretation": interpretation,
        "dps_pe_ttm": dps.get("pe_ratio_ttm"),
        "free_float_pct": dps.get("free_float_pct"),
        "years": years,
        "series": series,
        "eps_comparable_from": eps_comparable_from,
    }
