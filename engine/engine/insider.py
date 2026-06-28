"""
insider.py
----------
Insider (director/sponsor) transaction sentiment from a stock's
overview/insider.json. Net buying vs selling is a confidence signal:
sustained insider buying often precedes strength; heavy selling is a caution.
"""

from __future__ import annotations
import json

from .layout import StockPaths


def load(symbol: str) -> dict | None:
    path = StockPaths(symbol).overview / "insider.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def sentiment(symbol: str) -> dict | None:
    data = load(symbol)
    if not data:
        return None
    txns = data.get("transactions", []) or []
    buy_sh = sell_sh = buy_val = sell_val = 0.0
    n_buy = n_sell = 0
    for t in txns:
        action = str(t.get("action", "")).lower()
        sh = _num(t.get("shares"))
        val = _num(t.get("value"))
        if "buy" in action or "purchase" in action or "acqui" in action:
            buy_sh += sh; buy_val += val; n_buy += 1
        elif "sell" in action or "dispos" in action:
            sell_sh += sh; sell_val += val; n_sell += 1

    net_sh = buy_sh - sell_sh
    # Headline direction follows the transaction-COUNT majority so the label never
    # contradicts the "(N buys / M sells)" shown alongside it. Share/value totals are
    # kept as detail (a single large filing can dominate by value — surfaced via
    # value_note rather than silently flipping the headline).
    net_n = n_buy - n_sell
    total_n = n_buy + n_sell
    ratio = (net_n / total_n) if total_n else None  # +1 all buys, -1 all sells (by count)

    if ratio is None:
        label = "No recent insider activity"
    elif ratio >= 0.4:
        label = "Strong insider buying"
    elif ratio > 0:
        label = "Net insider buying"
    elif ratio == 0:
        label = "Balanced insider activity"
    elif ratio > -0.4:
        label = "Net insider selling"
    else:
        label = "Heavy insider selling"

    # note when net share VOLUME disagrees with the count-based headline
    value_note = None
    if total_n and net_n != 0 and net_sh != 0 and (net_sh > 0) != (net_n > 0):
        value_note = ("by share volume the balance is the other way "
                      f"(net {net_sh:+,.0f} shares) — a few large filings dominate")

    return {
        "n_transactions": len(txns),
        "buys": n_buy, "sells": n_sell,
        "buy_shares": buy_sh, "sell_shares": sell_sh,
        "buy_value": buy_val, "sell_value": sell_val,
        "net_shares": net_sh,
        "net_ratio": round(ratio, 2) if ratio is not None else None,
        "sentiment": label,
        "value_note": value_note,
        "transactions": txns[:8],
        "source": data.get("source"),
        "as_of": data.get("as_of"),
    }
