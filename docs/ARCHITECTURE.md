# PSX Volume Monitor — Architecture & Design

Technical companion to `PROCESS.md`. Describes the target **monorepo** layout, the data flow, the
**robust-fetch** framework, the **GitHub Actions** nightly automation, and the **auto-onboard** flow.

> Status: this is the *target* design for the consolidated monorepo. The system currently lives in two
> repos (`~/projects/Analysis/psx-top30` = dashboard, `~/projects/stock-agent-claude/...` = engine).
> `MIGRATION.md` is the step-by-step to fold them into this structure.

---

## 1. Repository layout (monorepo)

```
psx-system/
├── README.md                  # quickstart + what this is
├── requirements.txt           # one dependency set (incl. playwright)
├── docs/
│   ├── PROCESS.md             # newcomer-readable end-to-end process
│   ├── ARCHITECTURE.md        # this file
│   ├── DECISIONS.md           # append-only decision log (data sources, gotchas) — moved from repos
│   └── MIGRATION.md           # how the two old repos map into here
├── fetchers/                  # robust, source-specific data fetchers (the fallback loop)
│   ├── base.py                # Fetcher base + try-every-method loop
│   ├── dps.py                 # PSX DPS: market-watch top-30, EOD timeseries, company financials
│   ├── stockanalysis.py       # consolidated financials, statistics, dividends, history (Playwright)
│   ├── investing.py           # industry P/E (slug search + ratios, Playwright, Cloudflare-aware)
│   └── sarmaaya.py            # insider transactions (Playwright)
├── engine/                    # scoring + per-stock data store
│   ├── ... (analysis, indicators, scoring, schema, report)
│   └── stocks/<SYM>/          # one folder per onboarded stock (the data store)
├── dashboard/                 # static-site generator
│   ├── build.py               # assembles psx_dashboard.html / index.html from template + data
│   ├── template.html          # the single-file dashboard UI
│   └── (served on GitHub Pages)
├── data/                      # shared state (single source of truth)
│   ├── snapshots.json         # daily top-30 history
│   ├── companies.json         # DPS-side per-symbol data (name, sector, free float, unconsolidated)
│   ├── ohlc.json              # real intraday H/L store
│   ├── shariah.json, sectors.json
│   └── external/              # one JSON per onboarded stock (engine -> dashboard bridge)
├── scripts/                   # orchestrators (the entry points)
│   ├── daily_run.py           # THE nightly job: top-30 -> new entries -> onboard -> score -> publish
│   ├── onboard.py             # full onboard of one stock (used by daily_run and manually)
│   └── refresh_fundamentals.py# periodic (~quarterly) fundamentals refresh
└── .github/workflows/
    └── daily.yml              # cron 16:00 UTC Mon–Fri -> run daily_run.py -> deploy Pages
```

**Why this shape:** one clone, one `pip install`, one command to run the daily job, one folder of data,
and a clean separation: `fetchers/` (get data) → `engine/` (score) → `dashboard/` (show) with `data/`
as the shared bus. GitHub Actions runs `scripts/daily_run.py` and deploys `dashboard/` output to Pages.

---

## 2. Data flow

```
                 ┌─────────── nightly (GitHub Actions, 9PM PKT weekdays) ───────────┐
                 │                                                                   │
 PSX DPS ──► fetchers/dps ──► top-30 + EOD OHLCV ──► data/snapshots.json            │
                 │                    │                                              │
                 │             detect NEW ENTRIES                                    │
                 │                    │                                              │
                 │            ┌───────┴── for each new entry ──┐                     │
 stockanalysis ─►│ fetchers/stockanalysis ─┐                   │                     │
 Investing ─────►│ fetchers/investing ─────┤► scripts/onboard ─► engine/stocks/<SYM> │
 sarmaaya ──────►│ fetchers/sarmaaya ──────┘                   │         │           │
                 │                                             │   engine scores     │
                 │                                             ▼         │           │
                 │                                   data/external/<SYM>.json        │
                 │                                             │                     │
                 │                              dashboard/build.py                   │
                 │                                             ▼                     │
                 │                          psx_dashboard.html / index.html ──► Pages│
                 └───────────────────────────────────────────────────────────────────┘
```

**Authority per field** (unchanged from today — see `DECISIONS.md` for the full map):
- Daily volume / top-30 / EOD prices / unconsolidated financials / free-float → **PSX DPS**
- Consolidated financials / ratios / dividends / real recent H/L → **stockanalysis.com**
- Industry-average P/E → **Investing.com** (only field it uniquely has)
- Insider transactions → **sarmaaya.pk**
- ROE/ROA/margins → **computed from raw statement lines** (never a site's pre-computed value)

---

## 3. Robust fetching (the "try every possible way" requirement)

Every source has a **fetcher** that exposes one job (e.g. `dps.top30()`, `stockanalysis.financials(sym)`)
and tries **multiple methods in order** until one returns valid data. `fetchers/base.py`:

```
class Fetcher:
    methods = [...]   # ordered callables, cheapest/most-reliable first
    def get(self, *args):
        for method in self.methods:
            try:
                data = method(*args)
                if self.is_valid(data):     # source-specific validity check
                    return data
            except Exception as e:
                log(method, "failed:", e)   # log and fall through
            backoff()                       # small wait between attempts
        raise AllMethodsFailed(...)          # only after every method tried
```

**Method ladders per source** (learned this session — see `DECISIONS.md`):
- **DPS** → `urllib/requests` (JSON, works directly) → headless Playwright (fallback if blocked).
- **stockanalysis** → headless Playwright (page is JS-rendered; `requests` returns no data). One
  browser session can load all of a stock's pages.
- **Investing** → Playwright **search API** to resolve the page slug (only works from the homepage
  context), then a **fresh browser per page** to read the ratios (Cloudflare challenges *sequential*
  automated loads — a single first-load passes). Falls back to WebFetch-style render if needed.
- **sarmaaya** → headless Playwright (route-obfuscated; data is client-loaded into the DOM).

**Validity checks matter** — a 200 response or a rendered page isn't enough; e.g. an Investing
industry P/E must be a positive number in a sane range (2–80) or it's rejected as garbage. Each fetcher
defines `is_valid()` so a "successful but wrong" fetch doesn't poison the data.

**Why fallbacks are essential here:** these are public sites with bot protection that changes. GitHub
Actions runs from a datacenter IP, which sites treat more suspiciously — so the ladder (and per-method
retries / fresh contexts) is what keeps the nightly job working unattended.

---

## 4. Nightly automation (GitHub Actions)

`.github/workflows/daily.yml`:
- **Trigger:** `schedule: cron("0 16 * * 1-5")` — 16:00 UTC = 21:00 PKT, Monday–Friday. (PKT has no
  DST, so the offset is constant.) Plus `workflow_dispatch` for manual runs.
- **Job steps:** checkout → set up Python → `pip install -r requirements.txt` → `playwright install
  --with-deps chromium` → `python scripts/daily_run.py` → commit updated `data/` + built dashboard back
  to the repo → deploy `dashboard/` output to **GitHub Pages**.
- **Secrets/state:** no external DB — state lives in the repo (`data/`, `engine/stocks/`). The workflow
  commits the day's changes so history is versioned. (If the repo grows large, move `engine/stocks` and
  `data/external` to a release artifact or a data branch.)
- **Resilience:** the run is wrapped so a single stock's onboarding failure doesn't abort the whole job
  (each onboard is isolated, logged, and skipped on failure — same pattern as today's `batch_onboard`).

**Known risk on Actions:** Investing's Cloudflare may be stricter from a datacenter IP. Mitigations:
the per-source fallback ladder, `industry_pe` is non-critical (degrades to "—"), and the daily job's
*core* (DPS top-30 + OHLCV + dashboard) uses only direct HTTP, so it stays green even if browser
scraping has a bad night.

---

## 5. Auto-onboard flow (new entries, nightly)

When `daily_run.py` finds a symbol in today's top-30 that has no `engine/stocks/<SYM>/`:
1. `scripts/onboard.py <SYM>` runs the full Section-3 pipeline via the `fetchers/`.
2. On success → the stock gets scored + exported and appears on the dashboard the same night.
3. On failure (e.g. a tiny name with no stockanalysis page) → it's logged as `NO_DATA` and still shown
   in the volume list using the lightweight DPS data we already have; a retry is attempted on later runs.

This mirrors what we built manually this session (`fetch_sa.py` + `assemble_sa.py` + `batch_onboard.py`
+ `fetch_insider.py` + `fetch_industry_pe.py`) — the migration folds those into `fetchers/` + `scripts/`.

---

## 6. What changes vs. today (so nothing breaks)

- The **code already exists and works**; this is reorganization + automation, not a rewrite.
- Migration **copies** files into the monorepo and fixes the hardcoded cross-repo paths (the engine
  currently writes to `~/projects/Analysis/psx-top30/psx_data/external`; in the monorepo that becomes a
  relative `data/external`).
- The two old repos are kept untouched until the monorepo is verified end-to-end, then retired.
- See `MIGRATION.md` for the exact file-by-file mapping and the cutover checklist.
