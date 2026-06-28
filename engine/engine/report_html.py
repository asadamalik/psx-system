"""
report_html.py
--------------
Renders a styled, color-coded HTML report. Every section carries a SOURCE
badge so you can see at a glance where its numbers came from — without
repeating the source name on every value:

    Investing.com (consolidated)  -> blue
    PSX DPS (unconsolidated)      -> green
    Computed by the engine        -> grey

The "Earnings Basis" panel puts the two sources side by side (blue vs green)
and flags a material divergence.
"""

from __future__ import annotations
import json
from datetime import datetime

from .layout import StockPaths
from . import config as C

BLUE = "#2563eb"    # Investing.com
GREEN = "#059669"   # PSX DPS
GREY = "#6b7280"    # computed

SRC = {
    "investing": ("Investing.com", BLUE),
    "dps": ("PSX DPS", GREEN),
    "computed": ("Computed", GREY),
}


def _pct(x, nd=1):
    return "&mdash;" if x is None else f"{x*100:.{nd}f}%"


def _num(x, nd=2):
    return "&mdash;" if x is None else f"{x:,.{nd}f}"


def _money(x):
    return "&mdash;" if x is None else f"{x:,.0f}"


def _pill(kind):
    label, color = SRC[kind]
    return (f'<span class="pill" style="background:{color}1a;color:{color};'
            f'border:1px solid {color}55">{label}</span>')


def _card(title, kind, body):
    _, color = SRC[kind]
    return (f'<section class="card" style="border-left:4px solid {color}">'
            f'<div class="card-h"><h2>{title}</h2>{_pill(kind)}</div>{body}</section>')


def _pending(path_hint, note=""):
    return (f"<p class='muted'>&#9203; Data pending — add to "
            f"<code>{path_hint}</code>. {note}</p>")


def _rows(pairs):
    out = []
    for k, v in pairs:
        out.append(f"<tr><td class='k'>{k}</td><td class='v'>{v}</td></tr>")
    return "<table class='kv'>" + "".join(out) + "</table>"


def build(symbol, fundamentals, company_analysis, tech_snapshot, technical, scores, div, rs=None, insider=None):
    p = StockPaths(symbol).ensure()
    ov = fundamentals.get("overview", {})
    name = ov.get("company_name") or symbol
    cur = ov.get("currency") or "PKR"
    m = company_analysis["metrics"]
    g = company_analysis["growth"]
    latest = company_analysis["latest"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    rating_color = (GREEN if (scores["overall_score"] or 0) >= 65
                    else "#d97706" if (scores["overall_score"] or 0) >= 50 else "#dc2626")

    # ---- verdict ----
    verdict = _rows([
        ("Overall score", f"<b style='font-size:1.3em'>{_num(scores['overall_score'],1)}</b> / 100"),
        ("Rating", f"<b style='color:{rating_color}'>{scores['rating']}</b>"),
        ("Risk", scores["risk"]),
        ("Fundamental", f"{_num(scores['fundamental_score'],1)} <span class='w'>(70%)</span>"),
        ("Technical", f"{_num(scores['technical_score'],1)} <span class='w'>(30%)</span>"
                      + (f" &middot; {technical['trend']} / {technical['momentum']}" if technical else "")),
    ])

    # ---- fundamentals (Investing) ----
    pillars = "".join(
        f"<tr><td class='k'>{k.replace('_',' ').title()}</td>"
        f"<td class='v'>{_num(scores['fundamental_detail']['pillars'].get(k),0)}</td>"
        f"<td class='w'>{int(w*100)}%</td></tr>"
        for k, w in C.FUNDAMENTAL_PILLARS.items())
    fund_metrics = _rows([
        ("Revenue growth (5Y)", _pct(g.get("revenue_growth_5y"))),
        ("Net income growth (5Y)", _pct(g.get("net_income_growth_5y"))),
        ("ROE", _pct(m.get("roe"))), ("ROA", _pct(m.get("roa"))),
        ("Gross / Operating / Net margin",
         f"{_pct(m.get('gross_margin'))} / {_pct(m.get('operating_margin'))} / {_pct(m.get('net_margin'))}"),
        ("Debt / Equity", f"{_num(m.get('debt_to_equity'))}&times;"),
        ("Current ratio", f"{_num(m.get('current_ratio'))}&times;"),
        ("Interest coverage", f"{_num(m.get('interest_coverage'))}&times;"),
        ("P/E (consolidated)", f"{_num(m.get('pe_ratio'))}&times;"),
        ("Forward P/E", "<span class='w'>pending — brokerage estimate (Pro-locked)</span>"),
        ("Price / Book", f"{_num(m.get('price_to_book'))}&times;"),
    ])
    ext = company_analysis.get("extended", {})
    ext_metrics = _rows([
        ("ROIC", _pct(ext.get("roic"))),
        ("Quick ratio", f"{_num(ext.get('quick_ratio'))}&times;"),
        ("P/S", f"{_num(ext.get('ps_ratio'))}&times;"),
        ("PEG", _num(ext.get("peg"))),
        ("EV / EBITDA", f"{_num(ext.get('ev_ebitda'))}&times;"),
        ("Cash conversion (OCF/NI)", f"{_num(ext.get('cash_conversion'))}&times;"),
        ("Revenue CAGR (3Y / 5Y)", f"{_pct(ext.get('revenue_cagr_3y'))} / {_pct(g.get('revenue_growth_5y'))}"),
        ("EPS CAGR (3Y)", _pct(ext.get("eps_cagr_3y"))),
        ("OCF / FCF CAGR (5Y)", f"{_pct(ext.get('ocf_cagr_5y'))} / {_pct(ext.get('fcf_cagr_5y'))}"),
        ("Revenue QoQ / YoY", f"{_pct(ext.get('revenue_qoq'))} / {_pct(ext.get('revenue_yoy'))}"),
        ("EPS QoQ / YoY", f"{_pct(ext.get('eps_qoq'))} / {_pct(ext.get('eps_yoy'))}"),
    ])
    fund_body = (f"<h3>Pillars</h3><table class='kv'><tr><th>Pillar</th><th>Score</th><th>Weight</th></tr>{pillars}</table>"
                 f"<h3>Key metrics</h3>{fund_metrics}"
                 f"<h3>Extended metrics</h3>{ext_metrics}")

    # ---- earnings basis divergence (both sources) ----
    divergence_card = ""
    if div:
        c, u = div["consolidated"], div["unconsolidated"]
        flag_banner = ""
        if div["flagged"]:
            flag_banner = (f"<div class='flag'>&#9888; Divergence "
                           f"{_pct(div['eps_divergence'],0)} (&gt; {int(div['threshold']*100)}% threshold)"
                           f"<br><span>{div['interpretation']}</span></div>")
        body = (
            f"<p class='muted'>Same company, two accounting bases for FY{div['year']}. "
            f"Scoring uses the <span style='color:{BLUE}'>consolidated</span> basis (full statements available).</p>"
            "<table class='cmp'>"
            "<tr><th></th>"
            f"<th style='color:{BLUE}'>Consolidated<br><span class='src'>Investing.com</span></th>"
            f"<th style='color:{GREEN}'>Unconsolidated<br><span class='src'>PSX DPS</span></th>"
            "<th>Divergence</th></tr>"
            f"<tr><td class='k'>EPS</td>"
            f"<td style='color:{BLUE}'>{_num(c['eps'])}</td>"
            f"<td style='color:{GREEN}'>{_num(u['eps'])}</td>"
            f"<td>{_pct(div['eps_divergence'],0)}</td></tr>"
            f"<tr><td class='k'>Profit after tax ({cur} M)</td>"
            f"<td style='color:{BLUE}'>{_money(c['pat'])}</td>"
            f"<td style='color:{GREEN}'>{_money(u['pat'])}</td>"
            f"<td>{_pct(div['pat_divergence'],0)}</td></tr>"
            f"<tr><td class='k'>P/E (TTM)</td>"
            f"<td style='color:{BLUE}'>{_num(m.get('pe_ratio'))}&times;</td>"
            f"<td style='color:{GREEN}'>{_num(div.get('dps_pe_ttm'))}&times;</td>"
            f"<td>&mdash;</td></tr>"
            "</table>" + flag_banner)
        # special dual-source card (blue+green split border)
        divergence_card = (f'<section class="card" style="border-left:4px solid {BLUE};'
                           f'border-right:4px solid {GREEN}">'
                           f'<div class="card-h"><h2>Earnings Basis &mdash; Consolidated vs Unconsolidated</h2>'
                           f'{_pill("investing")}{_pill("dps")}</div>{body}</section>')

    # ---- technical (Investing export today; DPS going forward) ----
    tech_card = ""
    if tech_snapshot and technical:
        sr = tech_snapshot.get("support_resistance") or {}
        tb = _rows([
            ("As of", tech_snapshot.get("as_of")),
            ("Close", _num(tech_snapshot.get("close"))),
            ("Weekly / Monthly trend",
             f"{tech_snapshot.get('weekly_trend','—')} / {tech_snapshot.get('monthly_trend','—')}"),
            ("SMA 20 / 50 / 200",
             f"{_num(tech_snapshot.get('sma_20'))} / {_num(tech_snapshot.get('sma_50'))} / {_num(tech_snapshot.get('sma_200'))}"),
            ("EMA 20 / 50 / 100 / 200",
             f"{_num(tech_snapshot.get('ema_20'))} / {_num(tech_snapshot.get('ema_50'))} / {_num(tech_snapshot.get('ema_100'))} / {_num(tech_snapshot.get('ema_200'))}"),
            ("RSI (14)", _num(tech_snapshot.get("rsi_14"))),
            ("MACD / signal", f"{_num(tech_snapshot.get('macd'))} / {_num(tech_snapshot.get('macd_signal'))}"),
            ("ADX / DI+ / DI-",
             f"{_num(tech_snapshot.get('adx_14'))} / {_num(tech_snapshot.get('plus_di'))} / {_num(tech_snapshot.get('minus_di'))}"),
            ("ATR (14)", _num(tech_snapshot.get("atr_14"))),
            ("Support / Resistance",
             f"{_num(sr.get('nearest_support'))} / {_num(sr.get('nearest_resistance'))}"),
            ("52-wk high / low", f"{_num(tech_snapshot.get('week52_high'))} / {_num(tech_snapshot.get('week52_low'))}"),
        ])
        rdiv = (technical or {}).get("rsi_divergence") or {}
        div_html = ""
        if rdiv.get("type"):
            dcol = "#dc2626" if rdiv["type"] == "bearish" else GREEN
            div_html = (f"<div class='flag' style='background:{dcol}14;border-color:{dcol};color:{dcol}'>"
                        f"&#9888; {rdiv['label']} ({rdiv['bars_ago']} bars ago)"
                        f"<br><span style='color:#374151'>{rdiv['note']}</span></div>")
        pats = tech_snapshot.get("patterns") or []
        pat_html = ""
        if pats:
            rows = ""
            for pp in pats[:3]:
                pcol = GREEN if pp["type"] == "bullish" else "#dc2626" if pp["type"] == "bearish" else GREY
                tgt = f"target {_num(pp['target'])}" if pp.get("target") else ""
                rows += (f"<tr><td class='k' style='width:34%'><b style='color:{pcol}'>{pp['name']}</b> "
                         f"<span class='w'>{pp['status']}</span></td>"
                         f"<td class='v' style='font-weight:400'>conf {int(pp['confidence']*100)}% &middot; {tgt}"
                         f"<br><span class='muted'>{pp['note']}</span></td></tr>")
            pat_html = ("<h3>Chart patterns (candidates)</h3>"
                        "<p class='muted'>Algorithmic candidates — confirm visually on the chart.</p>"
                        f"<table class='kv'>{rows}</table>")
        tech_card = _card("Technical Analysis", "investing",
                          "<p class='muted'>Price history sourced from Investing.com export; "
                          "daily updates will come from PSX DPS.</p>" + tb + div_html + pat_html)
    else:
        tech_card = _card("Technical Analysis", "investing",
                          "<p class='muted'>No price history loaded yet.</p>")

    latest_card = _card(f"Latest Reported ({cur} M)", "investing", _rows([
        ("Revenue", _money(latest.get("revenue"))),
        ("Net income (consolidated)", _money(latest.get("net_income"))),
        ("Total equity", _money(latest.get("equity"))),
        ("Total debt", _money(latest.get("total_debt"))),
        ("Free cash flow", _money(company_analysis["derived"].get("free_cash_flow"))),
    ]))

    # ---- profile (DPS) ----
    prof = fundamentals.get("profile", {})
    profile_card = ""
    if prof:
        kp = prof.get("key_people", {})
        people = ", ".join(f"{v} ({k})" for k, v in kp.items()) if kp else "—"
        profile_card = _card("Company Profile", "dps",
            f"<p>{prof.get('description','—')}</p>" + _rows([
                ("Sector / Industry", f"{ov.get('sector','—')} / {ov.get('industry','—')}"),
                ("Holding company", prof.get("holding_company", "—")),
                ("Key people", people),
                ("Auditor", prof.get("auditor", "—")),
                ("Fiscal year end", prof.get("fiscal_year_end", "—")),
                ("Website", prof.get("website", "—")),
            ]))

    # ---- relative strength vs KSE100 ----
    rs_card = ""
    if rs and rs.get("windows"):
        rows = [("Rating", f"<b>{rs['rating']}</b>"),
                ("As of", f"{rs['as_of']} <span class='w'>(index feed latency)</span>")]
        for win, w in rs["windows"].items():
            op = w["outperformance"]
            color = GREEN if op >= 0 else "#dc2626"
            rows.append((f"{win} vs KSE100",
                         f"stock {_pct(w['stock_return'])} &middot; index {_pct(w['index_return'])} &middot; "
                         f"<b style='color:{color}'>{_pct(op)}</b>"))
        rs_card = _card("Relative Strength (vs KSE100)", "computed", _rows(rows))

    # ---- ownership (DPS) ----
    own = fundamentals.get("ownership", {})
    ownership_card = ""
    if own:
        spon = own.get("sponsors", {})
        spon_txt = ", ".join(f"{k}" for k in spon) if spon else "—"
        ownership_card = _card("Ownership", "dps", _rows([
            ("Free float", _pct(own.get("free_float"))),
            ("Free-float shares", _money(own.get("free_float_shares"))),
            ("Sponsor / parent", spon_txt),
        ]) + (f"<p class='muted'>{own.get('note','')}</p>" if own.get("note") else ""))

    # ---- insider transactions (sarmaaya) ----
    insider_card = ""
    if insider and insider.get("n_transactions"):
        scol = GREEN if (insider.get("net_ratio") or 0) > 0 else "#dc2626" if (insider.get("net_ratio") or 0) < 0 else GREY
        head = _rows([
            ("Sentiment", f"<b style='color:{scol}'>{insider['sentiment']}</b>"),
            ("Buys / Sells", f"{insider['buys']} / {insider['sells']}"),
            ("Net shares", _money(insider.get("net_shares"))),
        ])
        trows = "".join(
            f"<tr><td class='k' style='width:22%'>{t.get('date','')}</td>"
            f"<td class='v' style='font-weight:400'>{t.get('person','')} ({t.get('role','')}) "
            f"<b style='color:{GREEN if 'buy' in str(t.get('action','')).lower() else '#dc2626'}'>"
            f"{t.get('action','')}</b> {_money(t.get('shares'))} sh</td></tr>"
            for t in insider.get("transactions", []))
        insider_card = _card("Insider Transactions", "dps",
                             head + (f"<h3>Recent</h3><table class='kv'>{trows}</table>" if trows else ""))

    # ---- announcements (DPS) ----
    ann = fundamentals.get("announcements", {})
    announce_card = ""
    if ann:
        def _alist(items, n=4):
            return "".join(f"<tr><td class='k' style='width:22%'>{a.get('date','')}</td>"
                           f"<td class='v' style='font-weight:400'>{a.get('title','')}</td></tr>"
                           for a in (items or [])[:n])
        body = ("<h3>Financial results</h3><table class='kv'>" + _alist(ann.get("financial_results")) + "</table>"
                "<h3>Board meetings</h3><table class='kv'>" + _alist(ann.get("board_meetings")) + "</table>"
                "<h3>Other</h3><table class='kv'>" + _alist(ann.get("other")) + "</table>")
        announce_card = _card("Corporate Announcements", "dps", body)

    # ---- shareholding pattern (sarmaaya) ----
    sh = fundamentals.get("shareholding", {})
    cats = sh.get("categories") or {}
    if cats:
        body = _rows([(k, _pct(v)) for k, v in cats.items()])
    else:
        body = _pending("stocks/&lt;SYM&gt;/overview/shareholding.json",
                        "Full sponsor/institution/foreign breakdown from sarmaaya's Pattern of Shareholding.")
    shareholding_card = _card("Shareholding Pattern", "dps", body)

    # ---- smart money / FIPI ----
    fp = fundamentals.get("fipi", {})
    flows = fp.get("flows") or {}
    if flows:
        net = sum(v for v in flows.values() if isinstance(v, (int, float)))
        scol = GREEN if net > 0 else "#dc2626" if net < 0 else GREY
        rows = [("Net flow", f"<b style='color:{scol}'>{_num(net)}</b> "
                 f"<span class='w'>(+ = net buying, PKR mn)</span>")]
        rows += [(k, _num(v)) for k, v in flows.items()]
        body = _rows(rows)
    else:
        body = _pending("stocks/&lt;SYM&gt;/overview/fipi.json",
                        "Foreign/institutional net flows from NCCPL or sarmaaya FIPI/LIPI.")
    fipi_card = _card("Smart Money / FIPI", "computed", body)

    # ---- monthly sales ----
    ms = fundamentals.get("monthly_sales", {})
    months = ms.get("months") or []
    if months:
        rows = "".join(
            f"<tr><td class='k'>{m.get('month','')}</td>"
            f"<td class='v'>{_money(m.get('sales'))} {ms.get('unit','')} "
            f"<span class='w'>MoM {_pct(m.get('mom'))} · YoY {_pct(m.get('yoy'))}</span></td></tr>"
            for m in months[:6])
        body = f"<table class='kv'>{rows}</table>"
    else:
        body = _pending("stocks/&lt;SYM&gt;/overview/monthly_sales.json",
                        "Monthly dispatch/sales (APCMA for cement, PAMA for autos).")
    sales_card = _card("Monthly Sales", "dps", body)

    # ---- sector comparison (needs peers) ----
    sector_card = _card("Sector Comparison", "computed",
                        _pending("(add peer tickers)",
                                 "Activates once sector peers (e.g. LUCK, DGKC) are onboarded; "
                                 "compares P/E, growth, ROE, margins and ranks the sector."))

    # ---- qualitative risk (AI thesis layer) ----
    qrisk_card = _card("Qualitative Risk", "computed",
                       _pending("(AI Investment Thesis layer)",
                                "Regulatory, commodity (coal/energy), and FX risk narrative — "
                                "generated in the AI thesis build."))

    legend = (f"<div class='legend'>Sources: {_pill('investing')} consolidated full statements "
              f"&nbsp; {_pill('dps')} official PSX standalone &nbsp; {_pill('computed')} engine</div>")

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>{name} ({symbol}) — Analysis</title>
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
   max-width:860px;margin:24px auto;padding:0 18px;color:#111;background:#fff;line-height:1.45}}
 h1{{font-size:1.5em;margin:0 0 2px}} h2{{font-size:1.08em;margin:0}}
 h3{{font-size:.92em;color:#374151;margin:14px 0 6px;text-transform:uppercase;letter-spacing:.03em}}
 .sub{{color:#6b7280;font-size:.85em;margin:0 0 16px}}
 .legend{{font-size:.8em;color:#6b7280;margin:10px 0 18px}}
 .pill{{display:inline-block;font-size:.7em;font-weight:600;padding:1px 8px;border-radius:999px;
   margin-left:6px;vertical-align:middle}}
 .card{{background:#fafafa;border:1px solid #eee;border-radius:10px;padding:14px 16px;margin:12px 0}}
 .card-h{{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}}
 table{{width:100%;border-collapse:collapse;font-size:.9em;margin-top:6px}}
 .kv td,.cmp td,.cmp th,table th{{padding:5px 8px;border-bottom:1px solid #eee;text-align:left}}
 .kv .k,.cmp .k{{color:#374151;width:48%}} .kv .v{{font-weight:600}}
 .cmp th{{font-size:.85em;color:#374151}} .cmp td{{font-weight:600}}
 .src{{font-size:.78em;font-weight:400;opacity:.8}}
 .w{{color:#9ca3af;font-size:.85em}} .muted{{color:#6b7280;font-size:.85em;margin:2px 0 4px}}
 .flag{{background:#fef3c7;border:1px solid #f59e0b;border-radius:8px;padding:10px 12px;
   margin-top:10px;font-size:.86em;color:#92400e}} .flag span{{color:#78350f}}
 .disclaimer{{color:#9ca3af;font-size:.78em;margin-top:18px;border-top:1px solid #eee;padding-top:10px}}
</style></head><body>
<h1>{name} <span style="color:#6b7280">({symbol})</span></h1>
<p class="sub">Generated {now} &middot; decision-support only, not financial advice</p>
{legend}
{_card("Verdict", "computed", verdict)}
{profile_card}
{_card("Fundamental Analysis", "investing", fund_body)}
{divergence_card}
{tech_card}
{rs_card}
{latest_card}
{ownership_card}
{shareholding_card}
{insider_card}
{fipi_card}
{sales_card}
{sector_card}
{qrisk_card}
{announce_card}
<p class="disclaimer">Scores are mechanical functions of the inputs and the thresholds in
engine/config.py. Consolidated (Investing.com) and unconsolidated (PSX DPS) figures
reflect different accounting bases; neither is "wrong". Verify against primary filings.</p>
</body></html>"""

    with open(p.report_html, "w") as f:
        f.write(html)
    return p.report_html
