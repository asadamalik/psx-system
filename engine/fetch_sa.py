"""fetch_sa.py — headless stockanalysis.com scraper for a PSX ticker.

stockanalysis.com is the PRIMARY consolidated-data source (Investing is blocked; see
DECISIONS.md 2026-06-27). This loads the 8 relevant pages in ONE Playwright session and
writes a blob to <out>/sa_<SYM>.json with: consolidated annual + quarterly statements,
statistics (pe/pb/ps/eps_ttm/earnings_date/dividend summary), dividend history, and ~50
bars of real intraday H/L. Verified headless loads cleanly (HTTP 200, no bot block).

Usage:  python fetch_sa.py <SYM> [--out DIR]
"""
import sys, os, json, argparse
from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
BASE = "https://stockanalysis.com/quote/psx/{sym}/{path}"

# stockanalysis normalized row label -> engine field
FIELD_MAP = {
    "income": {"Revenue": "revenue", "Gross Profit": "gross_profit",
               "Operating Income": "operating_income", "Net Income": "net_income",
               "EPS (Diluted)": "eps", "Interest Expense": "interest_expense"},
    "balance": {"Total Current Assets": "current_assets", "Cash & Equivalents": "cash_and_equivalents",
                "Inventory": "inventory", "Total Assets": "total_assets",
                "Total Current Liabilities": "current_liabilities", "Total Liabilities": "total_liabilities",
                "Total Debt": "total_debt", "Shareholders' Equity": "total_equity"},
    "cashflow": {"Operating Cash Flow": "cash_from_operations", "Investing Cash Flow": "cash_from_investing",
                 "Financing Cash Flow": "cash_from_financing", "Capital Expenditures": "capex"},
}
ABS_FIELDS = {"interest_expense", "capex"}  # store positive

# JS run in the page to pull a statement table as {field: {periodKey: value}}
STMT_JS = r"""
([stmt, mode, mapObj, absList]) => {
  const t=document.querySelector('table'); if(!t) return {err:'no table'};
  const rows=[...t.querySelectorAll('tr')].map(tr=>[...tr.querySelectorAll('th,td')].map(c=>c.innerText.trim()));
  const hdr=rows[0]||[]; const per=rows.find(r=>r[0]==='Period Ending')||[];
  const MON={Jan:'01',Feb:'02',Mar:'03',Apr:'04',May:'05',Jun:'06',Jul:'07',Aug:'08',Sep:'09',Oct:'10',Nov:'11',Dec:'12'};
  const colKey={};
  for(let i=1;i<hdr.length;i++){
    if(mode==='quarterly'){const m=(per[i]||'').match(/([A-Za-z]{3})\s+\d{1,2},\s+(\d{4})/); if(m)colKey[i]=m[2]+'-'+MON[m[1]];}
    else {const h=hdr[i]; if(/TTM/i.test(h))continue; const m=h.match(/(\d{4})/); if(m)colKey[i]=m[1];}
  }
  const pf=s=>{const n=parseFloat(String(s).replace(/,/g,''));return isNaN(n)?null:n;};
  const out={};
  for(const lbl in mapObj){const key=mapObj[lbl];const r=rows.find(x=>x[0]===lbl);if(!r)continue;const mp={};
    for(let i=1;i<hdr.length;i++){if(!colKey[i])continue;let v=pf(r[i]);if(v==null)continue;if(absList.includes(key))v=Math.abs(v);mp[colKey[i]]=v;}
    if(Object.keys(mp).length)out[key]=mp;}
  return out;
}"""

STATS_JS = r"""
() => {
  const pairs={}; document.querySelectorAll('table tr').forEach(tr=>{const c=[...tr.querySelectorAll('td,th')].map(x=>x.innerText.trim());if(c.length>=2&&c[0])pairs[c[0]]=c[1];});
  const num=s=>{if(s==null)return null;s=String(s).replace(/,/g,'').trim();const m=s.match(/^(-?[\d.]+)\s*([BMK%])?/);if(!m)return null;let v=parseFloat(m[1]);if(m[2]==='B')v*=1000;else if(m[2]==='K')v/=1000;return v;};
  const MON={Jan:'01',Feb:'02',Mar:'03',Apr:'04',May:'05',Jun:'06',Jul:'07',Aug:'08',Sep:'09',Oct:'10',Nov:'11',Dec:'12'};
  const iso=s=>{const m=String(s||'').match(/([A-Za-z]{3})\s+(\d{1,2}),\s+(\d{4})/);return m?m[3]+'-'+MON[m[1]]+'-'+String(m[2]).padStart(2,'0'):null;};
  const g=k=>{for(const l in pairs){if(l.toLowerCase()===k.toLowerCase())return pairs[l];}return null;};
  return {market_cap:num(g('Market Cap')),pe:num(g('PE Ratio')),pb:num(g('PB Ratio')),ps:num(g('PS Ratio')),
    eps_ttm:num(g('Earnings Per Share (EPS)')),earnings_date:iso(g('Earnings Date')),
    div_yield:num(g('Dividend Yield')),div_dps:num(g('Dividend Per Share')),div_payout:num(g('Payout Ratio')),
    ex_date:iso(g('Ex-Dividend Date')),price:num(g('Stock Price'))};
}"""

DIV_JS = r"""
() => {
  let dt=null; document.querySelectorAll('table').forEach(t=>{const h=t.querySelector('tr')?.innerText||'';if(/Ex-Div|Ex-Date/i.test(h))dt=t;});
  const MON={Jan:'01',Feb:'02',Mar:'03',Apr:'04',May:'05',Jun:'06',Jul:'07',Aug:'08',Sep:'09',Oct:'10',Nov:'11',Dec:'12'};
  const iso=s=>{const m=String(s||'').match(/([A-Za-z]{3})\s+(\d{1,2}),\s+(\d{4})/);return m?m[3]+'-'+MON[m[1]]+'-'+String(m[2]).padStart(2,'0'):null;};
  const num=s=>{const n=parseFloat(String(s).replace(/,/g,''));return isNaN(n)?null:n;};
  const out=[]; if(dt){[...dt.querySelectorAll('tr')].slice(1).forEach(tr=>{const c=[...tr.querySelectorAll('td')].map(x=>x.innerText.trim());if(c[0]&&c[1])out.push({ex_date:iso(c[0]),amount:num(c[1]),type:null,yield:null});});}
  return out.slice(0,10);
}"""

HIST_JS = r"""
() => {
  const t=document.querySelector('table'); if(!t)return {};
  const MON={Jan:'01',Feb:'02',Mar:'03',Apr:'04',May:'05',Jun:'06',Jul:'07',Aug:'08',Sep:'09',Oct:'10',Nov:'11',Dec:'12'};
  const iso=s=>{const m=String(s||'').match(/([A-Za-z]{3})\s+(\d{1,2}),\s+(\d{4})/);return m?m[3]+'-'+MON[m[1]]+'-'+String(m[2]).padStart(2,'0'):null;};
  const num=s=>{const n=parseFloat(String(s).replace(/,/g,''));return isNaN(n)?null:n;};
  const hl={}; [...t.querySelectorAll('tr')].slice(1).forEach(tr=>{const c=[...tr.querySelectorAll('td,th')].map(x=>x.innerText.trim());const d=iso(c[0]);const h=num(c[2]),l=num(c[3]);if(d&&h!=null&&l!=null)hl[d]=[h,l];});
  return hl;
}"""

def fetch(sym, out_dir):
    sym = sym.upper()
    blob = {"sym": sym, "annual": {}, "quarterly": {}, "stats": {}, "div": [], "hl": {}}
    pages = {
        "income": "financials/", "balance": "financials/balance-sheet/",
        "cashflow": "financials/cash-flow-statement/",
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA)
        page = ctx.new_page()

        def load(path):
            url = BASE.format(sym=sym, path=path)
            r = page.goto(url, wait_until="domcontentloaded", timeout=40000)
            try:
                page.wait_for_selector("table tr", timeout=12000)
            except Exception:
                pass
            return r.status if r else 0

        # annual + quarterly statements
        for stmt, path in pages.items():
            for mode, q in (("annual", ""), ("quarterly", "?p=quarterly")):
                st = load(path + q)
                if st != 200:
                    continue
                sec = page.evaluate(STMT_JS, [stmt, mode, FIELD_MAP[stmt], list(ABS_FIELDS)])
                if isinstance(sec, dict) and "err" not in sec:
                    blob[mode][stmt] = sec
        # statistics
        if load("statistics/") == 200:
            blob["stats"] = page.evaluate(STATS_JS) or {}
        # dividends (404 for non-payers -> empty)
        if load("dividend/") == 200:
            blob["div"] = page.evaluate(DIV_JS) or []
        # history (real H/L)
        if load("history/") == 200:
            blob["hl"] = page.evaluate(HIST_JS) or {}
        browser.close()

    os.makedirs(out_dir, exist_ok=True)
    fp = os.path.join(out_dir, f"sa_{sym}.json")
    json.dump(blob, open(fp, "w"), indent=2)
    aq = len(next(iter(blob["annual"].get("income", {}).values()), {}))
    qq = len(next(iter(blob["quarterly"].get("income", {}).values()), {}))
    print(f"{sym}: annual_years={aq} quarters={qq} stats={'y' if blob['stats'] else 'n'} "
          f"div={len(blob['div'])} hl={len(blob['hl'])} -> {fp}")
    return blob

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("sym")
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache", "sa"))
    a = ap.parse_args()
    fetch(a.sym, a.out)
