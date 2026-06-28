"""batch_onboard.py — automated bulk onboarding driver for the Shariah-compliant universe.
For each symbol: fetch_sa (stockanalysis) -> assemble_sa (engine files) -> fetch_insider
(best-effort) -> run.py -> export_external.py. Robust: logs per-stock outcome, continues on
failure. Run from the engine dir with its venv. Re-runnable (idempotent)."""
import sys, subprocess, json, os, time

ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)                          # monorepo root
PY = os.path.join(ROOT, ".venv/bin/python")             # the monorepo venv
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
    return len(b.get("annual", {}).get("income", {}).get("revenue", {})) >= 2

def onboard(sym):
    rc, _ = run(["fetch_sa.py", sym], 90)
    if rc != 0 or not has_annual(sym):
        return "NO_DATA"
    rc, out = run(["assemble_sa.py", sym], 60)
    if rc != 0:
        return "ASSEMBLE_FAIL: " + out.strip().splitlines()[-1][:80]
    run(["fetch_insider.py", sym], 60)              # best-effort
    rc, out = run(["run.py", sym], 120)
    if rc != 0:
        return "RUN_FAIL: " + out.strip().splitlines()[-1][:80]
    rc, _ = run(["export_external.py", sym, "--out", DASH_EXT], 60)
    # pull the score line for the log
    for ln in out.splitlines():
        if "scores" in ln:
            return "OK " + ln.split(":", 1)[1].strip()[:70]
    return "OK"

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
