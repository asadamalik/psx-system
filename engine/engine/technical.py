"""
technical.py
------------
Reads stocks/<SYM>/technical/historical.csv (OHLCV from Investing.com
historical data), computes indicators -> indicators.json, and produces a
technical score with trend + momentum read.

historical.csv columns are auto-detected (Date/Open/High/Low/Close/Volume in
any order/casing). Investing.com 'Price' is treated as Close if Close absent.
"""

from __future__ import annotations
import json
import numpy as np
import pandas as pd

from . import indicators as ind_lib
from . import patterns
from .layout import StockPaths

_ALIASES = {
    "date": ["date", "datetime", "time"],
    "open": ["open"],
    "high": ["high"],
    "low": ["low"],
    "close": ["close", "price", "adj close", "adj_close"],
    "volume": ["volume", "vol", "vol."],
}


def _match(cols, names):
    low = {c.lower().strip(): c for c in cols}
    for n in names:
        if n in low:
            return low[n]
    return None


def _to_num(s):
    return pd.to_numeric(
        s.astype(str).str.replace(",", "", regex=False).str.replace("%", "", regex=False),
        errors="coerce",
    )


def load_historical(csv_path) -> pd.DataFrame:
    raw = pd.read_csv(csv_path)
    cols = {k: _match(raw.columns, v) for k, v in _ALIASES.items()}
    if not cols["date"] or not cols["close"]:
        raise ValueError(f"historical.csv needs Date + Close/Price. Found: {list(raw.columns)}")
    df = pd.DataFrame()
    df["date"] = pd.to_datetime(raw[cols["date"]], errors="coerce", dayfirst=False)
    for k in ("open", "high", "low", "close"):
        src = cols[k] or cols["close"]   # fall back to close if O/H/L missing
        df[k] = _to_num(raw[src])
    if cols["volume"]:
        df["volume"] = _to_num(raw[cols["volume"]])
    df = df.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
    return df.set_index("date")


def _last(df, col):
    if col not in df:
        return None
    s = df[col].dropna()
    return float(s.iloc[-1]) if not s.empty else None


def build_indicators(symbol: str) -> dict:
    """Compute indicators, write indicators.json + historical.json. Returns snapshot dict."""
    p = StockPaths(symbol).ensure()
    if not p.historical_csv.exists():
        raise FileNotFoundError(f"missing {p.historical_csv}")
    ohlc = load_historical(p.historical_csv)
    enriched = ind_lib.compute_all(ohlc)

    win = enriched.tail(252)  # ~1y for 52-week stats

    # weekly / monthly trend (price vs longer-period MA on resampled closes)
    def _trend(resampled, n):
        s = resampled.dropna()
        if len(s) < n:
            return "n/a"
        ma = s.rolling(n).mean().iloc[-1]
        if pd.isna(ma):
            return "n/a"
        return "Up" if s.iloc[-1] > ma else "Down"

    wk = enriched["close"].resample("W").last()
    mo = enriched["close"].resample("ME").last()

    if "volume" in enriched.columns and enriched["volume"].notna().any():
        enriched["obv"] = ind_lib.obv(enriched["close"], enriched["volume"])

    snapshot = {
        "as_of": str(enriched.index[-1].date()),
        "bars": int(len(enriched)),
        "close": _last(enriched, "close"),
        "sma_20": _last(enriched, "sma_20"),
        "sma_50": _last(enriched, "sma_50"),
        "sma_200": _last(enriched, "sma_200"),
        "ema_20": _last(enriched, "ema_20"),
        "ema_50": _last(enriched, "ema_50"),
        "ema_100": _last(enriched, "ema_100"),
        "ema_200": _last(enriched, "ema_200"),
        "obv": _last(enriched, "obv"),
        "weekly_trend": _trend(wk, 10),
        "monthly_trend": _trend(mo, 6),
        "support_resistance": patterns.support_resistance(enriched),
        "rsi_14": _last(enriched, "rsi_14"),
        "macd": _last(enriched, "macd"),
        "macd_signal": _last(enriched, "macd_signal"),
        "macd_hist": _last(enriched, "macd_hist"),
        "adx_14": _last(enriched, "adx"),
        "plus_di": _last(enriched, "plus_di"),
        "minus_di": _last(enriched, "minus_di"),
        "atr_14": _last(enriched, "atr_14"),
        "bb_upper": _last(enriched, "bb_upper"),
        "bb_lower": _last(enriched, "bb_lower"),
        "week52_high": float(win["high"].max()) if "high" in win else None,
        "week52_low": float(win["low"].min()) if "low" in win else None,
        "rsi_divergence": patterns.detect_rsi_divergence(enriched["close"], enriched["rsi_14"]),
        "patterns": patterns.detect_patterns(enriched),
    }

    # persist
    with open(p.indicators_json, "w") as f:
        json.dump(snapshot, f, indent=2)
    enriched.reset_index().assign(
        date=lambda d: d["date"].astype(str)
    ).to_json(p.historical_json, orient="records", indent=2)

    return snapshot


def score_technical(snap: dict) -> dict:
    """Turn the indicator snapshot into score (0-100), trend, momentum."""
    bull, total, notes = 0.0, 0.0, []
    close = snap.get("close")
    s50, s200 = snap.get("sma_50"), snap.get("sma_200")
    e20, e50 = snap.get("ema_20"), snap.get("ema_50")
    rsi = snap.get("rsi_14")
    macd_v, sig = snap.get("macd"), snap.get("macd_signal")
    adx = snap.get("adx_14")
    pdi, mdi = snap.get("plus_di"), snap.get("minus_di")

    # Trend (weight 3)
    total += 3
    if close and s50 and s200:
        if close > s50 > s200:
            bull += 3; trend = "Strong Bullish"
        elif close > s200:
            bull += 2; trend = "Bullish"
        elif close < s50 < s200:
            bull += 0; trend = "Bearish"
        else:
            bull += 1; trend = "Sideways"
    elif close and s50:
        bull += 2 if close > s50 else 0.5
        trend = "Bullish" if close > s50 else "Bearish"
    else:
        total -= 3; trend = "Unknown"
    notes.append(f"Trend: {trend}")

    # EMA cross (weight 1)
    total += 1
    if e20 and e50:
        bull += 1 if e20 > e50 else 0
        notes.append("EMA20 " + (">" if e20 > e50 else "<") + " EMA50")

    # ADX + DI (weight 2)
    total += 2
    if adx is not None and pdi is not None and mdi is not None:
        up = pdi > mdi
        if adx >= 25:
            bull += 2 if up else 0
            strength = "Strong"
        elif adx >= 20:
            bull += 1.5 if up else 0.5
            strength = "Developing"
        else:
            bull += 1
            strength = "Weak"
        notes.append(f"ADX {adx:.1f} ({strength}); DI {'+' if up else '-'} dominant")
    else:
        total -= 2
        strength = "Unknown"

    # RSI (weight 1.5) -> also momentum read
    total += 1.5
    momentum = "Neutral"
    if rsi is not None:
        if rsi >= 70:
            bull += 0.5; momentum = "Overbought"
        elif rsi >= 55:
            bull += 1.5; momentum = "Strong"
        elif rsi >= 45:
            bull += 0.9; momentum = "Neutral"
        elif rsi >= 30:
            bull += 0.5; momentum = "Weak"
        else:
            bull += 0.9; momentum = "Oversold"
        notes.append(f"RSI {rsi:.1f} ({momentum})")
    else:
        total -= 1.5

    # MACD (weight 1.5)
    total += 1.5
    if macd_v is not None and sig is not None:
        if macd_v > sig:
            bull += 1.5 if (snap.get("macd_hist") or 0) > 0 else 1.0
            notes.append("MACD above signal")
        else:
            bull += 0.0 if (snap.get("macd_hist") or 0) < 0 else 0.5
            notes.append("MACD below signal")
    else:
        total -= 1.5

    # RSI divergence (informational flag; nudges score slightly)
    rdiv = snap.get("rsi_divergence") or {}
    if rdiv.get("type") == "bearish":
        bull -= 0.5
        notes.append(f"⚠ {rdiv['label']} ({rdiv['bars_ago']} bars ago): {rdiv['note']}")
    elif rdiv.get("type") == "bullish":
        bull += 0.5
        notes.append(f"⚠ {rdiv['label']} ({rdiv['bars_ago']} bars ago): {rdiv['note']}")

    bull = max(0.0, bull)
    score = round(bull / total * 100, 1) if total > 0 else None
    return {
        "technical_score": score,
        "trend": trend,
        "momentum": momentum,
        "adx_strength": strength,
        "rsi_divergence": rdiv,
        "notes": notes,
    }
