"""assemble_sa.py — build all engine files for a PSX ticker from:
  - scratchpad/sa/sa_<SYM>.json  (stockanalysis blob: consolidated annual+quarterly, stats, div, hl)
  - dashboard companies.json     (DPS-side: name, sector, shares, free float, unconsolidated annual)
  - DPS EOD timeseries (curl)    (full-history close/open/vol -> historical.csv base + yearend_close)

Writes: overview.json, income/balance/cashflow_{annual,quarterly}.json, ratio.json, earnings.json,
dividends.json, psx_official.json, technical/historical.csv. industry_pe is left null (Investing-only;
the documented gap). Insider, run.py and export are done by the batch driver, not here.

Usage:  python assemble_sa.py <SYM>
"""
import sys, os, json, re, urllib.request, datetime

ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)                  # monorepo root (psx-system/)
DATA = os.path.join(ROOT, "data")
SA_DIR = os.path.join(ROOT, ".cache", "sa")
MON_ABBR = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
FY_MONTH = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
            "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12, "december": 12, "june": 6}

def title_sector(s):
    return " ".join(w.capitalize() if len(w) > 3 else w.upper() for w in (s or "").split())

def infer_fy_month(catalysts):
    for d, txt in (catalysts or []):
        m = re.search(r"year ended[^\d]*(\d{1,2})?\s*([A-Za-z]+)\s*\d{4}", txt, re.I)
        if m:
            mo = FY_MONTH.get(m.group(2).lower()[:3])
            if mo:
                return mo
    return 12  # default December

def dps_eod(sym):
    req = urllib.request.Request(f"https://dps.psx.com.pk/timeseries/eod/{sym}",
                                 headers={"User-Agent": "Mozilla/5.0"})
    data = json.load(urllib.request.urlopen(req, timeout=30))["data"]  # [ts, close, vol, open]
    data.sort(key=lambda r: r[0])
    return data

def assemble(sym):
    sym = sym.upper()
    blob = json.load(open(os.path.join(SA_DIR, f"sa_{sym}.json")))
    companies = json.load(open(os.path.join(DATA, "companies.json")))
    co = companies.get(sym, {})
    base = os.path.join(ENGINE, "stocks", sym)
    for sub in ("overview", "fundamentals", "technical", "analysis"):
        os.makedirs(os.path.join(base, sub), exist_ok=True)

    def w(path, obj):
        json.dump(obj, open(os.path.join(base, path), "w"), indent=2)

    # ---------- annual + quarterly statements (straight from blob) ----------
    a = blob.get("annual", {}); q = blob.get("quarterly", {})
    w("fundamentals/income_statement_annual.json", a.get("income", {}))
    w("fundamentals/balance_sheet_annual.json", a.get("balance", {}))
    w("fundamentals/cashflow_annual.json", a.get("cashflow", {}))
    w("fundamentals/income_statement_quarterly.json", q.get("income", {}))
    w("fundamentals/balance_sheet_quarterly.json", q.get("balance", {}))
    w("fundamentals/cashflow_quarterly.json", q.get("cashflow", {}))

    # ---------- DPS EOD -> historical.csv (base) + yearend_close ----------
    eod = dps_eod(sym)
    U = datetime.UTC
    # split detection: drop pre-split window where open/close ratio is far from 1
    cut = 0
    for i, r in enumerate(eod):
        if r[1] and not (0.7 < r[3] / r[1] < 1.43):
            cut = i + 1
    clean = eod[cut:] if cut < len(eod) - 30 else eod
    hl = {d: (h, l) for d, (h, l) in blob.get("hl", {}).items()}
    rows = []
    for i, r in enumerate(clean):
        ts, close, vol, op = r
        dt = datetime.datetime.fromtimestamp(ts, U)
        diso = dt.strftime("%Y-%m-%d")
        if diso in hl:
            hi, lo = hl[diso]
        else:
            hi, lo = max(op, close), min(op, close)
        prev = clean[i - 1][1] if i > 0 else None
        chg = "" if prev in (None, 0) else f"{(close - prev) / prev * 100:+.2f}%"
        rows.append((dt.strftime("%b %d, %Y"), close, op, hi, lo, int(vol), chg))
    newest_close = rows[-1][1] if rows else None
    rows.reverse()
    with open(os.path.join(base, "technical", "historical.csv"), "w") as f:
        f.write("date,close,open,high,low,volume,change_pct\n")
        for d, c, o, hi, lo, v, chg in rows:
            f.write(f'"{d}",{c},{o},{hi},{lo},{v},{chg}\n')

    fy_month = infer_fy_month(co.get("catalysts"))
    # year-end close at the company's FY-end month
    yearend = {}
    byyear = {}
    for r in eod:
        dt = datetime.datetime.fromtimestamp(r[0], U)
        if dt.month <= fy_month:
            byyear.setdefault(dt.year, []).append((dt, r[1]))
    for y, lst in byyear.items():
        yearend[str(y)] = round(max(lst, key=lambda x: x[0])[1], 2)

    # ---------- overview.json ----------
    st = blob.get("stats", {})
    shares_mn = round(co["shares"] / 1e6, 2) if co.get("shares") else None
    w("overview/overview.json", {
        "company_name": co.get("name") or sym,
        "sector": title_sector(co.get("sector")),
        "industry": title_sector(co.get("sector")),
        "market_cap": co.get("mcap_mn") or st.get("market_cap"),
        "shares_outstanding": shares_mn,
        "current_price": newest_close,
        "currency": "PKR",
    })

    # ---------- ratio.json (pe/pb from SA; roe/roa/gross_margin from raw; industry_pe null) ----------
    isa = a.get("income", {}); bsa = a.get("balance", {})
    def latest(m):
        ks = sorted((m or {}).keys())
        return m[ks[-1]] if ks else None
    ni, eq, ta = latest(isa.get("net_income", {})), latest(bsa.get("total_equity", {})), latest(bsa.get("total_assets", {}))
    rev, gp = latest(isa.get("revenue", {})), latest(isa.get("gross_profit", {}))
    div0 = lambda n, d: round(n / d, 4) if (n is not None and d) else None
    w("fundamentals/ratio.json", {
        "pe_ratio": st.get("pe"), "price_to_book": st.get("pb"),
        "roe": div0(ni, eq), "roa": div0(ni, ta),
        "gross_margin": div0(gp, rev) if gp is not None else None,
        "industry_pe": None,
    })

    # ---------- earnings.json ----------
    qeps = q.get("income", {}).get("eps", {})
    hist = []
    for k in sorted(qeps.keys(), reverse=True)[:8]:
        y, mo = k.split("-")
        hist.append({"period_end": f"{MON_ABBR[int(mo)]} {y}", "eps": qeps[k],
                     "eps_forecast": None, "eps_surprise_pct": None})
    ed = st.get("earnings_date")
    next_ed = (datetime.date.fromisoformat(ed).strftime("%b %-d, %Y") if ed else None)
    w("fundamentals/earnings.json", {
        "source": "stockanalysis.com (statistics + quarterly)", "as_of": "2026-06-28",
        "latest_eps": hist[0]["eps"] if hist else None,
        "eps_ttm": st.get("eps_ttm"), "next_earnings_date": next_ed, "history": hist,
    })

    # ---------- dividends.json (yield/payout as fractions) ----------
    frac = lambda v: round(v / 100, 4) if isinstance(v, (int, float)) else None
    w("fundamentals/dividends.json", {
        "source": "stockanalysis.com (statistics + dividend page)", "as_of": "2026-06-28",
        "yield": frac(st.get("div_yield")), "per_share_ttm": st.get("div_dps"),
        "payout_ratio": frac(st.get("div_payout")), "history": blob.get("div", []),
    })

    # ---------- psx_official.json (DPS unconsolidated from companies.json) ----------
    years = co.get("years", []) or []
    eps_a = co.get("eps") or []; sales_a = co.get("sales") or []; pat_a = co.get("pat") or []
    def by_year(arr, scale=1.0):
        return {years[i]: round(arr[i] * scale, 3) for i in range(min(len(years), len(arr))) if arr[i] is not None}
    ff = co.get("free_float_pct")
    w("overview/psx_official.json", {
        "source": "PSX DPS via dashboard companies.json", "basis": "unconsolidated",
        "as_of": "2026-06-28", "currency": "PKR", "units": "millions",
        "fiscal_year_end": MON_ABBR[fy_month] if fy_month != 6 else "June",
        "shares_outstanding": shares_mn,
        "free_float_pct": round(ff / 100, 4) if isinstance(ff, (int, float)) else None,
        "free_float_shares": round(co["shares"] / 1e6 * ff / 100, 2) if (co.get("shares") and ff) else None,
        "market_cap": co.get("mcap_mn"), "pe_ratio_ttm": co.get("pe"),
        "yearend_close": {y: yearend[y] for y in years if y in yearend},
        "note": "Bulk Shariah onboard. Unconsolidated annual from companies.json (DPS). "
                "industry_pe null (Investing-only). H/L overlaid from stockanalysis (~50 bars).",
        "annual": {"sales": by_year(sales_a, 1 / 1000), "profit_after_tax": by_year(pat_a, 1 / 1000),
                   "eps": by_year(eps_a)},
    })
    print(f"  {sym}: annual={len(a.get('income',{}).get('revenue',{}))}y "
          f"quarters={len(q.get('income',{}).get('revenue',{}))} bars={len(rows)} "
          f"fy={MON_ABBR[fy_month]} px={newest_close} ff={ff}")

if __name__ == "__main__":
    assemble(sys.argv[1])
