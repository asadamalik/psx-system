"""refresh_history.py — rebuild a stock's FULL real-OHLCV history from stockanalysis.com.

stockanalysis exposes complete daily OHLCV (real High/Low + Volume, split-adjusted) via a
plain HTTP API — far more than the ~50 rendered bars we scraped before, and with no
synthesized High/Low. This overwrites engine/stocks/<SYM>/technical/historical.csv with the
full series (newest-first), then (unless --csv-only) re-runs run.py + export_external.py so
the scores, chart and 52-week range pick up the deeper history.

API: https://stockanalysis.com/api/symbol/a/PSX-<SYM>/history?range=10Y
     -> {"status":..., "data":[{"t":"YYYY-MM-DD","o","h","l","c","a","v","ch"}, ... newest first]}

Usage:
  python refresh_history.py <SYM...>              # rewrite history + re-run + re-export
  python refresh_history.py <SYM...> --csv-only   # just rewrite historical.csv (used by onboard)
"""
import sys, os, json, urllib.request, subprocess

ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)
_venv_py = os.path.join(ROOT, ".venv", "bin", "python")
PY = _venv_py if os.path.exists(_venv_py) else sys.executable
DASH_EXT = os.path.join(ROOT, "data", "external")
API = "https://stockanalysis.com/api/symbol/a/PSX-{sym}/history?range=10Y"
UA = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")}
MIN_BARS = 2  # a stock with fewer usable bars isn't worth overwriting good data


def fetch_history(sym):
    """Return the newest-first list of daily OHLCV dicts, or [] if unavailable."""
    req = urllib.request.Request(API.format(sym=sym.upper()), headers=UA)
    try:
        payload = json.load(urllib.request.urlopen(req, timeout=30))
    except Exception:
        return []
    rows = payload.get("data")
    return rows if isinstance(rows, list) else []


def write_csv(sym, rows):
    """Write historical.csv (newest-first). Returns bar count written."""
    out = ["date,close,open,high,low,volume,change_pct"]
    for r in rows:
        try:
            c, o, h, l = r["c"], r["o"], r["h"], r["l"]
            v = int(round(r.get("v") or 0))
        except (KeyError, TypeError):
            continue
        ch = r.get("ch")
        chs = (f"{'+' if ch >= 0 else ''}{ch:.2f}%") if isinstance(ch, (int, float)) else ""
        out.append(f'{r["t"]},{c},{o},{h},{l},{v},{chs}')
    path = os.path.join(ENGINE, "stocks", sym.upper(), "technical", "historical.csv")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(out) + "\n")
    return len(out) - 1


def refresh_one(sym, csv_only=False):
    sym = sym.upper()
    rows = fetch_history(sym)
    if len(rows) < MIN_BARS:
        return f"NO_HISTORY (rows={len(rows)})"
    n = write_csv(sym, rows)
    if n < MIN_BARS:
        return f"NO_HISTORY (usable={n})"
    if csv_only:
        return f"OK {n} bars"
    r = subprocess.run([PY, "run.py", sym], cwd=ENGINE, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        return f"RUN_FAIL: {(r.stderr or r.stdout).strip().splitlines()[-1][:80]}"
    subprocess.run([PY, "export_external.py", sym, "--out", DASH_EXT], cwd=ENGINE,
                   capture_output=True, text=True, timeout=90)
    return f"OK {n} bars"


def main(argv):
    csv_only = "--csv-only" in argv
    syms = [a for a in argv if not a.startswith("--")]
    for i, s in enumerate(syms, 1):
        print(f"[{i}/{len(syms)}] {s.upper():10} {refresh_one(s, csv_only)}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
