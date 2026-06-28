# PSX Volume Monitor — How the System Works (start here)

This document explains the whole system end-to-end for someone seeing it for the first time.
No code knowledge required to read it.

---

## 1. The core idea (why this exists)

Every trading day, the Pakistan Stock Exchange (PSX) has stocks that trade unusually high
**volume**. A stock suddenly appearing among the day's **top-30 by volume** — when it wasn't there
yesterday — is a signal that something is happening (news, accumulation, a breakout). Those **new
entries** are the stocks we care about most.

So the system does three things, in order:

1. **Track** the daily top-30 volume leaders from PSX.
2. **Detect new entries** — stocks in today's top-30 that were *not* in yesterday's.
3. **Analyze** each interesting stock — pull its technicals and fundamentals from several websites,
   score it, and show whether it looks like a buy.

Everything is shown in a **dashboard** (a website). The user can also keep a **watchlist** with price
alerts and run **paper (demo) trades** with stop-loss / take-profit alerts.

---

## 2. The daily run (what happens automatically at 9 PM Pakistan time, Mon–Fri)

> Runtime: **GitHub Actions** on a cron schedule (9 PM PKT = 16:00 UTC, weekdays). See
> `.github/workflows/daily.yml`. The whole run is one orchestrator: `scripts/daily_run.py`.

**Step 1 — Fetch today's top-30 volume leaders (from PSX DPS).**
The market-watch page on `dps.psx.com.pk` lists every stock with its day's Open/High/Low/Close and
Volume. We sort by volume and take the **top 30**. (Source: PSX DPS — the authoritative exchange feed.)

**Step 2 — Save today's snapshot and detect new entries.**
Today's top-30 is appended to the running history (`data/snapshots.json`). We compare today's 30 to
yesterday's 30. Any symbol present today but not yesterday is a **NEW ENTRY** — flagged in the
dashboard with a "new" badge.

**Step 3 — Update price history (OHLCV) for the tracked stocks.**
For every stock we follow, we fetch its latest **EOD Open/High/Low/Close/Volume from PSX DPS** and
append it to that stock's price history. This is the daily incremental update — DPS is the source of
truth for daily prices because it's the exchange itself.

**Step 4 — Auto-onboard the new entries (first-time deep fetch).**
A brand-new stock has no data yet, so the job runs the **full onboarding** for it (Section 3). This is
the heavy step (it scrapes financial websites with a headless browser). After onboarding, the stock
has full history, financials, and a score.

**Step 5 — Score and export.**
The engine recomputes each stock's technical + fundamental score and exports a single JSON per stock
for the dashboard to read.

**Step 6 — Rebuild and publish the dashboard.**
The static dashboard site is regenerated with the new data and published (GitHub Pages). Watchlist
alerts and demo-trade alerts are evaluated against the new prices.

---

## 3. Onboarding one stock (how we get its technicals & fundamentals)

This runs the **first time** we see a stock, and rarely again (fundamentals only change ~quarterly).
It pulls from **four sources**, each authoritative for different things:

| Source | What we take from it | How we fetch it |
|---|---|---|
| **PSX DPS** (`dps.psx.com.pk`) | Daily volume, full EOD price history (Open/Close/Volume), **unconsolidated** annual financials (the "standalone" numbers), shares outstanding, free-float % | Direct HTTP (works with a normal request) |
| **stockanalysis.com** | **Consolidated** financials — full annual + quarterly income / balance sheet / cash flow, P/E, P/B, EPS, market cap, dividends, and ~50 bars of real intraday High/Low | Headless browser (the page renders with JavaScript) |
| **Investing.com** | **Industry-average P/E** (the "cheaper/pricier than its sector" comparison) — the one thing stockanalysis doesn't have | Headless browser (search to find the page, then read it) |
| **sarmaaya.pk** | **Insider transactions** (directors/sponsors buying or selling) | Headless browser |

**Why two sources for financials?** PSX DPS gives the *standalone* (unconsolidated) company numbers;
stockanalysis gives the *group* (consolidated) numbers. We keep **both** and surface the difference
(the "earnings-basis divergence") rather than hiding it — a big gap between standalone and consolidated
is itself a signal.

**The onboarding steps, in order:**
1. **Identify the stock** by its PSX ticker (e.g. `LUCK`). No manual lookups needed — every source is
   keyed by ticker or resolved automatically.
2. **Price history** — DPS gives the full multi-year daily Open/Close/Volume; stockanalysis gives real
   recent High/Low. We combine them: DPS as the base, real High/Low overlaid for recent sessions, and
   synthesized High/Low (from Open/Close) for older bars. This is what powers the **candlestick chart**.
3. **Financials** — consolidated annual + quarterly statements from stockanalysis; unconsolidated annual
   from DPS (for the divergence).
4. **Ratios & valuation** — P/E, P/B from stockanalysis; ROE/ROA/margins computed from the raw
   statement lines (never trust a site's pre-computed ROA); industry P/E from Investing.
5. **Dividends & earnings** — yield, payout, history, next-earnings date from stockanalysis.
6. **Insider activity** — from sarmaaya.
7. **Score it** — the engine combines a **technical score** (from price/volume indicators) and a
   **fundamental score** (from the financials) into one overall rating (Strong Buy → Sell), with a
   risk level. This is mechanical and transparent — it is decision-support, **not financial advice**.
8. **Export** one JSON for the dashboard.

> **Robust fetching (important):** every fetch tries multiple methods in a fallback loop — a plain
> HTTP request first, then a headless browser, then a fresh-browser retry, etc. — until it gets the
> data or exhausts all options. So if one method is blocked (e.g. a site adds bot protection), the
> system automatically falls back to another. See `docs/ARCHITECTURE.md` → "Robust fetching".

---

## 4. The technicals & fundamentals we compute

**Technical analysis** (from the price/volume history, computed in-engine and in the chart):
trend (EMA 20/50/100/200), RSI, MACD, ADX/DMI, Bollinger Bands, ATR, OBV, support/resistance, chart
patterns, and a mechanical **trading plan** (entry zone, stop-loss, targets, risk/reward).

**Fundamental analysis** (from the financials): growth (revenue/EPS), profitability (margins, ROE),
financial strength (debt/equity, current ratio, cash flow), and valuation (P/E vs industry, P/B, PEG,
dividend yield). Quarterly data drives TTM figures and quarter-on-quarter / year-on-year momentum.

These only change when new financials are filed (~quarterly), so they're refreshed occasionally — the
**daily** job mostly just updates prices and detects new volume leaders.

---

## 5. What the dashboard shows

- **Overview** — today's top-30 volume leaders, **new entries** badged, and top gainers/losers over
  1 week / 2 weeks / 1 month.
- **Watchlist** — stocks you're watching, each with a **price alert** ("notify me when LUCK hits 1000")
  and an optional note. When the price crosses the level, you're notified.
- **Demo Trades** — paper trading: add a position (entry price, market or pending order, stop-loss,
  take-profit). When stop-loss or take-profit is hit, you're notified. No real money.
- **Individual stock page** — everything for one stock: the candlestick chart with the trading plan,
  full technical readings, the score, and all the fundamentals (financials, ratios, dividends,
  earnings, insider activity, sector comparison).

---

## 6. One-paragraph summary

Every weekday at 9 PM PKT the system pulls the **top-30 volume leaders from PSX**, flags the **new
entries** (yesterday-absent, today-present), updates everyone's daily prices, deeply **onboards** any
new stock by scraping **DPS + stockanalysis + Investing + sarmaaya** (with automatic fallbacks if a
fetch is blocked), **scores** each stock on technicals and fundamentals, and **rebuilds the dashboard**
where you track volume leaders, keep a watchlist with price alerts, run demo trades, and open a full
analysis page for any stock.
