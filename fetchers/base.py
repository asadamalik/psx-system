"""Robust fetching foundation — "try every possible way in a loop".

Every data source is a Fetcher with an ordered list of `methods` (cheapest/most-reliable first).
`get()` tries each method until one returns data that passes `is_valid()`. A method that raises or
returns invalid data is logged and skipped, and the next method is tried. Only after EVERY method
fails does `get()` raise. This is what keeps the unattended nightly job working when a site changes
its bot protection.

Subclass per source (see dps.py, stockanalysis.py, investing.py, sarmaaya.py). The concrete fetch
logic from this session's scripts (fetch_sa.py, fetch_industry_pe.py, fetch_insider.py) gets ported
into these methods during migration — see docs/MIGRATION.md.
"""
from __future__ import annotations
import time
import logging

log = logging.getLogger("fetchers")


class AllMethodsFailed(Exception):
    pass


class Fetcher:
    """Base class. A subclass defines `methods` (a list of bound callables, tried in order) and
    optionally overrides `is_valid()` and the backoff schedule."""

    name = "fetcher"
    backoff_seconds = (0, 2, 5)   # wait before attempt i (clamped to the last value)

    def methods(self, *args, **kwargs):
        """Return an ordered list of zero-arg callables for this request. Override per source."""
        raise NotImplementedError

    def is_valid(self, data) -> bool:
        """Source-specific check that the fetched data is real and usable (not an empty page, a
        Cloudflare challenge, a 'successful but wrong' response, or out-of-range garbage). Override."""
        return data is not None

    def get(self, *args, **kwargs):
        attempts = self.methods(*args, **kwargs)
        last_err = None
        for i, method in enumerate(attempts):
            wait = self.backoff_seconds[min(i, len(self.backoff_seconds) - 1)]
            if wait:
                time.sleep(wait)
            label = getattr(method, "__name__", f"method{i}")
            try:
                data = method()
                if self.is_valid(data):
                    log.info("%s: got data via %s", self.name, label)
                    return data
                log.warning("%s: %s returned invalid data, falling back", self.name, label)
            except Exception as e:  # noqa: BLE001 — we intentionally try the next method
                last_err = e
                log.warning("%s: %s failed (%s), falling back", self.name, label, str(e)[:120])
        raise AllMethodsFailed(f"{self.name}: all {len(attempts)} methods failed (last: {last_err})")


# --- shared method building blocks (used by the per-source ladders) ----------------------------

def http_json(url, headers=None, timeout=30):
    """Plain HTTP GET → JSON. The first rung for sources that serve data directly (PSX DPS)."""
    import json
    import urllib.request
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def playwright_eval(url, js, *, wait_ms=4000, fresh=False, ua=None, timeout=40000):
    """Load a JS-rendered page in headless chromium and run `js` (a page-context function string),
    returning its result. `fresh=True` launches a brand-new browser (needed for Investing, whose
    Cloudflare challenges sequential automated loads in the same session). The rung for stockanalysis,
    Investing and sarmaaya."""
    from playwright.sync_api import sync_playwright
    ua = ua or ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            page = b.new_context(user_agent=ua, locale="en-US").new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            page.wait_for_timeout(wait_ms)
            return page.evaluate(js)
        finally:
            b.close()
