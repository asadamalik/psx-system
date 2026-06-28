# Migration — two repos → monorepo

How to fold the current two repos into `psx-system/`. **Copy, don't move**, until the monorepo is
verified end-to-end; then retire the originals.

- **Engine repo:** `~/projects/stock-agent-claude/stock-agent-claude`
- **Dashboard repo:** `~/projects/Analysis/psx-top30`

## File mapping

| From (current) | To (monorepo) | Notes |
|---|---|---|
| engine: `engine/*.py` | `engine/engine/*.py` | core scoring lib — unchanged |
| engine: `run.py`, `export_external.py`, `make_chart.py`, `parse_raw.py`, `update_prices.py` | `engine/*.py` | per-stock run/export |
| engine: `stocks/<SYM>/` (62) | `engine/stocks/<SYM>/` | the data store — copy as-is |
| engine: `fetch_sa.py` | `fetchers/stockanalysis.py` | refactor into a `Fetcher` (Section 3) |
| engine: `fetch_industry_pe.py` | `fetchers/investing.py` | refactor into a `Fetcher` |
| engine: `fetch_insider.py` | `fetchers/sarmaaya.py` | refactor into a `Fetcher` |
| engine: `assemble_sa.py` | `scripts/onboard.py` (assembly half) | reads `data/companies.json` + DPS |
| engine: `batch_onboard.py` | `scripts/onboard.py` (driver) + called by `daily_run.py` | |
| dashboard: `psx_auto.py` | `scripts/daily_run.py` (top-30 + OHLCV half) | the DPS daily scrape |
| dashboard: `build_lib.py`, `ohlc_store.py`, `external_fundamentals.py`, `dev_rebuild.py` | `dashboard/build.py` (+ helpers) | site assembly |
| dashboard: `dashboard_template.html` | `dashboard/template.html` | the UI (unchanged) |
| dashboard: `dev_server.py` | `scripts/dev_server.py` | local preview + insider sidecar |
| dashboard: `psx_data/*.json` | `data/*.json` | shared state |
| dashboard: `psx_data/external/` | `data/external/` | engine→dashboard bridge |
| both: `DECISIONS.md`, `CLAUDE.md` | `docs/DECISIONS.md` (merge) | keep the decision log |

## Path changes to fix (the only real code edits)

1. **Engine export target.** `export_external.py` / callers currently write to the absolute
   `~/projects/Analysis/psx-top30/psx_data/external`. In the monorepo this becomes the relative
   `data/external` (resolve from a repo-root constant, not `~`).
2. **Onboarding reads `companies.json`** from the dashboard's `psx_data/`. Point it at `data/`.
3. **Scratchpad temp dirs** (the `/private/tmp/.../scratchpad/sa` paths in `fetch_sa.py` /
   `assemble_sa.py`) → a repo-local `./.cache/` or `tempfile`.
4. **Dashboard build** reads `psx_data/` and writes `psx_dashboard.html`; repoint to `data/` and
   `dashboard/` output.
5. Replace all `~/projects/...` absolute paths with a single `ROOT = Path(__file__).resolve().parents[N]`
   pattern so it runs identically locally and in GitHub Actions.

## Cutover checklist

- [ ] Copy files per the mapping above.
- [ ] Fix the 5 path issues; add `ROOT`-relative resolution everywhere.
- [ ] `pip install -r requirements.txt` + `playwright install chromium` in a clean venv → green.
- [ ] Run `scripts/daily_run.py` locally once → confirm snapshots update, a new entry onboards,
      dashboard rebuilds, looks identical to today's output.
- [ ] Wrap each source fetch in the `fetchers/` fallback loop; verify each ladder (DPS direct,
      stockanalysis Playwright, Investing fresh-browser, sarmaaya Playwright).
- [ ] Add `.github/workflows/daily.yml`; test via `workflow_dispatch` (manual trigger) before relying
      on the 16:00 UTC cron.
- [ ] Verify GitHub Pages deploy renders the dashboard.
- [ ] Confirm the engine's 62 onboarded stocks all export and render in the monorepo build.
- [ ] Only then: archive the two old repos (don't delete — tag a final commit).

## Gotchas carried over (full detail in `docs/DECISIONS.md`)

- Investing: search API only works from the homepage; Cloudflare challenges sequential loads → fresh
  browser per page.
- stockanalysis: tool-result size limits don't apply in Playwright (we read the DOM directly now).
- Dividend `yield`/`payout_ratio` are stored as **fractions** (export multiplies by 100).
- ROE/ROA/gross_margin are **computed from raw lines**, not taken from any site.
- FY-end is inferred from filing dates (defaults December) — affects only the cosmetic derived
  per-year P/E for non-December fiscal years.
- `industry_pe` is a **sector average**, so an imperfect slug match still yields the right value as
  long as the sector matches.
