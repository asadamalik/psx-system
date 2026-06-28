"""
relative_strength.py
---------------------
Relative strength of a stock vs the KSE100 index.

Aligns the stock's daily close with stocks/_market/kse100.csv on common
trading dates, then over each lookback window computes:

    outperformance = stock_return - index_return

Positive = the stock beat the market over that window (leadership).
Anchored on the LAST COMMON date, so it self-adjusts to whatever index
history is available (the index feed can lag the stock feed).
"""

from __future__ import annotations
import pandas as pd

from .layout import StockPaths, STOCKS_DIR
from . import technical as tech

INDEX_CSV = STOCKS_DIR / "_market" / "kse100.csv"
WINDOWS = {"1w": 5, "2w": 10, "1m": 21, "3m": 63}


def _load_index():
    if not INDEX_CSV.exists():
        return None
    return tech.load_historical(INDEX_CSV)["close"]


def relative_strength(symbol: str) -> dict | None:
    idx = _load_index()
    if idx is None:
        return None
    p = StockPaths(symbol)
    if not p.historical_csv.exists():
        return None
    stock = tech.load_historical(p.historical_csv)["close"]

    df = pd.concat({"stock": stock, "index": idx}, axis=1).dropna()
    if len(df) < 6:
        return None
    df = df.sort_index()
    last_date = df.index[-1]

    out = {"as_of": str(last_date.date()), "common_days": int(len(df)), "windows": {}}
    for name, n in WINDOWS.items():
        if len(df) <= n:
            continue
        s0, s1 = df["stock"].iloc[-(n + 1)], df["stock"].iloc[-1]
        i0, i1 = df["index"].iloc[-(n + 1)], df["index"].iloc[-1]
        s_ret = s1 / s0 - 1
        i_ret = i1 / i0 - 1
        out["windows"][name] = {
            "stock_return": round(s_ret, 4),
            "index_return": round(i_ret, 4),
            "outperformance": round(s_ret - i_ret, 4),
        }

    # rating from the available windows (favor 1m/3m, fall back to shorter)
    perfs = [w["outperformance"] for w in out["windows"].values()]
    avg = sum(perfs) / len(perfs) if perfs else None
    if avg is None:
        rating = "n/a"
    elif avg >= 0.03:
        rating = "Market Leader"
    elif avg >= 0.0:
        rating = "Outperforming"
    elif avg >= -0.03:
        rating = "Inline"
    else:
        rating = "Lagging"
    out["avg_outperformance"] = round(avg, 4) if avg is not None else None
    out["rating"] = rating
    return out
