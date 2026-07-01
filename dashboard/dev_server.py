#!/usr/bin/env python3
"""dev_server.py — local one-click refresh sidecar for the PSX dashboard.

Runs ONLY on your machine (binds 127.0.0.1). Serves the baked dashboard AND exposes two
POST endpoints that the stock detail page's buttons call. On the live GitHub Pages site
there is no backend, so the buttons gracefully fall back (see the JS refresh functions).

  • POST /api/refresh-insider?sym=<SYM>  ("↻ Refresh insider"):
      engine fetch_insider.py -> export_external.py -> dev_rebuild.py
  • POST /api/refresh-stock?sym=<SYM>    ("↻ Refresh data" — fundamentals + technicals):
      engine batch_onboard.py <SYM> (stockanalysis, or DPS fallback; + insider + industry P/E
      + score + export) -> dev_rebuild.py

Both re-bake psx_dashboard.html (cached embed, ~1s) and the button reloads onto the same stock.
Paths are monorepo-relative: engine at ../engine, exports to ../data/external, one root .venv.

Run:  ./.venv/bin/python dashboard/dev_server.py   then open http://127.0.0.1:8079/
Override engine location with ENGINE_DIR=/path/to/engine.
"""
import json, os, re, subprocess, sys, urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))        # dashboard/
ROOT = os.path.dirname(HERE)                             # monorepo root
PORT = int(os.environ.get("PSX_DEV_PORT", "8079"))
ENGINE_DIR = os.environ.get("ENGINE_DIR", os.path.join(ROOT, "engine"))
# One self-contained monorepo venv (was two per-repo venvs); fall back to the current
# interpreter if it's missing so the sidecar still works from any Python.
_VENV_PY = os.path.join(ROOT, ".venv", "bin", "python")
ENGINE_PY = DASH_PY = _VENV_PY if os.path.exists(_VENV_PY) else sys.executable
EXTERNAL_DIR = os.path.join(ROOT, "data", "external")    # monorepo shared state (was psx_data/)
SYM_RE = re.compile(r"^[A-Z0-9]{1,12}$")  # guards the subprocess argv (defense-in-depth)


def _run(cmd, cwd, timeout=180):
    """Run a child process, raising with captured output on failure."""
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"{cmd[1] if len(cmd) > 1 else cmd[0]} failed "
                           f"(exit {p.returncode}): {(p.stderr or p.stdout).strip()[:400]}")
    return p.stdout


def refresh_insider(sym: str) -> dict:
    sym = sym.upper()
    if not SYM_RE.match(sym):
        raise ValueError(f"bad symbol {sym!r}")
    _run([ENGINE_PY, "fetch_insider.py", sym], cwd=ENGINE_DIR)
    _run([ENGINE_PY, "export_external.py", sym, "--out", EXTERNAL_DIR], cwd=ENGINE_DIR)
    _run([DASH_PY, "dev_rebuild.py"], cwd=HERE)
    # report count + as_of straight from the freshly written engine file
    insider_path = os.path.join(ENGINE_DIR, "stocks", sym, "overview", "insider.json")
    data = json.load(open(insider_path)) if os.path.exists(insider_path) else {}
    txns = data.get("transactions", [])
    return {"ok": True, "sym": sym, "count": len(txns), "as_of": data.get("as_of")}


def refresh_stock(sym: str) -> dict:
    """Full on-demand onboard/refresh of a stock's fundamentals + technicals.

    batch_onboard.py is robust: it tries stockanalysis, falls back to a DPS income-only
    blob for illiquid names, fetches insider + industry P/E, scores, and exports. Then we
    re-bake the dashboard so the stock's detail page fills in. Slow (headless scraping),
    so a generous timeout.
    """
    sym = sym.upper()
    if not SYM_RE.match(sym):
        raise ValueError(f"bad symbol {sym!r}")
    out = _run([ENGINE_PY, "batch_onboard.py", sym], cwd=ENGINE_DIR, timeout=420)
    _run([DASH_PY, "dev_rebuild.py"], cwd=HERE)
    # batch_onboard prints "[1/1] SYM   OK ..." / "OK[dps] ..." / "NO_DATA" / "..._FAIL"
    status = next((ln.strip() for ln in out.splitlines()
                   if ln.lstrip().startswith("[") and sym in ln), "")
    onboarded = os.path.exists(os.path.join(ENGINE_DIR, "stocks", sym, "analysis"))
    return {"ok": ("OK" in status) or onboarded, "sym": sym, "status": status or "done"}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=HERE, **kw)

    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        routes = {"/api/refresh-insider": refresh_insider,
                  "/api/refresh-stock": refresh_stock}
        fn = routes.get(parsed.path)
        if fn is None:
            self._json(404, {"ok": False, "error": "unknown endpoint"})
            return
        sym = urllib.parse.parse_qs(parsed.query).get("sym", [""])[0]
        try:
            result = fn(sym)
            print(f"[{parsed.path}] {result}")
            self._json(200, result)
        except Exception as e:  # noqa: BLE001
            print(f"[{parsed.path}] FAILED for {sym!r}: {e}", file=sys.stderr)
            self._json(500, {"ok": False, "sym": sym, "error": str(e)[:500]})

    def do_GET(self):
        # serve the baked dashboard at "/"
        if urllib.parse.urlparse(self.path).path == "/":
            self.path = "/psx_dashboard.html"
        try:
            super().do_GET()
        except (BrokenPipeError, ConnectionResetError):
            pass  # client closed early (e.g. reload mid-transfer) — not an error

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}")


def main():
    for label, path in (("engine python", ENGINE_PY), ("dashboard python", DASH_PY)):
        if not os.path.exists(path):
            print(f"WARNING: {label} not found at {path} — refresh will fail until fixed.",
                  file=sys.stderr)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"PSX dev server -> http://127.0.0.1:{PORT}/  (Ctrl-C to stop)")
    print(f"  engine: {ENGINE_DIR}")
    print("  POST /api/refresh-insider?sym=<SYM>  -> refresh insider filings")
    print("  POST /api/refresh-stock?sym=<SYM>    -> onboard/refresh fundamentals + technicals")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
