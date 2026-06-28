# HANDOFF — current state (read this first if you're a fresh session)

**Date:** 2026-06-28. The monorepo at `~/projects/Analysis/psx-system/` is **built and working**.
Git-initialized with an initial commit. This file is the cold-start summary; full detail is in
`PROCESS.md`, `ARCHITECTURE.md`, `MIGRATION.md`, and `DECISIONS.md`.

## What this project is (one line)
Tracks PSX daily **top-30 volume leaders**, flags **new entries**, deeply onboards each from
DPS + stockanalysis + Investing + sarmaaya, scores them, and shows everything in a static dashboard
(volume tracker, watchlist with alerts, demo trading, per-stock analysis page).

## Where things came from
- Source repos (UNTOUCHED — safety net, retire later): dashboard `~/projects/Analysis/psx-top30`,
  engine `~/projects/stock-agent-claude/stock-agent-claude`. The monorepo is a **copy** of both with
  paths fixed; nothing was moved or deleted.

## DONE and verified
- Files copied into `engine/`, `dashboard/`, `data/`; all hardcoded `~/...`/scratchpad paths made
  **monorepo-relative** (`ROOT/data`, `ROOT/.cache`, `ROOT/.venv`).
- **Self-contained `.venv`** (`requirements.txt`; `playwright install chromium` done).
- **Dashboard build** works → renders all 60 engine symbols (`dashboard/dev_rebuild.py`).
- **Engine** run + export works → `data/external/<SYM>.json`.
- **Full onboarding** of a new stock works end-to-end (validated by onboarding **TPL** fresh).
- **`scripts/daily_run.py`** orchestrator works (scrape → new-entry diff → auto-onboard → rebuild →
  publish `dashboard/index.html`). Tested via `--no-scrape`.
- Browser-verified: detail pages render (Shariah badge, two-col Key Stats, real H/L, divergence,
  industry-P/E annotation e.g. LUCK "8.22 (ind 8.92, cheaper)").
- `.github/workflows/daily.yml` written (cron 16:00 UTC Mon–Fri = 9 PM PKT).

## NOT done / next steps (in priority order)
1. **Decide the runtime** — GitHub Actions vs a VPS (e.g. Namecheap VPS). See "Hosting" below; this is
   an open decision. Code runs the same either way (Python + cron + Playwright); only the host differs.
2. **Live scrape untested** — `psx_auto`'s market-watch fetch needs an open trading session. Everything
   *except* the live fetch is verified. Run `python scripts/daily_run.py` (no flag) on a trading day to
   confirm the top-30 + OHLCV append + new-entry onboarding works live.
3. **Create the GitHub repo** → push → Settings/Pages = GitHub Actions → test via **Run workflow**
   (workflow_dispatch) before trusting the cron.
4. **Refactor onboarding scripts into `fetchers/`** — they currently live in `engine/` (`fetch_sa.py`,
   `assemble_sa.py`, `fetch_industry_pe.py`, `fetch_insider.py`, `batch_onboard.py`) and work; the
   target is to port them onto the `fetchers/base.py` fallback-loop framework (try-every-method).
5. **`index.html` is ~7 MB** (60 stocks embedded) — lazy-load per-stock data to slim it.

## Carryover work from earlier this session (not monorepo-specific)
- **Shariah onboarding:** 58/65 compliant stocks done; **8 `NO_DATA`** (no stockanalysis page):
  PAKQATAR, SLM, TPLRF1, GCIL, ITANZ, PQGTL, SRR, BBFL — need manual/alt source.
- **industry_pe:** 35/60 patched; **14 `NO_RATIOS`** are retryable (Cloudflare intermittent):
  SPSL, SSGC, STCL, SYM, TELE, THCCL, TOMCL, TREET, TRSM, UNITY, WAHDAT, WASL, WAVES, WTL.
- The **57 non-compliant** universe stocks are un-onboarded (do them with `engine/batch_onboard.py`
  if/when full-universe coverage is wanted).

## Gotchas (full detail in DECISIONS.md)
- Investing: search API works only from the homepage; **Cloudflare challenges sequential loads** →
  fresh browser per page. Datacenter IPs (GitHub Actions) get challenged harder.
- Dividend `yield`/`payout_ratio` stored as **fractions** (export ×100). ROE/ROA/margins **computed
  from raw lines**. FY-end inferred from filings (defaults Dec). `industry_pe` is a **sector average**.

## How to run (monorepo)
```
cd ~/projects/Analysis/psx-system
./.venv/bin/python scripts/daily_run.py            # full nightly job (live scrape)
./.venv/bin/python scripts/daily_run.py --no-scrape# detect/onboard/build only
cd engine && ../.venv/bin/python batch_onboard.py <SYM...>   # onboard specific stocks
cd dashboard && ../.venv/bin/python dev_rebuild.py --fresh   # rebuild dashboard from data/
```

## Hosting decision (GitHub Actions vs Namecheap) — captured for the fresh session
- **GitHub Actions (current default):** free, zero-maintenance, cron + Playwright work, auto-deploys
  Pages, state committed back to the repo. Caveat: datacenter IP → Investing Cloudflare can be harsher
  (mitigated by the fallback ladder; `industry_pe` degrades to "—").
- **Namecheap *shared* hosting:** fine for serving the static dashboard + a custom domain, but
  **cannot run the nightly Playwright scraping** (no chromium / restricted processes) → not enough on
  its own.
- **Namecheap *VPS* (or any $5–10/mo VPS — DigitalOcean/Hetzner/Linode):** can run the *whole* thing
  (cron + Playwright + serve the dashboard). **Better than Actions for the scraping** (stable IP →
  fewer Cloudflare blocks, persistent disk state, no job-time limits), at the cost of ~$6/mo and you
  managing the box. Recommended if Investing scraping needs to be rock-solid.
