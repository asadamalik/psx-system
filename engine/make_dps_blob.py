"""make_dps_blob.py — synthesize a stockanalysis-compatible blob from DPS data
(data/companies.json) for stocks that have NO stockanalysis / Investing financial-statement
page (illiquid small caps). The blob is written to the same .cache/sa/sa_<SYM>.json path the
real fetch_sa.py uses, so the existing assemble_sa -> run -> export pipeline consumes it
unchanged. Only the (unconsolidated) income line is available from DPS: revenue (=sales),
net_income (=PAT), eps. Balance sheet / cash flow have no source and stay empty (render "—").

companies.json units: sales/pat are in THOUSANDS (assemble_sa scales psx_official by 1/1000),
so we divide by 1000 to match the blob's millions convention; eps is per-share; mcap_mn is
already millions.

Usage: python make_dps_blob.py <SYM...>
"""
import sys, os, json

ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)
DATA = os.path.join(ROOT, "data")
SA_DIR = os.path.join(ROOT, ".cache", "sa")

# "Q3 2026" -> calendar-ish YYYY-MM period-end key (approx; quarter end month by Q number,
# assuming a Dec fiscal year — good enough for TTM/QoQ ordering on a partial record).
_QMON = {"Q1": "03", "Q2": "06", "Q3": "09", "Q4": "12"}


def _by_year(years, arr, scale=1.0):
    if not years or not arr:
        return {}
    out = {}
    for i, y in enumerate(years):
        if i < len(arr) and arr[i] is not None:
            out[str(y)] = round(arr[i] * scale, 4)
    return out


def _by_quarter(labels, arr, scale=1.0):
    if not labels or not arr:
        return {}
    out = {}
    for i, lbl in enumerate(labels):
        if i >= len(arr) or arr[i] is None:
            continue
        parts = str(lbl).split()
        if len(parts) == 2 and parts[0] in _QMON:
            key = f"{parts[1]}-{_QMON[parts[0]]}"
            out[key] = round(arr[i] * scale, 4)
    return out


def build(sym, companies):
    sym = sym.upper()
    c = companies.get(sym)
    if not c:
        return None, "NOT_IN_COMPANIES_JSON"
    years = [str(y) for y in (c.get("years") or [])]

    income = {}
    rev = _by_year(years, c.get("sales"), 1 / 1000)
    ni = _by_year(years, c.get("pat"), 1 / 1000)
    eps = _by_year(years, c.get("eps"))
    if rev:
        income["revenue"] = rev
    if ni:
        income["net_income"] = ni
    if eps:
        income["eps"] = eps

    # need >=2 yrs of at least one income series to be a usable annual record
    if max((len(rev), len(ni), len(eps)), default=0) < 2:
        return None, f"INSUFFICIENT_ANNUAL(rev={len(rev)} ni={len(ni)} eps={len(eps)})"

    qlabels = c.get("q_labels")
    qincome = {}
    qrev = _by_quarter(qlabels, c.get("q_sales"), 1 / 1000)
    qni = _by_quarter(qlabels, c.get("q_pat"), 1 / 1000)
    qeps = _by_quarter(qlabels, c.get("q_eps"))
    if qrev:
        qincome["revenue"] = qrev
    if qni:
        qincome["net_income"] = qni
    if qeps:
        qincome["eps"] = qeps

    eps_ttm = None
    qe = c.get("q_eps") or []
    if len(qe) >= 4 and all(x is not None for x in qe[:4]):
        eps_ttm = round(sum(qe[:4]), 4)
    elif eps:
        eps_ttm = list(eps.values())[0]

    blob = {
        "sym": sym,
        "source": "dps",  # marks a DPS-synthesized (unconsolidated, income-only) blob
        "annual": {"income": income, "balance": {}, "cashflow": {}},
        "quarterly": {"income": qincome, "balance": {}, "cashflow": {}},
        "stats": {
            "market_cap": c.get("mcap_mn"),
            "pe": c.get("pe"),
            "pb": None,
            "eps_ttm": eps_ttm,
            "price": None,
        },
        "div": [],
        "hl": {},
    }
    return blob, f"OK(annual_yrs={len(years)} q={len(qincome.get('eps', {}))})"


def main(syms):
    companies = json.load(open(os.path.join(DATA, "companies.json")))
    os.makedirs(SA_DIR, exist_ok=True)
    for s in syms:
        blob, status = build(s, companies)
        if blob is None:
            print(f"  {s:8} SKIP {status}")
            continue
        fp = os.path.join(SA_DIR, f"sa_{s.upper()}.json")
        json.dump(blob, open(fp, "w"), indent=2)
        print(f"  {s:8} {status} -> {fp}")


if __name__ == "__main__":
    main(sys.argv[1:])
