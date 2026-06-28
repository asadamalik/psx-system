"""
report.py
---------
Writes reports/<SYM>_report.md (human) and reports/<SYM>_report.json (machine)
from the analysis + technical + scoring outputs.
"""

from __future__ import annotations
import json
from datetime import datetime

from .layout import StockPaths


def _pct(x, nd=1):
    return "—" if x is None else f"{x*100:.{nd}f}%"


def _num(x, nd=2):
    return "—" if x is None else f"{x:,.{nd}f}"


def _money(x, nd=0):
    """Statement figures arrive already in millions (Investing.com convention),
    so we show them with thousands separators and no extra scaling suffix.
    The report caption states the unit."""
    if x is None:
        return "—"
    return f"{x:,.{nd}f}"


def build(symbol, fundamentals, company_analysis, tech_snapshot, technical, scores):
    p = StockPaths(symbol).ensure()
    ov = fundamentals.get("overview", {})
    name = ov.get("company_name") or symbol
    sector = ov.get("sector")
    m = company_analysis["metrics"]
    g = company_analysis["growth"]
    latest = company_analysis["latest"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    L = []
    w = L.append
    w(f"# {name} ({symbol}) — Analysis Report")
    sub = f"*Generated {now}*"
    if sector:
        sub += f" · Sector: {sector}"
    w(sub + "  \n*Decision-support only — not financial advice.*\n")

    # ---- verdict ----
    w("## Verdict\n")
    w("| | |")
    w("|---|---|")
    w(f"| **Overall score** | **{_num(scores['overall_score'],1)} / 100** |")
    w(f"| **Rating** | **{scores['rating']}** |")
    w(f"| Risk | {scores['risk']} |")
    w(f"| Fundamental score | {_num(scores['fundamental_score'],1)} (70% weight) |")
    w(f"| Technical score | {_num(scores['technical_score'],1)} (30% weight) |")
    if technical:
        w(f"| Trend / Momentum | {technical.get('trend','—')} / {technical.get('momentum','—')} |")
    w("")

    # ---- fundamental pillars ----
    fd = scores["fundamental_detail"]
    w("## Fundamental Analysis\n")
    w("### Pillar Scores\n")
    w("| Pillar | Score | Weight |")
    w("|---|---|---|")
    from . import config as C
    for pillar, weight in C.FUNDAMENTAL_PILLARS.items():
        ps = fd["pillars"].get(pillar)
        w(f"| {pillar.replace('_',' ').title()} | {_num(ps,0) if ps is not None else '—'} | {int(weight*100)}% |")
    w("")

    w("### Key Metrics\n")
    w("| Metric | Value |")
    w("|---|---|")
    w(f"| Revenue growth (5Y CAGR) | {_pct(g.get('revenue_growth_5y'))} |")
    w(f"| Net income growth (5Y CAGR) | {_pct(g.get('net_income_growth_5y'))} |")
    w(f"| Equity growth (5Y CAGR) | {_pct(g.get('equity_growth_5y'))} |")
    w(f"| ROE | {_pct(m.get('roe'))} |")
    w(f"| ROA | {_pct(m.get('roa'))} |")
    w(f"| Gross margin | {_pct(m.get('gross_margin'))} |")
    w(f"| Operating margin | {_pct(m.get('operating_margin'))} |")
    w(f"| Net margin | {_pct(m.get('net_margin'))} |")
    w(f"| Debt / Equity | {_num(m.get('debt_to_equity'))}× |")
    w(f"| Current ratio | {_num(m.get('current_ratio'))}× |")
    w(f"| Interest coverage | {_num(m.get('interest_coverage'))}× |")
    w(f"| FCF margin | {_pct(m.get('fcf_margin'))} |")
    w(f"| P/E | {_num(m.get('pe_ratio'))}× |")
    w(f"| Price / Book | {_num(m.get('price_to_book'))}× |")
    w(f"| PEG | {_num(m.get('peg'))} |")
    w("")

    cur = ov.get("currency") or "reporting currency"
    w(f"### Latest Reported\n")
    w(f"*Figures in millions of {cur}.*\n")
    w("| Item | Value |")
    w("|---|---|")
    w(f"| Revenue | {_money(latest.get('revenue'))} |")
    w(f"| Net income | {_money(latest.get('net_income'))} |")
    w(f"| Total equity | {_money(latest.get('equity'))} |")
    w(f"| Total debt | {_money(latest.get('total_debt'))} |")
    w(f"| Operating cash flow | {_money(latest.get('operating_cash_flow'))} |")
    w(f"| Free cash flow | {_money(company_analysis['derived'].get('free_cash_flow'))} |")
    w("")

    # ---- technical ----
    if tech_snapshot and technical:
        w("## Technical Analysis\n")
        w(f"As of **{tech_snapshot.get('as_of','—')}** ({tech_snapshot.get('bars','—')} bars). "
          f"Trend **{technical.get('trend')}**, momentum **{technical.get('momentum')}**, "
          f"technical score **{_num(technical.get('technical_score'),1)}/100**.\n")
        w("| Indicator | Value |")
        w("|---|---|")
        w(f"| Close | {_num(tech_snapshot.get('close'))} |")
        w(f"| SMA 20 / 50 / 200 | {_num(tech_snapshot.get('sma_20'))} / {_num(tech_snapshot.get('sma_50'))} / {_num(tech_snapshot.get('sma_200'))} |")
        w(f"| EMA 20 / 50 | {_num(tech_snapshot.get('ema_20'))} / {_num(tech_snapshot.get('ema_50'))} |")
        w(f"| RSI (14) | {_num(tech_snapshot.get('rsi_14'))} |")
        w(f"| MACD / signal | {_num(tech_snapshot.get('macd'))} / {_num(tech_snapshot.get('macd_signal'))} |")
        w(f"| ADX (14) | {_num(tech_snapshot.get('adx_14'))} |")
        w(f"| DI+ / DI− | {_num(tech_snapshot.get('plus_di'))} / {_num(tech_snapshot.get('minus_di'))} |")
        w(f"| ATR (14) | {_num(tech_snapshot.get('atr_14'))} |")
        w(f"| 52-week high / low | {_num(tech_snapshot.get('week52_high'))} / {_num(tech_snapshot.get('week52_low'))} |")
        w("")
        w("Signals: " + "; ".join(technical.get("notes", [])) + "\n")

    w("## Notes\n")
    w("> Scores are mechanical functions of the extracted data and the thresholds in "
      "`engine/config.py`. They ignore qualitative factors (management, sector cycle, "
      "news, guidance) and are not a recommendation to trade. Verify against primary filings.\n")

    md = "\n".join(L)
    with open(p.report_md, "w") as f:
        f.write(md)

    machine = {
        "symbol": symbol,
        "generated": now,
        "scores": scores,
        "technical": technical,
        "technical_snapshot": tech_snapshot,
        "growth": g,
        "metrics": m,
        "latest": latest,
    }
    with open(p.report_json, "w") as f:
        json.dump(machine, f, indent=2)

    return p.report_md
