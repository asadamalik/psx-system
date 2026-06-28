#!/usr/bin/env python3
"""dev_server.py — local one-click insider refresh for the PSX dashboard.

Runs ONLY on your machine (binds 127.0.0.1). It serves the baked dashboard AND
exposes POST /api/refresh-insider?sym=<SYM>, which the "↻ Refresh insider" button
on the stock detail page calls. On the live GitHub Pages site there is no backend,
so the button gracefully falls back to the manual kickoff (opens sarmaaya + copies
a paste-prompt). See DECISIONS.md "Refresh button".

The refresh chain (all local):
  1. engine  fetch_insider.py <SYM>           -> rewrites stocks/<SYM>/overview/insider.json (Playwright)
  2. engine  export_external.py <SYM> --out ./psx_data/external
  3. dash    dev_rebuild.py                    -> re-bakes psx_dashboard.html (cached embed, ~1s)
Then the button reloads the page and the fresh filings show.

Run (dashboard venv):  .venv/bin/python dev_server.py   then open http://127.0.0.1:8079/
Override engine location with ENGINE_DIR=/path/to/stock-agent-claude.
"""
import json, os, re, subprocess, sys, urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PSX_DEV_PORT", "8079"))
ENGINE_DIR = os.environ.get(
    "ENGINE_DIR", os.path.expanduser("~/projects/stock-agent-claude/stock-agent-claude"))
ENGINE_PY = os.path.join(ENGINE_DIR, ".venv", "bin", "python")
DASH_PY = os.path.join(HERE, ".venv", "bin", "python")
EXTERNAL_DIR = os.path.join(HERE, "psx_data", "external")
SYM_RE = re.compile(r"^[A-Z0-9]{1,12}$")  # guards the subprocess argv (defense-in-depth)


def _run(cmd, cwd):
    """Run a child process, raising with captured output on failure."""
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=180)
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
        if parsed.path != "/api/refresh-insider":
            self._json(404, {"ok": False, "error": "unknown endpoint"})
            return
        sym = urllib.parse.parse_qs(parsed.query).get("sym", [""])[0]
        try:
            result = refresh_insider(sym)
            print(f"[refresh-insider] {result}")
            self._json(200, result)
        except Exception as e:  # noqa: BLE001
            print(f"[refresh-insider] FAILED for {sym!r}: {e}", file=sys.stderr)
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
    print("  POST /api/refresh-insider?sym=<SYM> rebuilds insider data on demand.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
