"""daily_run.py — THE nightly job (9 PM PKT weekdays, via .github/workflows/daily.yml).

Composes the proven pieces into the daily loop:
  1. Live PSX DPS market-watch scrape -> today's top-30 + EOD OHLCV, append snapshot, build dashboard
     (this is dashboard/psx_auto.main()).
  2. Diff the last two snapshots -> NEW ENTRIES.
  3. Auto-onboard any new entry not yet in engine/stocks (engine/batch_onboard.py) — isolated;
     one failure never aborts the run.
  4. If anything onboarded, rebuild so the new stocks appear; publish index.html for Pages.

Run:  python scripts/daily_run.py            (full run, live scrape)
      python scripts/daily_run.py --no-scrape (skip the live scrape; just detect/onboard/build)
"""
from __future__ import annotations
import sys, subprocess, shutil, argparse, logging
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard"))
import psx_auto, dev_rebuild  # noqa: E402  (dashboard modules)

log = logging.getLogger("daily_run")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
PY = str(ROOT / ".venv" / "bin" / "python")
STOCKS = ROOT / "engine" / "stocks"


def top_symbols(snap) -> set[str]:
    return {r["symbol"] for r in (snap or {}).get("top", [])}


def main(scrape: bool = True) -> None:
    # 1. live scrape + snapshot + OHLCV + dashboard build (the dashboard daily job)
    if scrape:
        try:
            psx_auto.main()
        except Exception as e:  # noqa: BLE001 — core must stay green
            log.warning("market-watch scrape failed (%s); continuing with existing snapshots", str(e)[:120])

    # 2. new-entry detection from the last two snapshots
    snaps = psx_auto.load_snaps()
    today, prev = (snaps[-1] if snaps else None), (snaps[-2] if len(snaps) >= 2 else None)
    new_entries = sorted(top_symbols(today) - top_symbols(prev))
    todo = [s for s in new_entries if not (STOCKS / s).exists()]
    log.info("new entries: %s | to onboard: %s", new_entries or "none", todo or "none")

    # 3. auto-onboard new entries (isolated; batch_onboard logs + continues per stock)
    if todo:
        subprocess.run([PY, str(ROOT / "engine" / "batch_onboard.py"), *todo],
                       cwd=str(ROOT / "engine"))
        # 4. rebuild so the freshly onboarded stocks appear in the dashboard
        dev_rebuild.rebuild(fresh=False)

    # publish: Pages serves index.html; the build writes psx_dashboard.html
    out = Path(psx_auto.OUT)
    if out.exists():
        shutil.copy(out, ROOT / "dashboard" / "index.html")
    log.info("daily run complete")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-scrape", action="store_true", help="skip the live market-watch scrape")
    a = ap.parse_args()
    main(scrape=not a.no_scrape)
