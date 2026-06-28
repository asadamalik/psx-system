"""fetch_industry_pe.py — recover the ONE Investing-only field (industry_pe, + industry P/B)
for onboarded stocks. Investing IS reachable via headless Playwright (the Chrome-MCP block was
tool-specific). Per stock: resolve the Investing slug via the search API (filter to Karachi
exchange), load <slug>-ratios, extract the company-vs-industry ratios table (renders as
label-column + "company\tindustry" value-lines), verify the company matches, then patch
stocks/<SYM>/fundamentals/ratio.json with industry_pe. Re-export is done by the caller.

Usage: python fetch_industry_pe.py <SYM...>
"""
import sys, os, json, re, difflib
from playwright.sync_api import sync_playwright

ENGINE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(ENGINE), "data")   # monorepo <root>/data
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

SEARCH_JS = """async (q)=>{
  try{ const r=await fetch('https://api.investing.com/api/search/v2/search?q='+encodeURIComponent(q),
       {headers:{'accept':'application/json','domain-id':'www'}});
    const j=await r.json(); return (j.quotes||[]).map(x=>({name:(x.name||x.description||x.shortName||''),url:x.url,exch:(x.exchange||x.exchangeName||'')}));
  }catch(e){return [];}
}"""

RATIOS_JS = r"""()=>{
  const out={};
  // scan every table row across the page; the data rows have a label-column and a
  // "company\tindustry" value-column (newline-separated, one line per ratio).
  document.querySelectorAll('table tr').forEach(tr=>{
    const c=[...tr.children].map(td=>td.innerText.trim());
    if(c.length>=2 && /P\/E Ratio|Price to Book|Price to Sales/i.test(c[0]) && /\t/.test(c[1])){
      const labels=c[0].split('\n').map(s=>s.trim()).filter(Boolean);
      const vals=c[1].split('\n').map(s=>s.trim()).filter(Boolean);
      labels.forEach((lbl,i)=>{ if(vals[i]){const pair=vals[i].split('\t').map(x=>parseFloat(x.replace(/,/g,'')));
        out[lbl]={company:pair[0]??null, industry:pair[1]??null};} });
    }
  });
  return Object.keys(out).length?out:{err:'no ratios'};
}"""

def clean_queries(name, sym):
    n = re.sub(r"\b(limited|ltd|company|co|corporation|corp|the)\b\.?", "", name or "", flags=re.I)
    n = n.replace("&", "and"); n = re.sub(r"\s+", " ", n).strip()
    variants = [n]
    parts = n.split()
    if len(parts) > 2:
        variants.append(" ".join(parts[:2]))
    variants.append(name)
    return [v for v in dict.fromkeys(variants) if v]

def resolve_slug(page, name, sym):
    for q in clean_queries(name, sym) + [sym]:
        if not q:
            continue
        results = page.evaluate(SEARCH_JS, q)
        kar = [r for r in results if (r.get("exch") or "").lower() == "karachi" and r.get("url")]
        if kar:
            # best name match among Karachi results
            best = max(kar, key=lambda r: difflib.SequenceMatcher(None, (r.get("name") or "").lower(),
                                                                  (name or "").lower()).ratio())
            return best["url"].rsplit("/", 1)[-1], best.get("name")
    return None, None

def fetch(syms):
    companies = json.load(open(os.path.join(DATA, "companies.json")))
    results = {}
    with sync_playwright() as p:
        # ---- Phase A: resolve ALL slugs via search (this taints the session with Cloudflare,
        # so it runs in its own throwaway browser) ----
        b = p.chromium.launch(headless=True)
        page = b.new_context(user_agent=UA, locale="en-US").new_page()
        page.goto("https://www.investing.com/", wait_until="domcontentloaded", timeout=35000)
        page.wait_for_timeout(1500)
        slugmap = {}
        for sym in syms:
            name = (companies.get(sym) or {}).get("name", "")
            try:
                slug, inv_name = resolve_slug(page, name, sym)
            except Exception:
                slug, inv_name = None, None
            slugmap[sym] = (slug, inv_name)
            if not slug:
                results[sym] = "NO_SLUG"; print(f"  {sym:8} NO_SLUG ({name})", flush=True)
        b.close()
        # ---- Phase B: ratios extraction. Investing Cloudflare-challenges sequential automated
        # navigations, so use a FRESH browser per stock (a single first-load always passes). ----
        for sym in syms:
            slug, inv_name = slugmap[sym]
            if not slug:
                continue
            name = (companies.get(sym) or {}).get("name", "")
            try:
                b = p.chromium.launch(headless=True)
                page = b.new_context(user_agent=UA, locale="en-US").new_page()
                page.goto(f"https://www.investing.com/equities/{slug}-ratios",
                          wait_until="domcontentloaded", timeout=35000)
                page.wait_for_timeout(6000)
                ratios = page.evaluate(RATIOS_JS)
                if not isinstance(ratios, dict) or "err" in ratios:
                    results[sym] = f"NO_RATIOS (slug {slug})"; print(f"  {sym:8} NO_RATIOS slug={slug}", flush=True); continue
                pe = next((v for k, v in ratios.items() if k.startswith("P/E Ratio")), {})
                pb = next((v for k, v in ratios.items() if k.startswith("Price to Book")), {})
                ind_pe = pe.get("industry"); ind_pb = pb.get("industry")
                match = difflib.SequenceMatcher(None, (inv_name or "").lower(), (name or "").lower()).ratio()
                sane = isinstance(ind_pe, (int, float)) and 2 <= ind_pe <= 80   # guard vs garbage
                rp = os.path.join(ENGINE, "stocks", sym, "fundamentals", "ratio.json")
                patched = False
                if os.path.exists(rp) and sane and match >= 0.45:
                    r = json.load(open(rp)); r["industry_pe"] = ind_pe
                    if isinstance(ind_pb, (int, float)) and ind_pb > 0:
                        r["industry_pb"] = ind_pb
                    json.dump(r, open(rp, "w"), indent=2); patched = True
                results[sym] = f"{'OK' if patched else 'SKIP'} slug={slug} ind_pe={ind_pe} match={match:.2f}"
                print(f"  {sym:8} {results[sym]}", flush=True)
            except Exception as e:
                results[sym] = "ERR " + str(e)[:60]; print(f"  {sym:8} ERR {str(e)[:60]}", flush=True)
            finally:
                try: b.close()
                except Exception: pass
    ok = sum(1 for v in results.values() if v.startswith("OK"))
    print(f"\nindustry_pe patched: {ok}/{len(syms)}")
    return results

if __name__ == "__main__":
    fetch(sys.argv[1:])
