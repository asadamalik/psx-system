# PSX Volume Monitor

Tracks the **daily top-30 volume leaders** on the Pakistan Stock Exchange, flags **new entries**
(stocks that weren't in yesterday's top-30 — the ones worth a look), and for each interesting stock
pulls its **technicals and fundamentals** from PSX DPS, stockanalysis.com, Investing.com and
sarmaaya.pk, scores it, and shows everything in a **dashboard** with a watchlist (price alerts) and
demo trading.

**New here? Read [`docs/PROCESS.md`](docs/PROCESS.md)** — it explains the whole system end-to-end in
plain language. Then [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the technical design.

## Layout

```
fetchers/   robust data fetchers (try every method until one works)
engine/     scoring + per-stock data store (engine/stocks/<SYM>/)
dashboard/  static-site generator (published to GitHub Pages)
data/       shared state (snapshots, companies, external exports)
scripts/    orchestrators — daily_run.py (the nightly job), onboard.py
docs/       PROCESS, ARCHITECTURE, DECISIONS, MIGRATION
.github/    daily.yml — runs at 9 PM PKT (16:00 UTC), Mon–Fri
```

## Run it

```bash
pip install -r requirements.txt
python -m playwright install chromium

python scripts/daily_run.py        # the full nightly job (top-30 → onboard new → score → build)
python scripts/onboard.py <SYM>    # fully onboard one stock
python scripts/dev_server.py       # local dashboard preview
```

## Automation

The nightly run is a GitHub Actions cron (`.github/workflows/daily.yml`): every weekday at 16:00 UTC it
fetches the top-30, onboards new entries, rescoring everything, commits the updated `data/`, and
deploys the dashboard to GitHub Pages. Trigger it manually from the Actions tab (**Run workflow**)
to test. State lives in the repo — no external database.

> Decision-support tool, **not financial advice**. All scoring is mechanical and transparent.
