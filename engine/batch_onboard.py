"""batch_onboard.py — automated bulk onboarding driver for the Shariah-compliant universe.
For each symbol: fetch_sa (stockanalysis) -> assemble_sa (engine files) -> fetch_insider
(best-effort) -> run.py -> export_external.py. Robust: logs per-stock outcome, continues on
failure. Run from the engine dir with its venv. Re-runnable (idempotent)."""
import sys, subprocess, json, os, time

ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)                          # monorepo root
# Prefer the monorepo venv locally; fall back to the current interpreter on CI
# (GitHub Actions runs system Python with deps installed and has no .venv).
_venv_py = os.path.join(ROOT, ".venv", "bin", "python")
PY = _venv_py if os.path.exists(_venv_py) else sys.executable
DASH_EXT = os.path.join(ROOT, "data", "external")
SA_DIR = os.path.join(ROOT, ".cache", "sa")

def run(args, timeout):
    try:
        r = subprocess.run([PY] + args, cwd=ENGINE, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr)
    except subprocess.TimeoutExpired:
        return -9, "TIMEOUT"

def has_annual(sym):
    fp = os.path.join(SA_DIR, f"sa_{sym}.json")
    if not os.path.exists(fp):
        return False
    b = json.load(open(fp))
    inc = b.get("annual", {}).get("income", {})
    # Insurers / REITs / takaful have no top-line "revenue" row on stockanalysis
    # (their income statement leads with net_income / eps). Accept >=2 yrs of any
    # of these as a valid annual series so they aren't false-flagged NO_DATA.
    return (len(inc.get("revenue", {})) >= 2
            or len(inc.get("net_income", {})) >= 2
            or len(inc.get("eps", {})) >= 2)

def onboard(sym):
    src = "sa"
    rc, _ = run(["fetch_sa.py", sym], 90)
    if rc != 0 or not has_annual(sym):
        # Fallback for illiquid small caps with NO stockanalysis financials page:
        # synthesize an income-only blob from DPS (data/companies.json). See DECISIONS.md
        # "Data-source priority + FALLBACK ORDER".
        rc2, _ = run(["make_dps_blob.py", sym], 30)
        if rc2 != 0 or not has_annual(sym):
            return "NO_DATA"
        src = "dps"
    rc, out = run(["assemble_sa.py", sym], 60)
    if rc != 0:
        return "ASSEMBLE_FAIL: " + out.strip().splitlines()[-1][:80]
    run(["fetch_insider.py", sym], 60)              # best-effort (sarmaaya)
    if src == "dps":
        run(["fetch_industry_pe.py", sym], 90)      # best-effort (Investing -ratios, still public)
    rc, out = run(["run.py", sym], 120)
    if rc != 0:
        return "RUN_FAIL: " + out.strip().splitlines()[-1][:80]
    run(["export_external.py", sym, "--out", DASH_EXT], 60)
    tag = "OK[dps] " if src == "dps" else "OK "
    # pull the score line for the log
    for ln in out.splitlines():
        if "scores" in ln:
            return tag + ln.split(":", 1)[1].strip()[:70]
    return tag.strip()

def main():
    syms = sys.argv[1:]
    results = {}
    for i, s in enumerate(syms, 1):
        t0 = time.time()
        r = onboard(s)
        results[s] = r
        print(f"[{i}/{len(syms)}] {s:10} {r}  ({time.time()-t0:.0f}s)", flush=True)
    ok = sum(1 for v in results.values() if v.startswith("OK"))
    print(f"\nDONE: {ok}/{len(syms)} onboarded. Failures:")
    for s, v in results.items():
        if not v.startswith("OK"):
            print(f"  {s}: {v}")

if __name__ == "__main__":
    main()
