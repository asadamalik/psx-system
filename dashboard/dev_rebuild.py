#!/usr/bin/env python3
"""Fast UI rebuild for the PSX dashboard WITHOUT live market-watch scraping.

Mirrors psx_auto.py's post-compute steps (external bridge + OHLC) so the template
renders against the real pipeline, but skips the live PSX scrape. Caches the
expensive compute_embed() output to psx_data/.embed_cache.json so template tweaks
and insider refreshes re-render in ~1s. Pass --fresh to recompute the cache.

Used both standalone (template tweaks) and by dev_server.py after an insider fetch.
MUST run under the dashboard venv (needs pandas/bs4): .venv/bin/python dev_rebuild.py
"""
import os, sys, json, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import psx_auto, build_lib, external_fundamentals, ohlc_store  # noqa: E402

STATE = psx_auto.STATE
CACHE = os.path.join(STATE, ".embed_cache.json")


def rebuild(fresh: bool = False) -> dict:
    snaps = psx_auto.load_snaps()
    if fresh or not os.path.exists(CACHE):
        det = psx_auto.snaps_to_det(snaps)
        embed = build_lib.compute_embed(det, fetch_charts=True)
        cpath = os.path.join(STATE, "companies.json")
        cache = json.load(open(cpath)) if os.path.exists(cpath) else {}
        cache.update(embed.get("companies", {}) or {})
        embed["companies"] = cache
        json.dump(embed, open(CACHE, "w"))
        print("cached compute_embed ->", CACHE)
    else:
        embed = json.load(open(CACHE))
        print("loaded cached embed (use --fresh to recompute)")

    for key in ("sectors", "shariah"):
        p = os.path.join(STATE, key + ".json")
        embed[key] = json.load(open(p)) if os.path.exists(p) else {}

    # engine bridge + OHLC (same as psx_auto, minus the live rows)
    embed["external"] = external_fundamentals.load(STATE)
    ohlc = ohlc_store.load(STATE)
    ohlc_store.backfill_from_snapshots(ohlc, snaps)
    ohlc_store.save(STATE, ohlc)
    ohlc_store.attach_external_charts(embed.get("charts", {}), embed.get("external", {}))
    ohlc_store.merge_into_charts(embed.get("charts", {}), ohlc, embed.get("external", {}))

    embed["built_at"] = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC")
    build_lib.render_html(psx_auto.TEMPLATE, embed, psx_auto.OUT)
    print("rendered ->", psx_auto.OUT, "| external symbols:", ", ".join(sorted(embed["external"])))
    return embed


if __name__ == "__main__":
    rebuild(fresh="--fresh" in sys.argv)
