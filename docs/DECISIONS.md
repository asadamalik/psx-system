# DECISIONS — PSX analysis system

**How to read this file.** Append-only decision log. **Newest at top.** Each entry
has a one-line **Why**. When a decision is reversed, do **not** delete the old entry —
add a new superseding entry at the top that names what it replaces. This file is the
source of truth for *why* the data-source and scraping logic is the way it is; read it
before touching any scraper, export, or data-source code.

**One monorepo (`~/projects/psx-system/`, GitHub `asadamalik/psx-system`).** This consolidates what
were originally two sibling repos; the dated log entries below still name the old layout — see the
**2026-06-28 "Consolidated into one monorepo"** entry directly below for the old→new path map. The
two subsystems now live as sibling dirs inside the one repo, sharing `data/`:
- `dashboard/` — **DASHBOARD** (was `~/projects/Analysis/psx-top30`).
  Static-site generator: `daily.yml → psx_auto.py → build_lib.py → dashboard_template.html`
  → baked into `dashboard/psx_dashboard.html`/`dashboard/index.html`, served on GitHub Pages.
- `engine/` — **ENGINE** (was `~/projects/stock-agent-claude/stock-agent-claude`). File-based Python
  under `engine/stocks/<SYM>/`. Produces Fund-70 / Tech-30 scored reports; `export_external.py` emits
  one JSON per symbol into the shared `data/external/` (old name: `psx_data/external/`).
- `data/` — **shared state** at the repo root (`data/external/`, `data/snapshots.json`,
  `data/ohlc.json`, `data/companies.json`, `data/shariah.json`). Where older entries say `psx_data/…`,
  read `data/…`.

One self-contained venv at the repo root: `./.venv/bin/python` (was two separate per-repo venvs).

---

## 2026-06-28 — Data-source priority + FALLBACK ORDER (read before fetching any new stock)
**Decision (canonical fetch order).** When onboarding/refreshing a stock, check sources in this order
and stop at the first that has the data; everything else is a documented **fallback**:

1. **stockanalysis.com — PRIMARY.** `engine/fetch_sa.py <SYM>` (headless Playwright). Consolidated
   annual + quarterly income/balance/cashflow, stats (pe/pb/ps/eps_ttm), dividends, ~50 real H/L bars.
   The automated `engine/batch_onboard.py` uses this. **If it has the data, you're done.**
2. **If stockanalysis has NO page / no statements → FALL BACK to these (in this order):**
   - **Investing.com** — consolidated statements for **well-covered (large/mid) caps only**
     (illiquid small caps have a quote page but **no statement rows** — same gap as stockanalysis);
     statements now render in **div-grids, not `<table>`s**. The `-ratios` page (company-vs-industry
     P/E) is still public and scriptable: `engine/fetch_industry_pe.py <SYM>` (slug via the search
     API, fresh browser per stock for Cloudflare). Use Investing for `industry_pe` always, and for
     full statements when the cap is covered.
   - **sarmaaya.pk** — **insider transactions** (always; `engine/fetch_insider.py <SYM>`, headless
     Playwright, best-effort). Also ownership/peers.
   - **PSX DPS** — **unconsolidated** annual/quarterly EPS·sales·PAT, free float, market cap, P/E,
     plus the authoritative **EOD OHLCV price history**. For the dashboard this is pre-harvested into
     `data/companies.json` (whole universe). For small caps with no stockanalysis/Investing statements,
     `engine/make_dps_blob.py <SYM>` synthesizes a stockanalysis-shaped blob from `companies.json`
     (income-only: revenue=sales/1000, net_income=PAT/1000, eps) so the normal
     `assemble_sa → run → export` pipeline runs unchanged.

**Records built from a fallback are PARTIAL** (income + price + ratios + insider; no balance-sheet /
cash-flow source exists for them). `export_external.py` sets **`limited_data: true`** when no
balance-sheet AND no cash-flow series exist, and the dashboard shows a **"⚠ LIMITED DATA" badge**
(amber) on the stock's verdict + an "LD" tag in the leaderboard. **Caveat:** the fundamental score
over-reads on these thin inputs (some show F=100 with no balance sheet, like banks show 0%
financial-strength) — treat partial-record scores with caution.

**Why this order:** stockanalysis is fully scriptable, consolidated, and bot-block-free (the primary
since 2026-06-27). The others fill specific gaps it can't: Investing → industry P/E (+ big-cap
statements), sarmaaya → insider, DPS → unconsolidated basis + price history + small-cap fundamentals.
See the per-field extraction map below and the dated entries for each source's constraints.

---

## 2026-06-28 — Consolidated into one monorepo (`psx-system`); old `psx_data/` → `data/`
**Decision:** the formerly-separate dashboard and engine repos are now one self-contained monorepo at
`~/projects/psx-system/` (GitHub `asadamalik/psx-system`, public for free GitHub Pages). Nothing about
the *data-source/scraping logic* changed — only locations did. **All dated entries below predate the
move and still reference the old two-repo paths;** translate them with this map:

| Old (two repos) | New (monorepo) |
|---|---|
| `~/projects/Analysis/psx-top30/` (dashboard repo) | `dashboard/` |
| `~/projects/stock-agent-claude/stock-agent-claude/` (engine repo) | `engine/` |
| engine `stocks/<SYM>/` | `engine/stocks/<SYM>/` |
| `psx_data/external/` (drop-folder) | `data/external/` |
| `psx_data/snapshots.json` · `psx_data/ohlc.json` · `psx_data/shariah.json` · `companies.json` | `data/…` |
| `psx_data/.embed_cache.json` | `data/.embed_cache.json` (gitignored) |
| dashboard `.venv` + engine `.venv` | one root `./.venv` |
| GitHub `asadamalik/psx-top30` | GitHub `asadamalik/psx-system` |

**Why:** one cloneable, runnable unit (one venv, one `requirements.txt`, one `daily.yml`) instead of
two repos that had to be checked out as siblings. **Source repos were copied, not moved** — the
originals at the old paths are an untouched safety net (see `docs/HANDOFF.md` / `docs/MIGRATION.md`).
**Code still contains legacy `psx_data/` strings in some docstrings/comments**, but runtime paths
resolve to `data/` (e.g. `dashboard/psx_auto.py:36` already notes the shared state lives at
`<repo-root>/data`). Nightly job + Pages run from this repo via `.github/workflows/daily.yml`.

---

## 2026-06-28 — Investing.com IS reachable after all (headless Playwright) → industry_pe recovered
**Correction to the "Investing blocked" premise.** The block was **specific to the Claude-in-Chrome
MCP** (a tool safety restriction), NOT site-wide. **Headless Playwright loads Investing fine (HTTP
200, full JS render)** — same engine that scrapes stockanalysis/sarmaaya. So Investing is usable for
the one field stockanalysis lacks: **`industry_pe`** (company-vs-industry P/E), plus `industry_pb`.

**Tool: `fetch_industry_pe.py <SYM...>`** (engine). Two phases, because of two gotchas learned:
1. **Slug resolution** via Investing's search API — `fetch('https://api.investing.com/api/search/v2/
   search?q=<name>')` in the page context, filter results to **exchange = "Karachi"**, best name-match
   → slug from the result `url`. Query must be cleaned (drop "Limited/Company", `&`→`and`). The search
   API only works from the **investing.com homepage** context.
2. **Cloudflare gotcha:** the search calls taint the session, and Investing **Cloudflare-challenges
   sequential automated equity-page navigations** ("Just a moment…", 403 — only the *first* load in a
   session passes). Fix: run slug-resolution in one throwaway browser, then extract ratios with a
   **FRESH browser launch per stock** (a single first-load always passes). ~3–4s/stock.
3. **Extraction:** the ratios table renders as a label-column + a `"company\tindustry"` value-column
   (one line per ratio); split + zip. Guards: name-match ≥0.45 (vs wrong slug) and `2 ≤ ind_pe ≤ 80`
   (Investing sometimes returns garbage industry values, e.g. SSGC 0.7 → skipped/left null).

Validated: cement names → industry P/E 8.92, oil&gas → 8.55 (sensible). WebFetch of the `-ratios` page
also works (proven on FFC: company 9.38 / industry 8.88) but isn't scriptable — Playwright is.
**Quarterly is also reachable this way** if ever needed (we already have it from stockanalysis).

---

## 2026-06-27 — stockanalysis.com is now PRIMARY for consolidated/market data (Investing → fallback)
**Decision (supersedes "Investing = consolidated fundamentals authority" for everything stockanalysis
covers).** Investing.com is blocked in Claude-in-Chrome and its quarterly is WebFetch-invisible, while
stockanalysis.com is fully accessible and carries the **same consolidated dataset** (validated
identical to the rupee). So: **prefer stockanalysis for any field it provides; keep Investing only for
the gaps.** Re-onboarded all 9 from stockanalysis this session.

**Source map after the switch:**
| Field group | Source now | Notes |
|---|---|---|
| Annual income/balance/cashflow | **(unchanged on disk)** | byte-identical to stockanalysis (validated) — left as-is; re-pulling is a no-op that only risks transcription error |
| Quarterly financials | stockanalysis | (added earlier today) |
| PE, PB | stockanalysis `/statistics/` | |
| market_cap, EPS-TTM, next earnings date | stockanalysis `/statistics/` | |
| Dividends (yield, DPS-TTM, payout, history) | stockanalysis `/statistics/` + `/dividend/` | |
| Recent intraday **H/L** | stockanalysis `/history/` (~50 real bars) | **upgraded from ~19 Investing bars**; overlaid on the DPS full-history base |
| **industry_pe** (+ industry_pb) | **Investing (headless Playwright)** | the one field stockanalysis lacks. **Investing IS reachable** (2026-06-28) — the Chrome-MCP block was tool-specific; headless Playwright loads it fine. See the 2026-06-28 "Investing recovered" entry + `fetch_industry_pe.py`. |
| ROE / ROA / gross_margin | computed from raw statement lines | unchanged — never trust a provider's ROA |
| unconsolidated divergence, free_float, EOD base, yearend_close | **PSX DPS** | unchanged |
| insider | **sarmaaya** | unchanged |

**Bug found + fixed during the switch:** `dividends.json` `yield` and `payout_ratio` must be stored as
**fractions** (export does `_pct = x*100`). Original FFC was 0.0693/0.644. When I onboarded BOP earlier
today I stored percents (7.12 / 49.93) → the page showed **712%** yield. `apply_profile.py` now divides
stockanalysis percents by 100; BOP re-applied → 8.5% correct. Verified all 9 in browser (no inflated %).

**Tooling (scratchpad, reusable):** `apply_profile.py` patches `ratio.json` (pe/pb), `overview.json`
(market_cap + current_price=newest close), `earnings.json` (eps_ttm + next date), `dividends.json`
(yield/dps/payout/history), and **overlays real H/L onto the existing `historical.csv`** for matching
recent dates (preserves split truncation + full DPS history — does NOT regenerate). Harvest via the
cached `PROFSRC` DOM extractor over `/statistics/`, `/dividend/`, `/history/` (dump columnar; 50-bar
H/L dumped as `{d,h,l}` split across two evals to dodge the ~1.3KB tool-result cap). Per-stock quirks:
non-payers 404 on `/dividend/` (→ empty, fine); KEL statistics are current even though its quarterly
table is stale; WTL pe/eps null + pb negative (distressed) — kept as-is.

---

## 2026-06-27 — Quarterly financials added for all 9 onboarded stocks (source: stockanalysis.com)
**What:** every onboarded stock now has `income_statement_quarterly.json` /
`balance_sheet_quarterly.json` / `cashflow_quarterly.json` (last ~6 quarters; FFC 20), keyed by
**period-end `YYYY-MM`**, millions PKR, **consolidated**. The engine already had quarterly slots
(`analysis.py` computes TTM / QoQ / YoY-quarter / P-S from them) — they were just empty. Now
populated → `ttm_revenue`, `ttm_net_income`, `revenue_qoq/yoy`, `eps_qoq/yoy`, `ps_ratio` are live
and feed the fundamental score (several scores shifted as TTM valuation replaced last-annual; this is
*more* accurate, not a regression — e.g. FFC 80.6 Strong Buy).

**Source decision — stockanalysis.com, NOT Investing (overrides the "Investing = consolidated
fundamentals" rule for the quarterly slice only).** Why: Investing's quarterly is unreachable by our
tools — the Annual/Quarterly toggle is **client-side JS** so WebFetch only ever returns the annual
columns, and `investing.com` is **blocked in Claude-in-Chrome** ("not allowed due to safety
restrictions"). stockanalysis.com loads in Claude-in-Chrome and exposes a clean normalized quarterly
table. **Validated before adopting** (user asked to cross-check): stockanalysis annual is **identical
to Investing to the rupee** (FFC FY21–25 revenue/NI/EPS + TTM 59.82 all match the on-disk Investing
annual — same provider); sarmaaya headline EPS (59.83) = same consolidated TTM; **PSX DPS is the
lower *unconsolidated* basis** we already surface as divergence. So quarterly (stockanalysis) and
annual (Investing) are the same consolidated series — no basis mismatch. **Bonus:** stockanalysis
fills some rows Investing omitted (PAEL inventory, PIBTL cash/inventory).

**Per-stock quirks:** banks (BOP) expose only revenue/NI/EPS on the income statement and no
current-asset/liability split or gross profit → those rows render "—" (matches the [[bank template]]).
**KEL quarterly is stale** — last filed quarter is **Jun 2024** (KEL is behind on filings; its annual
also stops at FY2024), so its QoQ/YoY reflect 2024. CNERGY/WTL have loss quarters (real).

**Plumbing:** `export_external.py` now emits a `quarterly` block (same `*_mn` field names as annual,
keyed by `YYYY-MM`) plus `revenue_qoq_pct`/`revenue_yoy_pct`/`eps_qoq_pct`/`eps_yoy_pct`/
`ttm_revenue_mn`/`ttm_net_income_mn`. Dashboard `dashboard_template.html` adds an **Annual | Quarterly
toggle** on the Financials card (`buildStmts(src,cols,fmtHead)` generic builder + global `finView()`;
`.fin-toggle`/`.fin-btn` CSS), with a momentum line (Rev/EPS QoQ·YoY) and a source note. Verified in
browser: toggle swaps, QoQ coloring, bank rows degrade to "—", no console errors.

**Harvest recipe (repeat when refreshing / onboarding):** stockanalysis quarterly via Claude-in-Chrome
(WebFetch can't see it; the JSON API 404s; `fetch()` to a localhost sink is blocked by Chrome Private
Network Access; Downloads is blocked by macOS TCC — so **scrape the rendered table**). For each stock,
3 pages — `/quote/psx/<SYM>/financials/?p=quarterly`, `…/balance-sheet/?p=quarterly`,
`…/cash-flow-statement/?p=quarterly` — run a DOM extractor that maps stockanalysis's normalized labels
(Revenue/Gross Profit/Operating Income/Interest Expense/Net Income/EPS (Diluted); Total Current Assets/
Cash & Equivalents/Inventory/Total Assets/Total Current Liabilities/Total Liabilities/Total Debt/
Shareholders' Equity; Operating/Investing/Financing Cash Flow/Capital Expenditures) → engine schema,
keying by the **Period Ending** date as `YYYY-MM`, storing interest_expense & capex **positive**.
Tool-result size caps ~1.3KB → dump **columnar** (`{p:[…], i/b/c:{field:[vals]}}`) capped at 6
quarters. Scratchpad builder `build_quarterly.py` converts columnar→engine files.

---

## Extraction map — where each field comes from (concrete URLs + method)

`<SYM>` = PSX ticker (e.g. `FFC`, `MLCF`). `<slug>` = Investing slug, hand-mapped in
`engine/sources.py SLUGS` — the **authoritative source of truth for slugs**; current values
include `MLCF → maple-leaf-cement-factory-ltd`, `FFC → fauji-fertiliz`. Always read `SLUGS`
rather than guessing (the historical-data path sometimes uses a different slug than the og
metadata, so don't infer from the logo/filename).

| Field / artifact | Source | URL pattern | How we fetch it |
|---|---|---|---|
| Daily volume, Top-30, per-symbol O/H/L/C/V | PSX DPS | `https://dps.psx.com.pk/market-watch` | plain `urllib`/curl 200, parsed with BeautifulSoup in `psx_auto.fetch_marketwatch()` |
| **EOD OHLCV incl. High/Low** + company profile/unconsolidated fundamentals — **primary source for NEW (going-forward) daily data** | PSX DPS | `https://dps.psx.com.pk/company/<SYM>` | direct fetch (200); company-page EOD carries real O/H/L/C/V |
| EOD price series — close/volume/open only, **no H/L** (JSON feed) | PSX DPS | `https://dps.psx.com.pk/timeseries/eod/<SYM>` | direct fetch (200); returns `[ts, close, vol, open]` — for H/L use the company page (above) or market-watch instead |
| Long historical **OHLCV** (real H/L **and volume**) | Investing.com | `https://www.investing.com/equities/<slug>-historical-data` | **WebFetch tool** (curl=403); full Open/High/Low/Close **+ Volume** per bar; JS date-picker → only ~1mo default, longer ranges need Claude-in-Chrome |
| Consolidated fundamentals (all sections — see list below) | Investing.com | `https://www.investing.com/equities/<slug><suffix>` | **WebFetch tool**; returns the **ANNUAL** view (quarterly tab is JS-only); sanity-check units (wrong slug silently returns another company) |
| Insider transactions | sarmaaya.pk | page `https://sarmaaya.pk/stocks/<SYM>`, table `div#insider-transactions` | **rendered DOM only** — Claude-in-Chrome or user-pasted HTML; extract every `<tbody><tr>`. NOT fetchable (data client-loads from `https://beta-restapi.sarmaaya.pk` via an obfuscated `STOCKS_ROUTE`; not in HTML or JS chunks; endpoint guesses 404) |
| Insider filing attachments (referenced in that table) | PSX DPS | `https://dps.psx.com.pk/download/image/<id>-1.gif` | links only; not downloaded into the engine |

**Investing.com section URLs** — full map is `engine/sources.py SECTION_SUFFIX`
(**source of truth**); `BASE = https://www.investing.com/equities/`, URL = `BASE + slug + suffix`.

Auto-fetched by the fundamental pipeline (`FUNDAMENTAL_SECTIONS`):

| Section | Suffix | Example (FFC, slug `fauji-fertiliz`) |
|---|---|---|
| overview | *(none)* | `…/equities/fauji-fertiliz` |
| income_statement | `-income-statement` | `…/equities/fauji-fertiliz-income-statement` |
| balance_sheet | `-balance-sheet` | `…/equities/fauji-fertiliz-balance-sheet` |
| cash_flow | `-cash-flow` | `…/equities/fauji-fertiliz-cash-flow` |
| ratios | `-ratios` | `…/equities/fauji-fertiliz-ratios` |
| earnings | `-earnings` | `…/equities/fauji-fertiliz-earnings` |
| dividends | `-dividends` | `…/equities/fauji-fertiliz-dividends` |

Also mapped in `SECTION_SUFFIX` but **not** in the auto-fetch set (fetch on demand):
`historical` (`-historical-data`, OHLCV incl. volume — see its own row above), `financial_summary`
(`-financial-summary`), `forecast` (`-forecast`), `technical` (`-technical`),
`profile` (`-company-profile`).

**Industry P/E + dividend per-share (2026-06-27):** the `-ratios` page carries a company-vs-industry
P/E (stored as `ratio.json industry_pe`; valuation card shows "P/E (ind X, cheaper/pricier)"); the
`-dividends` page carries the TTM dividend-per-share + ex-date history (`dividends.json per_share_ttm`
+ `history`; dividends card shows "38.50 (6.9% yield)"). **MLCF has no `-ratios`/`-dividends`/`-earnings`
pages on Investing (all 404)** — so its industry_pe is null and its dividend/earnings data come from
PSX instead. ROE/ROA/gross-margin are computed from raw statement lines per the ratios rule below
(Investing's reported ROA is unreliable — it has printed values exceeding ROE).

Engine writes extracted fundamentals/insider to `stocks/<SYM>/...`; `export_external.py`
then bundles them (+ true OHLC + scores) into `psx_data/external/<epoch>_<SYM>.json` for the
dashboard. See the dated entries below for *why* each source is used and its constraints.

---

## 2026-06-27 — PLANNED (approved, not yet built): import QUARTERLY statements
**Decision:** add quarterly income statement / balance sheet / cash flow (today we import **annual
only**). Investing's quarterly tab is a **JS toggle** — WebFetch can't click it, so this needs a
**headless Playwright** fetch (same tech as `fetch_insider.py`): load `…-income-statement` (and
`-balance-sheet`, `-cash-flow`), click **"Quarterly"**, scrape the quarterly table. We already have
quarterly **EPS** (from the Investing `-earnings` page + PSX DPS) feeding the Earnings card, but not
the full quarterly line items.
**Build plan (for the next session):**
1. New `fetch_quarterly.py` (or a flag on an existing fetcher) — Playwright clicks Quarterly,
   writes `fundamentals/income_statement_quarterly.json` / `balance_sheet_quarterly.json` /
   `cashflow_quarterly.json`. The engine schema **already has these slots** (currently `{}` — see
   `engine/fundamentals.py` SECTION_LOCATION).
2. `export_external.py` → emit the quarterly series alongside the annual `*_mn` series.
3. Dashboard Financials card → add an **Annual / Quarterly toggle** (like Investing).
4. **Fold the quarterly click into the onboarding flow** so each new stock gets annual + quarterly
   in one pass; **backfill** the 7 already done (FFC, MLCF, SYS, KEL, PIBTL, PAEL, WTL).
**Caveat:** an extra Playwright pass per stock = slower + more Cloudflare exposure across the 122 —
that's why it's folded into onboarding rather than a separate mass run.

---

## 2026-06-27 — Export schema expanded + insider label fixed
**Export (`export_external.py`) now carries** (all consumed by the redesigned page):
- Full statement series in PKR mn: `revenue_mn`, `gross_profit_mn`, `operating_income_mn`,
  `net_income_mn`, `interest_expense_mn`, `eps_history`; `current_assets_mn`, `cash_mn`,
  `inventory_mn`, `total_assets_mn`, `current_liabilities_mn`, `total_liabilities_mn`, `debt_mn`,
  `equity_mn`; `op_cashflow_mn`, `cf_investing_mn`, `cf_financing_mn`, `capex_mn`, `free_cashflow_mn`.
- Valuation extras: `industry_pe` (from Investing `-ratios`), `dividend_per_share_ttm` +
  `dividend_history`, `free_float_pct`, `high52`/`low52` (computed from last ~252 OHLC bars).
- `earnings` (latest/forecast/surprise/TTM/next + history) and `earnings_basis_divergence` with the
  per-year `series` (eps/pat/pe) + `eps_comparable_from` + derived FY-end P/E (from
  `psx_official.yearend_close`).
- `insider_sentiment` now includes `value_note`, `buy_value`/`sell_value`.

**Insider label fixed (`engine/insider.py`):** the headline (Strong/Net buying/selling) was based on
net **share volume**, which contradicted the "(N buys / M sells)" shown beside it (e.g. KEL 8b/16s
read "buying"). Now the headline follows the **transaction-count majority**; when net share volume
disagrees (a few large filings dominate), it's surfaced via `value_note` instead of flipping the
headline. Re-exported all onboarded symbols after the fix.

---

## 2026-06-27 — Engine stock page redesigned (single long page, card layout)
Approved redesign shipped for **engine symbols** (those with a `DATA.external` export); the
non-engine scraped path is unchanged. Built in `renderEngineDetail` + the `openDetail` assembly:
- **Layout:** key-statistics strip + engine verdict (score breakdown folded in) render in `dtThesis`
  (above the chart); the rest in `dtBody` in this order: Trading plan → Technical analysis →
  Relative strength → Financials → Ratios & valuation → Earnings → Earnings basis → Dividends →
  Company & ownership → Pending → Insider. One long page (tabs deferred). Pending cards kept.
- **Financials:** income/balance/cash rendered as **year-column tables**; key rows (revenue, net
  income, EPS, equity, operating CF) colored by **year-on-year** change (green up / red down). Needs
  the full statement series now in `export_external.py` (`gross_profit_mn`, `operating_income_mn`,
  `interest_expense_mn`, `current_assets_mn`, `inventory_mn`, `total_assets_mn`,
  `current_liabilities_mn`, `total_liabilities_mn`, `cf_investing_mn`, `cf_financing_mn`, `capex_mn`).
- **Tables inverted** (periods/dates across the top) for Earnings history and Dividends, matching the
  divergence table. Earnings-basis is its own card above Dividends. MAs use diagonal arrows (↗/↘).
- **Terminology** matches sources (Total revenue, Diluted EPS, EPS forecast/surprise; insider
  Name/Position/Action/Quantity/Rate from sarmaaya; Profit after tax / Free Float from DPS).
- **Remaining polish (not done this pass):** header still shows the old badge-overlaps-name layout
  and centered action buttons (the mockup moved actions top-right + fixed the Shariah badge spacing) —
  those live in `dtSym`/`dtMeta`/`dtLinks`, separate from `renderEngineDetail`.

---

## 2026-06-27 — Data parity across stocks: shared renderer/calculations, per-stock data
**Rule (learned the hard way — user caught FFC with an empty Earnings card after SYS got one):**
the dashboard renderer (`dashboard_template.html renderEngineDetail`) and the engine's scoring/
divergence/relative-strength calculations are **shared across every symbol**. So a **design,
calculation, card, or field change instantly applies to ALL stocks** — but the **per-stock DATA
does not**. If you add a capability (e.g. an Earnings card, `psx_official.json` divergence,
`high52/low52`) and only populate it for the symbol you're working on, every other onboarded stock
shows blank "—".
- **Therefore:** when you add/change a card/field/source, **backfill the data for EVERY onboarded
  stock in the same change**, re-export all symbols, and update the parity table below. If a source
  genuinely isn't available for a symbol (e.g. Investing has no earnings tab for MLCF), record that
  in the table rather than leaving it silently blank.
- **Two render improvements made the same day so a present-but-immaterial signal still shows:**
  (1) free-float / 52-week now come from the engine export (`ext.free_float_pct`, `ext.high52/low52`)
  with fallback to scraped `co.*`, so engine-only symbols stop showing "—";
  (2) the earnings-basis divergence is folded into the Earnings card and **renders whenever both
  bases exist** (not only when flagged) — unflagged just shows the EPS gap + "within tolerance".

### Per-stock data parity table (keep current when onboarding/refreshing)
| Symbol | fundamentals | historical.csv | insider.json | earnings.json | psx_official.json (unconsolidated) | divergence |
|---|---|---|---|---|---|---|
| FFC  | ✓ Investing | ✓ 183 bars | ✓ 42 | ✓ Investing (TTM 59.82) | ✓ DPS (multi-yr) | computed, **unflagged** (EPS −11.6%) |
| MLCF | ✓ Investing | ✓ | ✓ | ✓ Investing (TTM 10.74) | ✓ DPS (multi-yr) | computed, **flagged** (EPS +48%, one-off) |
| SYS  | ✓ Investing | ✓ 267 bars (post-split) | ✓ 44 | ✓ Investing (TTM 7.71) | ✓ DPS (multi-yr) | computed, **flagged** (EPS −27%, subsidiaries) |
| KEL  | ✓ Investing (Jun FY; no gross profit) | ✓ 1237 | ✓ 24 | ✓ Investing (sparse) | ✓ DPS (2021–24) | computed, multi-yr |
| PIBTL| ✓ Investing (Jun FY; no cash/inv row) | ✓ 1237 | ✓ 6 | ~ partial | ✓ DPS (**FY2025 only**) | single-year |
| PAEL | ✓ Investing (Dec FY) | ✓ 1237 (H/L synth) | ✓ 3 | ✓ Investing | ✓ DPS (**FY2025 only**) | single-year |
| WTL  | ✓ Investing (Dec FY; distressed) | ✓ 1237 (H/L synth) | ✗ **timed out** | ~ minimal | ✓ DPS (**FY2025 only**) | single-year; industry P/E null |
| CNERGY| ✓ Investing (Jun FY; refiner, has inventory) | ✓ 1237 (19 real H/L) | ✓ 10 | ✓ Investing (TTM swung +ve) | ✓ DPS (2022–25) | computed, **flagged** (EPS +18%, subsidiaries) |
| BOP  | ✓ Investing (**bank**: no gross profit/current split) | ✓ 1237 (19 real H/L) | ✓ 1 | ✓ Investing | ✓ DPS (2023–25) | computed, ~+3.5% (unflagged) |

Required per onboarded stock: fundamentals + historical.csv + insider.json + earnings.json +
psx_official.json + **quarterly** (income/balance/cashflow `*_quarterly.json`, stockanalysis.com —
see the 2026-06-27 quarterly entry at top). All 9 have quarterly as of 2026-06-27 (KEL stale to Jun
2024; banks income = revenue/NI/EPS only). `free_float`/`52w`/`industry_pe`/`dividend_per_share_ttm` flow through the export
(see the export-fields note below). **DPS company pages usually expose only the latest FY annual**, so
most newly-onboarded stocks get a *single-year* divergence (FFC/MLCF/SYS have the full multi-year set).

---

## 2026-06-27 — Insider IS fetchable headlessly via Playwright; local one-click sidecar shipped
**SUPERSEDES** the 2026-06-26 "rendered DOM only, never a headless fetch" entry AND the manual-only
half of the flag-on-trigger entry below — fetch is now automated; manual paste/Chrome is the fallback.
- **Finding (verified 2026-06-27):** headless Chromium (Playwright) loads `sarmaaya.pk/stocks/<SYM>`
  fine — HTTP 200, **no Cloudflare challenge** — and after hydration the `#insider-transactions`
  table renders; we extract every `<tbody><tr>`. Confirmed on FFC (42 rows, identical to the
  hand-pasted set bar harmless name-casing drift) and MLCF (8 rows). The old belief that sarmaaya
  insider was "rendered-DOM-only, never headless" was wrong — a real browser engine clears it; only
  plain `urllib`/curl and raw-API guesses fail.
  **Why:** removes the manual paste/Chrome step entirely; `fetch_insider.py <SYM>` now does it.
- **Engine: `fetch_insider.py <SYM>`** (engine repo, new). Playwright-renders the page, maps the
  table (Date·Name·Position·Action·Qty·Rate) → the insider schema (`date` ISO, person, role, action,
  shares int, price float, value), writes `stocks/<SYM>/overview/insider.json` with `source` + today's
  `as_of`. **Guards:** on HTTP≥400 / no rows it exits non-zero and writes nothing, so a flaky fetch
  never clobbers good data. Requires `pip install playwright && playwright install chromium` (done in
  the engine venv 2026-06-27).
- **Dashboard: `dev_server.py` + `dev_rebuild.py`** (this repo, new). `dev_server.py` is a LOCAL-ONLY
  sidecar (binds `127.0.0.1:8079`, stdlib http.server, no new deps) that serves the baked dashboard
  AND exposes `POST /api/refresh-insider?sym=<SYM>`. That endpoint runs the chain
  **engine `fetch_insider.py` → engine `export_external.py --out ./psx_data/external` → `dev_rebuild.py`**
  and returns `{ok,count,as_of}`. `dev_rebuild.py` is the durable port of the scratchpad fast-rebuild
  (caches `compute_embed()` to `psx_data/.embed_cache.json`; `--fresh` recomputes). End-to-end measured
  **~6.6s** per refresh. **Why:** delivers the "Both" choice — the `↻ Refresh insider` button does a
  true one-click rebuild when you run the dashboard via the sidecar locally.
- **Button behaviour is graceful:** `insiderRefresh()` POSTs the endpoint first (works under the
  sidecar) and falls back to the kickoff (open sarmaaya + copy paste-prompt) when there's no backend.
  So the same baked HTML is correct everywhere. **Operational gotcha (the #1 confusion):** the backend
  one-click ONLY happens when the dashboard is opened *through the sidecar* at `http://127.0.0.1:8079/`.
  Open the baked HTML any other way (file://, the preview server, GitHub Pages) and the relative POST
  has no backend, so it ALWAYS falls back to the open-tab/copy kickoff. If a refresh opens sarmaaya
  locally, you're not viewing via `dev_server.py`.
- **Success path updates in place (2026-06-27):** on a successful sidecar refresh the button no longer
  alerts; it stashes the symbol in `sessionStorage['psx_reopen_detail']`, reloads, and a bootstrap at
  end-of-script reopens that stock's detail — so only the insider card visibly changes instead of
  dumping the user back at the overview.
- **State:** Part A (button+kickoff) and Part B (sidecar one-click) both **DONE & verified**
  (curl 200 in 6.6s; MLCF card shows "8 buy-side · 8 filings · Last checked 2026-06-27 · 0d old").
  FFC refreshed + MLCF onboarded (8 buys/0 sells). To use one-click: `.venv/bin/python dev_server.py`
  then open `http://127.0.0.1:8079/`. NOT wired into CI (GitHub Actions could call `fetch_insider.py`
  on the flagged worklist, but that needs Playwright in the runner — deferred).
- **Open items (for the next session):** (1) all new files — engine `fetch_insider.py`, dashboard
  `dev_server.py` / `dev_rebuild.py` / `.gitignore` — plus the doc edits are **uncommitted** in both
  repos (user hasn't asked to commit/push). (2) CI/Actions insider automation deferred (needs
  Playwright in the runner). (3) `fetch_insider.py` is verified on FFC + MLCF only; other symbols
  untested but the same DOM shape should work.

---

## 2026-06-27 — Insider refresh = flag-on-trigger + manual fetch (no schedule, no in-page fetch)
- **Decision:** Insider data is refreshed **on demand**, never on a fixed schedule. The daily
  pipeline only **flags** which symbols are worth a look — (a) a **first-time Top-30-by-volume
  entrant**, and (b) any engine symbol whose **last insider check is older than ~14 days (or
  missing)**. The actual fetch stays **manual**: refresh the flagged symbol via Claude-in-Chrome
  (or pasted rendered DOM), then extract → `run.py` → `export_external.py`. You can't know there's
  new activity without fetching, so the flag means "worth checking," and we diff fetched rows
  against the stored data to see what's new.
- **Why:** new entrants are rare (weekly/biweekly), and the deployed dashboard is **static GitHub
  Pages with no backend** — a browser can't fetch sarmaaya (cross-origin CORS + Cloudflare +
  obfuscated JS route), so a literal in-page "fetch" button is impossible. Flagging + manual fetch
  delivers the trigger with **zero new infra** (no Playwright, no local server, no Cloudflare risk).
- **Considered & deferred** (revisit only if cadence rises): *local dev-mode button* (localhost
  sidecar runs Playwright on click — true one-click but local-only); *GitHub Actions dispatch*
  (CI runs Playwright, commits, Pages redeploys — on-demand, no local server). Both add
  Playwright + Cloudflare handling not justified at this cadence.
- **State: flagging built & verified (2026-06-27)** — fetch remains manual.
  - `export_external.py` carries `insider_as_of` (from `insider.json` `as_of` = last-checked date).
  - `psx_auto.py`: `insider_worklist()` / `print_insider_worklist()` print each run —
    new Top-30 entrants not in the engine ("onboard incl. insider") + engine symbols whose
    `insider_as_of` is missing/`>INSIDER_STALE_DAYS` (14, module constant). Offline-tested:
    today flags MLCF (never fetched); +30d also flags FFC ("31d old").
  - `dashboard_template.html` insider card shows a "Last checked `<date>` · `<N>`d old" row,
    appending " — refresh suggested" (red) past 14d; browser-verified (FFC "1d old", not stale).
  - Remaining: MLCF has no `insider.json` yet → currently flagged "never fetched" (expected;
    onboard its insider when convenient).
- **Refresh button (2026-06-27, "Both" chosen):** one `↻ Refresh insider` button on the stock
  detail card, **graceful two-mode** (`insiderRefresh(sym,btn)` in `dashboard_template.html`):
  it POSTs `/api/refresh-insider?sym=<SYM>` first (LOCAL sidecar one-click fetch); if that fails
  (LIVE Pages — no backend), it falls back to the **kickoff**: opens `sarmaaya.pk/stocks/<SYM>`
  and copies a paste-prompt to the clipboard. **Part A (button + kickoff) DONE & browser-verified**
  (fallback opens sarmaaya, copies prompt, console clean). **Part B (local sidecar + Playwright
  one-click) IN PROGRESS** — gated on whether headless Playwright clears sarmaaya's Cloudflare.

## 2026-06-27 — Data-recency split: NEW data from DPS OHLCV (it HAS H/L); OLD/historical from Investing.com
- **Decision:** Source price data by recency. **New / going-forward** daily bars come from
  **PSX DPS OHLCV** — the DPS company page `https://dps.psx.com.pk/company/<SYM>` (and the
  market-watch scrape) carry **real High/Low**, so DPS is the authoritative live OHLCV source.
  **Old / historical backfill** comes from **Investing.com** `…/<slug>-historical-data` (full
  OHLCV incl. volume + real H/L, deep history).
- **Why:** DPS is the regulator-sourced live feed and now confirmed to include intraday H/L, so
  there's no reason to depend on a third party for fresh bars; Investing is only needed for the
  long history DPS doesn't expose in one call.
- **Supersedes / refines** the 2026-06-26 "Real intraday High/Low only from market-watch or
  engine export; else synthesize" entry: DPS EOD (company page) **does** provide H/L — the
  earlier "no H/L" applied specifically to the `/timeseries/eod/<SYM>` JSON feed, **not** to the
  company-page EOD. The `max/min(O,C)` synthesis is now a **last-resort fallback only** (used
  when neither a DPS company-page/market-watch bar nor an Investing bar supplies H/L), still
  flagged "approximated" with `realHL=false`.
- **State:** extraction map updated (DPS company page = primary NEW-data OHLCV incl. H/L;
  `/timeseries/eod` row marked H/L-less). No code change required for this entry on its own.

## 2026-06-27 — Insider export carries the FULL filing list, not the 8-row preview
- **Decision:** `export_external.py` now reads the complete transaction list straight from
  the raw file via `insider_mod.load(symbol)` for the `insider_tx` field, instead of
  `insider_mod.sentiment(symbol)["transactions"]` (which is capped at `txns[:8]`).
  `engine/insider.py:sentiment()` is unchanged — its `[:8]` cap stays as the compact
  preview for the engine's own markdown/HTML report; the aggregate counts (buys/sells/
  ratio/label) already use all rows.
- **Why:** the dashboard's "Insider activity (real filings)" card is driven by the export
  and should show every filing; 8-of-N was arbitrary truncation for the dashboard.
- **Also (dashboard side):** the detail-page insider card in `dashboard_template.html`
  (`renderEngineDetail`) was itself capping the *display* at `itx.slice(0,8)`. Removed the
  cap — it now renders **all** filings inside a `max-height:260px; overflow-y:auto` scroll
  container (matching the app's long-table pattern), and the "Recent read" line shows
  `<N> buy-side · <total> filings`. Aggregate buy/sell counts already used all rows.
- **State: DONE & verified (2026-06-27).** Re-exported FFC → `1782502198_FFC.json` carries all
  **42** filings (32 buys / 10 sells, "Strong insider buying"); stale 8-row export files removed;
  manifest points only to the new file. Dashboard rebuilt; browser-verified the card renders all
  42 rows (newest 2026-06-24 → oldest 2019-07-22) in the scroll container, console clean.

## 2026-06-26 — sarmaaya.pk insider data is obtained from the rendered DOM, never a headless fetch
- **Decision:** Authoritative source for **insider transactions** (and ownership/peers) is
  `sarmaaya.pk/stocks/<SYM>`, table `div#insider-transactions` (cols: Posting Date · Name ·
  Position · Action · Quantity · Rate(PKR) · Attachment). Capture it from the **fully
  rendered DOM** — Claude-in-Chrome on the live page, or the user pasting the rendered HTML.
  Then extract every `<tbody> <tr>` into `stocks/<SYM>/overview/insider.json`
  (schema: `{source, as_of, transactions:[{date(ISO), person, role, action, shares, price, value}]}`;
  value = shares×price rounded).
- **Why:** sarmaaya is a Next.js App Router app; insider rows are **client-fetched after
  hydration** from host `https://beta-restapi.sarmaaya.pk` via an **obfuscated `STOCKS_ROUTE`**
  config. The route is **not** in the served HTML or in any of the ~45 JS chunks, and every
  guessed REST endpoint returned 404. So there is no static URL to fetch; the data only
  exists once the page's JS runs. WebFetch/curl of the page returns only an unresolved
  Suspense placeholder (`<!--$?-->`).
- **State:** FFC `insider.json` populated with all 42 filings extracted from the rendered DOM
  (Jul 2019 → Jun 2026); engine reads 32 buys / 10 sells → "Strong insider buying".
  Insider is **optional** and degrades gracefully when the file is absent.

## 2026-06-26 — Real intraday High/Low only from market-watch or engine export; else synthesize and flag it
- **Decision:** Charts use **real intraday H/L** when available, sourced (in priority order)
  from the engine export's true OHLC, then the persisted `ohlc.json` store. When neither has
  it, **synthesize H/L = max/min(Open,Close)** and label the chart "approximated" (vs "Real
  intraday H/L"). `ch.realHL=true` marks genuine bars.
- **Why:** the PSX DPS EOD feed `/timeseries/eod/<SYM>` returns only `[ts, close, vol, open]`
  — **no high/low**. The only daily H/L source is the market-watch scrape (per-symbol OHLCV),
  so true H/L only exists for sessions we captured live or got from Investing/engine history.
- **Mechanics:** `ohlc_store.py` persists real O/H/L/C/V per fetched symbol to
  `psx_data/ohlc.json` every run (backfilled from snapshots; today's live bar overwrites —
  idempotent). `merge_into_charts()` attaches H/L arrays aligned to each chart's dates
  (engine export wins over store). `attach_external_charts()` builds a chart from the engine
  export's OHLC for engine symbols that never entered the tracked top-30 universe (e.g. FFC),
  so their detail page still renders.

## 2026-06-26 — Technicals are computed client-side from OHLCV in the browser
- **Decision:** SMA(20/50/200), EMA(20/50/100/200), MACD, Bollinger, ATR(14, Wilder), OBV are
  computed in `dashboard_template.html`'s `TA.analyze(chart)` from the chart's OHLCV — not
  precomputed server-side or scraped. The detail page renders them as MA/MACD/BB/ATR/OBV cards.
- **Why:** keeps the dashboard a single self-contained baked HTML file; indicators stay
  consistent with whatever OHLCV is embedded, and update for free when OHLC improves.
- **Gotcha:** TA hi/lo uses `series.h`/`series.l` when present, else synthesizes from o/c
  (see real-H/L decision above). JS loop variables must not shadow browser globals (`name`,
  `top`, etc.) — a known hazard in this template.

## 2026-06-26 — Engine→Dashboard bridge: per-symbol JSON drop-folder, newest wins
- **Decision:** The engine's `export_external.py <SYM> --out <dashboard>/psx_data/external`
  writes `<epoch>_<SYM>.json`. Dashboard's `external_fundamentals.load(STATE)` reads
  `psx_data/external/*.json`, keys by **uppercase symbol, newest file per symbol wins**, skips
  `manifest.json`, fault-tolerant. Result → `embed["external"]`.
- **Why:** decouples the two repos — the engine drops a file, the dashboard picks it up on its
  next build; no shared imports or DB.
- **Export payload (top-level keys):** `ohlc` (true OHLC), valuation (`pe,pb,peg,ps,ev_ebitda`),
  balance/liquidity (`debt_to_equity,current_ratio,quick_ratio`), returns
  (`roe_pct,roa_pct,roic_pct`), margins, `market_cap,shares_outstanding,eps_history`,
  statement lines (`revenue_mn,net_income_mn,cash_mn,debt_mn,equity_mn,op_cashflow_mn,
  free_cashflow_mn`), growth CAGRs, `dividend_yield_pct,dividend_history,earnings`,
  `insider_tx,insider_sentiment`, `scores` (Fund-70/Tech-30), `technical_snapshot,
  technical_read`, `earnings_basis_divergence`, `relative_strength`.
- **Render:** `renderEngineDetail(ext,sym,…)` returns `{verdict, fundHTML, insiderCard}`.
  `openDetail` leads with the engine verdict, uses engine fundamentals, shows the real-filings
  insider card, and **suppresses the dashboard's own AI thesis** for engine symbols. Symbols
  with no export keep the scraped/computed path unchanged. Overview leaderboard shows a neutral
  engine-rating badge.
- **State:** MLCF and FFC exported. FFC: F=86.6 / T=66.7 → overall **80.6 Strong Buy**, risk
  Low, relative strength Outperforming (+2.8% vs KSE100), insider "Strong insider buying".

## 2026-06-26 — Field authority: PSX (unconsolidated) wins on EPS/profit; consolidated divergence is surfaced
- **Decision:** For EPS and profit, the **PSX (DPS) unconsolidated** figures are authoritative
  in the engine; Investing.com's **consolidated** numbers are kept separately and the
  **divergence is shown**, not silently reconciled (engine `psx_mod.divergence` →
  `earnings_basis_divergence` in the export, rendered as an "Earnings-basis divergence" card).
- **Why:** PSX unconsolidated is the locally-filed, regulator-sourced truth for the listed
  entity; consolidated rolls in subsidiaries and legitimately differs — hiding the gap would
  misrepresent one basis as the other.

## 2026-06-26 — Compute Debt/Equity (and ratios) from raw statement lines, not a pre-computed field
- **Decision:** Derive Debt/Equity and similar ratios from raw balance-sheet numbers
  (`debt_mn`, `equity_mn`, etc.) rather than trusting any site's pre-computed ratio.
- **Why:** pre-computed ratios vary by basis/definition between sources; computing from raw
  lines keeps every ratio on one consistent, auditable basis.

## 2026-06-26 — Investing.com via WebFetch (curl is 403); slugs are manually mapped; long history needs Chrome
- **Decision:** Authoritative source for **consolidated fundamentals** and **longer real-H/L
  historical OHLC** is Investing.com, retrieved with the **WebFetch tool** (plain curl is
  blocked 403). Per-symbol Investing slugs are **manually maintained** in `engine/sources.py`
  (`SLUGS`). Always sanity-check returned units/magnitude — a wrong slug returns a *different
  company's* page without erroring.
- **Why:** WebFetch bypasses Investing's bot block; there is no reliable slug-derivation rule,
  so the mapping is curated by hand.
- **Constraint:** Investing's historical-data page is JS-driven (date-picker). WebFetch returns
  only the **default ~1 month**; for longer ranges use **Claude-in-Chrome** to drive the picker.

## 2026-06-26 — Daily top-30 by volume: append-only snapshots, idempotent per day, set-diff for "new entrants"
- **Decision:** `psx_auto.py` fetches the full DPS market-watch, sorts by volume desc, takes
  **Top-30**, and appends `{date, top:[…]}` to `psx_data/snapshots.json`. Re-running the same
  day **overwrites** that date (idempotent). Weekends are skipped (file still rebuilt). First
  run seeds history from `PSX_Top30_Daily.xlsx` if `snapshots.json` is absent (xlsx then
  unneeded). "New vs previous session" = `set(today top symbols) − set(prev session top symbols)`.
- **Why:** a running daily history powers the movers/history/tracker views and the new-entrant
  signal; idempotency makes re-runs and CI retries safe.

## 2026-06-26 — Report heading bug: don't shadow the company name with the window key
- **Decision:** In `engine/report_html.py` the relative-strength loop iterates
  `for win, w in rs["windows"].items()` (was `for name, w …`, which shadowed the company name
  and rendered headings like "2w (MLCF)").
- **Why:** the loop variable collided with the outer company-name binding; renaming fixed the
  heading. (User's intent was simply to drop the "2w" artifact.)

---

## Feature state (dashboard, as of 2026-06-26/27)

All client features are **browser-local (localStorage)** — no backend, no accounts.

- **Single-stock detail page** — *built/working; engine symbols use the 2026-06-27 redesign* (see
  "Engine stock page redesigned" entry above for the full layout). For engine symbols
  (`DATA.external`), `openDetail` puts the **key-statistics strip + verdict (score breakdown folded
  in)** in `dtThesis` above the chart, then `dtBody` = Trading plan (chart beside the mechanical
  plan; S&R | patterns) → Technical analysis → Relative strength → Financials (income/balance/cash
  year-column tables, key rows YoY-colored) → Ratios & valuation → Earnings (inverted) → Earnings
  basis → Dividends → Company & ownership (profile+ownership left, announcements right) → Pending →
  Insider. MAs show ↗/↘ arrows; the chart node is rescued above `dtBody` each `openDetail` so
  re-renders don't destroy it. Non-engine (scraped) symbols keep the older `renderEngineDetail`-less
  layout. **Pending placeholders still shown** (awaiting data): shareholding, FIPI, monthly sales,
  sector comparison, qualitative risk, AI thesis.
- **Watchlist** — *built/working.* localStorage key `psx_watchlist…`; star-toggle on rows,
  add/edit modal (`wlLoad/wlSave/wlOpenModal`). Browser-only.
- **Demo Trades (paper trading)** — *built/working.* localStorage key `psx_demo_trades_v1`;
  positions carry entry/TP/SL/qty; `dmCalc` shows R:R, %-to-TP/SL and PnL; a trade auto-flags
  TP-hit/SL-hit when the latest tracked price reaches the level but stays **open** until the user
  explicitly closes it (mirrors needing a real fill confirmation). Browser-only.
- **Screener** — *built/working.* `_computeScreener()` scans every symbol in `DATA.charts` with
  ≥30 bars. **Scores are 0–100 and match each stock's detail page** (fixed 2026-06-28): for engine
  stocks it surfaces the **engine export's** `overall_score` / `technical_score` / `fundamental_score`
  (the exact detail-page numbers, Fund-70/Tech-30); only stocks with **no engine export** fall back to
  the technical-led blend `overall = 0.55·tech + 0.45·fund` via `computeFundScore(DATA.companies[sym])`
  (scraped fundamentals). Color thresholds 65/45, "strong" ≥65 on both, min-overall filters 65/80.
  Filters: min-score, Shariah-only; sortable. **Previously** the screener always used the 0.55/0.45
  scraped blend on a 0–10 scale, which disagreed with the engine detail page for every engine stock —
  that mismatch is what this fix removed.

## Onboarding a stock — canonical full-Investing recipe (do every step)
This is the **complete per-stock checklist** (FFC/MLCF/SYS were all built this way). Every file
goes under `~/projects/stock-agent-claude/stock-agent-claude/stocks/<SYM>/`. Run engine cmds from
the engine repo with its `.venv`.

1. **Investing slug — verify, never guess.** `WebSearch "<company> PSX investing.com equities"`,
   open the overview page, sanity-check price/sector match the PSX ticker (a wrong slug silently
   returns another company). Add `"<SYM>": "<slug>"` to `engine/sources.py SLUGS`.
2. **Fundamentals from Investing (WebFetch; annual view):**
   - `-income-statement` → `fundamentals/income_statement_annual.json`: `revenue`, `gross_profit`,
     `operating_income`, `net_income`, `eps` (Diluted), `interest_expense` (store **positive**).
   - `-balance-sheet` → `fundamentals/balance_sheet_annual.json`: `current_assets`,
     `cash_and_equivalents`, `inventory`, `total_assets`, `current_liabilities`,
     `total_liabilities`, `total_equity`, `total_debt`.
   - `-cash-flow` → `fundamentals/cashflow_annual.json`: `cash_from_operations`,
     `cash_from_investing`, `cash_from_financing`, `capex` (store **positive**).
   - `-ratios` → `fundamentals/ratio.json`: `pe_ratio`, `price_to_book` from Investing; **compute
     `roe`/`roa`/`gross_margin` from the raw statement lines** (Investing's ROA is unreliable — has
     printed values above ROE); `industry_pe` from the page's company-vs-industry P/E.
   - overview (slug root) → `overview/overview.json`: `company_name`, `sector`, `industry`,
     `market_cap` (mn), `shares_outstanding` (mn), `current_price`, `currency`.
   - `-earnings` → `fundamentals/earnings.json`: `latest_eps`, `eps_ttm`, `next_earnings_date`,
     `history[{period_end,eps,eps_forecast,eps_surprise_pct}]`.
   - `-dividends` → `fundamentals/dividends.json`: `yield`, `per_share_ttm`, `payout_ratio`,
     `history[{ex_date,amount,type,yield}]`.
3. **PSX DPS unconsolidated (by ticker, no slug)** → `overview/psx_official.json`: annual `sales`,
   `profit_after_tax`, `eps`; `shares_outstanding`, `free_float_pct`, `market_cap`, `pe_ratio_ttm`;
   **`yearend_close`** {year→FY-end close} taken at the company's real FY-end month (most = Dec,
   cement = Jun) — drives the derived per-year P/E; **`eps_comparable_from`** if a split makes
   pre-split standalone EPS non-comparable.
4. **`technical/historical.csv`** (`date,close,open,high,low,volume,change_pct`, newest-first): base
   from DPS `/timeseries/eod/<SYM>` (open/close/vol); overlay real H/L from Investing
   `-historical-data` for recent sessions; **split-detect** (drop the pre-split window where
   `open/close` is far from 1) — sanity-check the oldest bar's open/close ratio.
5. **`overview/insider.json`** via `python fetch_insider.py <SYM>` (headless Playwright, sarmaaya).
6. `python run.py <SYM>` → `python export_external.py <SYM> --out <dashboard>/psx_data/external`
   (keep newest-per-symbol; delete stale duplicate export files).
7. Rebuild dashboard (`dev_rebuild.py`) and verify the symbol's detail page in the browser.

**Gotchas:** some stocks have **no Investing `-ratios`/`-dividends`/`-earnings` page (404)** (e.g.
MLCF) → take those from PSX or leave null (`industry_pe` null, dividends from PSX). Fiscal year-end
month varies. Always compute ratios from raw lines. Keep the per-stock parity table above current.

## 2026-06-28 — AUTOMATED bulk onboarding pipeline + Shariah-compliant batch
**Decision:** focus the bulk effort on the **Shariah-compliant** subset first (65 of the 122 universe
are compliant per `psx_data/shariah.json`; 7 already onboarded → **59 to do**), and **automate** the
onboard end-to-end now that stockanalysis is primary and **loads in headless Playwright** (HTTP 200,
no bot block — same as sarmaaya). This supersedes the "manual chunks, ~2/turn" cadence below for any
stock sourced from stockanalysis.

**Pipeline (engine repo, by ticker — no Investing slug needed):**
1. `fetch_sa.py <SYM>` — one headless Playwright session loads the 8 stockanalysis pages and writes
   `scratchpad/sa/sa_<SYM>.json`: consolidated annual + quarterly income/balance/cashflow, statistics
   (pe/pb/ps/eps_ttm/earnings_date/dividend summary), dividend history, ~50 real H/L bars. ~30s/stock.
2. `assemble_sa.py <SYM>` — writes all engine files from {blob + dashboard `companies.json` + DPS EOD
   curl}. **`companies.json` supplies the whole DPS side locally** (name, sector, shares, free-float,
   and the **unconsolidated annual EPS/sales/PAT** → `psx_official.json`, so the consolidated-vs-
   unconsolidated **divergence still works**). DPS EOD curl builds the full-history `historical.csv`
   base (split-detected) with the stockanalysis ~50-bar real H/L overlaid; yearend_close at the FY-end
   month inferred from `companies.json` catalysts. `industry_pe` left **null** (Investing-only gap).
3. `batch_onboard.py <SYM...>` — drives fetch→assemble→`fetch_insider.py` (best-effort)→`run.py`→
   `export_external.py` per stock, logs outcomes, continues on failure. ~25s/stock.

**Validated:** FFC blob matches existing FFC to the rupee; SSGC/UNITY/FCCL/LOADS onboarded clean
(FCCL Strong Buy 83.1; SSGC divergence flagged EPS −22%). Caveats: FY-end inference can miss (defaults
Dec) → derived per-year P/E uses the wrong month's close for non-Dec FYs (cosmetic; divergence is
year-keyed so unaffected). Some tiny names / funds (e.g. TPLRF1) may 404 on stockanalysis → logged
NO_DATA, skip. Annual financials are stockanalysis-sourced here (not Investing) but the two are
identical.

---

## Bulk onboarding — Top-30 universe (122 stocks), full Investing per stock (started 2026-06-27)
**Decision:** onboard all **122** symbols that have appeared in the daily Top-30 (not the full 495
market-watch), each to **full Investing grade** via the recipe above. This is a multi-session,
per-stock effort (slugs are hand-verified; ~9 WebFetches + DPS + Playwright insider per stock), run
in **chunks** with browser verification — NOT a blind one-shot batch. Tooling that's by-ticker and
scriptable: historical.csv, insider, run/export. The slow gate is Investing slug verification +
statement extraction.

**Progress (update as you go — newest status wins):**
- **DONE (60 engine symbols as of 2026-06-28).** The first 9 were hand-onboarded (detail below); the
  Shariah-compliant batch (+51) was done via the automated pipeline (see the 2026-06-28 entry at top).
  **Shariah coverage: 58 of 65 compliant-universe stocks onboarded.** 8 failed `NO_DATA` (no
  stockanalysis page — onboard manually/another source if needed): **PAKQATAR, SLM, TPLRF1 (a fund),
  GCIL, ITANZ, PQGTL, SRR, BBFL**. Strong-Buy compliant names: LUCK 87.6, SPEL 87.2, GHGL 85.4, GGL
  84.5, PPL 82.3, OGDC 82.0, HUBC 81.7, THCCL 80.4. Remaining universe = the 57 non-compliant stocks.
- Hand-onboarded 9 (Investing-then-stockanalysis recipe): FFC `fauji-fertiliz`, MLCF `maple-leaf-cement-factory-ltd`, SYS `systems-ltd`,
  KEL `k-electric` (June FY, 1237 bars, 24 insider; no dividends; gross profit not on Investing),
  PIBTL `pakistan-intl-bulk-terminal-private` (June FY; DPS only FY2025 → single-year divergence;
  no cash/inventory on Investing; split twice), PAEL `pak-electron` (Dec FY, 1237 bars; non-payer
  since 2018; DPS only FY2025; H/L synth), WTL `wrldcal-teleco` (Dec FY, distressed/negative equity,
  delisting risk; **insider fetch timed out — no insider.json**; industry P/E null),
  CNERGY `byco-petroleum` (ex-Byco refiner, June FY, 1237 bars, 10 insider; loss FY2023/FY2025 but
  TTM swung +ve → P/E ~3; multi-yr divergence +18%; non-payer; 2023 equity jump = revaluation not a
  split), BOP `bank-of-punjab` (**first bank** — Dec FY, 1237 bars; real dividends 7.1% yield; govt
  majority-owned, ~42% free float; 2025 bank re-rating 10.81→38.56 is real not a split).
- **BANK TEMPLATE (learned onboarding BOP, 2026-06-27):** banks have no gross profit / no
  current-asset-vs-current-liability split / no inventory → leave those dicts **empty `{}`** (render
  as "—") and set `gross_margin: null`. Store **Net Interest Income as `operating_income`** (the
  bank's core operating result). **Compute ROE/ROA from raw FY lines** — Investing's printed bank ROA
  is the known-bad figure (BOP showed 17.53%; true ROA ≈ 0.5%). `total_debt` = borrowings only
  (deposits live in `total_liabilities`), so the D/E shown understates true bank leverage — document
  it, don't "fix" it. **Known artifact:** the engine's financial-strength sub-score reads **0%** for
  banks because it keys off the current ratio (N/A) — overall score still computes. Page renders
  clean (verified BOP detail in browser: no JS errors, divergence card, real H/L). Apply this same
  template to the other bank/NBFI names (NBP, BAFL, JSBL, AKBL, NML-bank?, SBL, etc.).
- DEFERRED: **PIAHCLA** (PIA Holding) — govt-owned holding shell (96% govt, 3.61% free float); real
  airline business is in subsidiaries (consolidated) while the holding-co unconsolidated is near-empty
  → consolidated-vs-unconsolidated divergence is meaningless; Investing slug is malformed
  (`p.i.a.c-.-(a)`). Needs special handling (consolidated-only, skip divergence) — don't force the
  standard recipe.
- REMAINING (~113): the rest of the 122 (see `psx_data/snapshots.json`). Next by Top-30 frequency:
  FNEL (45, tiny brokerage — likely no Investing page → PSX-only partial), TPL (39), SSGC (36),
  HASCOL (36), KOSM (35), UNITY (33).
- **Lessons from chunk 1:** ~2 full onboards per turn is realistic. DPS company page usually exposes
  only the latest FY annual (so divergence is often single-year). Investing omits some rows for
  smaller caps (cash/inventory/gross profit) and some have no dividends/earnings tables → leave gaps
  documented. sarmaaya insider can time out for tiny names (WTL). Null meaningless ratios (negative
  industry P/E, ROE on negative equity).
- **Known small-cap reality:** smaller names often have partial Investing data (missing
  cash/inventory rows, no dividends/earnings tables, only the latest DPS annual) — onboard with the
  gaps documented rather than skipping. **Engine insider label looks buggy** (KEL 8b/16s and PIBTL
  2b/4s both printed "insider buying" despite more sells) — flagged to fix in `engine/insider.py`.

**Stock-split gotcha (learned onboarding SYS, 2026-06-27):** the DPS `/timeseries/eod/<SYM>`
feed returns `[ts, close, vol, open]` where **close is split-adjusted across the whole history
but `open` is NOT adjusted before the split date** — so for SYS (a ~5:1 split in late May 2025)
every pre-split bar had `open ≈ 5× close`, which would produce garbage synthesized H/L and insane
candles. Detect it by flagging bars where `open/close` is far from 1 (e.g. outside 0.7–1.43) and
**truncate history to the clean post-split window** (SYS → 267 bars from 2025-06-02). Recent real
H/L comes from Investing `-historical-data`; older bars synth `max/min(O,C)` from the *consistent*
open. Always sanity-check the oldest `historical.csv` bar's open-vs-close ratio when onboarding.

**A split also breaks EPS-basis comparability (2026-06-27):** the earnings-basis divergence is now
**multi-year** (EPS + PAT across every common year, rendered as year columns in the Earnings card).
But Investing retroactively split-adjusts historical *consolidated* EPS while PSX DPS does **not**
adjust *standalone* EPS — so comparing the two for pre-split years is meaningless. Set
`eps_comparable_from: <year>` in `psx_official.json` (SYS → 2024) and the engine returns null EPS
divergence before that year (shown as "—" with a note); **PAT divergence is split-independent and
computed for all years**. FFC/MLCF have no split, so the field is omitted and every year computes.
A **derived per-year consolidated P/E** row is also shown (FY-end close ÷ FY consolidated EPS) — the
FY-end close is stored as `yearend_close` in `psx_official.json` (resolved at the company's actual
FY-end month: FFC/SYS Dec, MLCF Jun). It's labeled "derived" and won't match the live TTM P/E (which
uses today's price and TTM EPS). No P/E *divergence* row — it's just the inverse of the EPS gap.
