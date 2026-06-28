"""
patterns.py
-----------
Technical pattern detection. Currently: RSI divergence.

RSI divergence compares the slope of price against the slope of RSI between
two recent swing points:

  - Bearish (regular): price higher high, RSI lower high  -> momentum fading
  - Bullish (regular): price lower low,  RSI higher low   -> selling exhausting

It is a *warning*, not a certainty — it works best near overbought/oversold
extremes and should be confirmed by price action.
"""

from __future__ import annotations
import pandas as pd


def _pivots(series: pd.Series, left: int, right: int):
    """Return (highs, lows) as lists of integer positions that are local
    extrema within a +/- window."""
    vals = series.values
    n = len(vals)
    highs, lows = [], []
    for i in range(left, n - right):
        if pd.isna(vals[i]):
            continue
        lhs = vals[i - left:i]
        rhs = vals[i + 1:i + right + 1]
        # strict local extremum: greater/less than ALL neighbours on both sides
        if vals[i] > lhs.max() and vals[i] > rhs.max():
            highs.append(i)
        if vals[i] < lhs.min() and vals[i] < rhs.min():
            lows.append(i)
    return highs, lows


def _cluster(levels, tol):
    levels = sorted(levels)
    out = []
    for lv in levels:
        if out and abs(lv - out[-1]) / out[-1] <= tol:
            out[-1] = (out[-1] + lv) / 2
        else:
            out.append(lv)
    return out


def support_resistance(df, left: int = 4, right: int = 4,
                       lookback: int = 120, tol: float = 0.02) -> dict:
    """Swing-pivot based support/resistance from OHLC."""
    high = df["high"].reset_index(drop=True)
    low = df["low"].reset_index(drop=True)
    close = float(df["close"].dropna().iloc[-1])
    n = len(high)
    cut = max(0, n - lookback)
    res_idx = _pivots(high, left, right)[0]
    sup_idx = _pivots(low, left, right)[1]
    res = _cluster([float(high[i]) for i in res_idx if i >= cut], tol)
    sup = _cluster([float(low[i]) for i in sup_idx if i >= cut], tol)
    resistance = [r for r in res if r > close]
    support = [s for s in sup if s < close]
    return {
        "price": round(close, 2),
        "nearest_resistance": round(min(resistance), 2) if resistance else None,
        "nearest_support": round(max(support), 2) if support else None,
        "resistance_levels": [round(x, 2) for x in sorted(resistance)[:3]],
        "support_levels": [round(x, 2) for x in sorted(support, reverse=True)[:3]],
    }


def _zigzag(df, left, right, lookback):
    """Alternating swing-pivot sequence: list of [idx, 'H'/'L', value]."""
    high = df["high"].reset_index(drop=True)
    low = df["low"].reset_index(drop=True)
    n = len(high)
    cut = max(0, n - lookback)
    hi = _pivots(high, left, right)[0]
    lo = _pivots(low, left, right)[1]
    piv = [[i, "H", float(high[i])] for i in hi if i >= cut] + \
          [[i, "L", float(low[i])] for i in lo if i >= cut]
    piv.sort(key=lambda p: p[0])
    out = []
    for p in piv:
        if out and out[-1][1] == p[1]:  # same type in a row -> keep the extreme
            if (p[1] == "H" and p[2] > out[-1][2]) or (p[1] == "L" and p[2] < out[-1][2]):
                out[-1] = p
        else:
            out.append(p)
    return out


def _near(a, b, tol):
    return abs(a - b) / ((a + b) / 2.0) <= tol


def detect_patterns(df, left: int = 4, right: int = 4,
                    lookback: int = 120, tol: float = 0.03) -> list:
    """Pivot-geometry candidate detection. Returns patterns sorted by
    confidence (each is a *candidate*, confirm visually on the chart)."""
    z = _zigzag(df, left, right, lookback)
    close = float(df["close"].dropna().iloc[-1])
    c = df["close"].reset_index(drop=True)
    found = []

    def conf(equality_err):  # closer pivots -> higher confidence
        return max(0.0, min(1.0, 1 - equality_err / tol)) * 0.6

    H = [p for p in z if p[1] == "H"]
    L = [p for p in z if p[1] == "L"]

    # ---- Double Top: ...H L H, two near-equal peaks, break below trough ----
    if len(z) >= 3 and z[-1][1] == "H" and z[-2][1] == "L" and z[-3][1] == "H":
        p1, trough, p2 = z[-3][2], z[-2][2], z[-1][2]
        err = abs(p1 - p2) / ((p1 + p2) / 2)
        if err <= tol:
            confirmed = close < trough
            peak = max(p1, p2)
            found.append({"name": "Double Top", "type": "bearish",
                          "confidence": round(conf(err) + (0.4 if confirmed else 0.15), 2),
                          "status": "confirmed" if confirmed else "forming",
                          "neckline": round(trough, 2),
                          "target": round(trough - (peak - trough), 2),
                          "note": "Two near-equal peaks; breaks down below the trough (neckline)."})

    # ---- Double Bottom: ...L H L ----
    if len(z) >= 3 and z[-1][1] == "L" and z[-2][1] == "H" and z[-3][1] == "L":
        b1, peak, b2 = z[-3][2], z[-2][2], z[-1][2]
        err = abs(b1 - b2) / ((b1 + b2) / 2)
        if err <= tol:
            confirmed = close > peak
            low = min(b1, b2)
            found.append({"name": "Double Bottom", "type": "bullish",
                          "confidence": round(conf(err) + (0.4 if confirmed else 0.15), 2),
                          "status": "confirmed" if confirmed else "forming",
                          "neckline": round(peak, 2),
                          "target": round(peak + (peak - low), 2),
                          "note": "Two near-equal troughs; breaks up above the peak (neckline)."})

    # ---- Head & Shoulders: H L H L H, head highest, shoulders near-equal ----
    if len(z) >= 5 and [p[1] for p in z[-5:]] == ["H", "L", "H", "L", "H"]:
        ls, t1, head, t2, rs = [p[2] for p in z[-5:]]
        if head > ls and head > rs and _near(ls, rs, tol * 1.5):
            neck = (t1 + t2) / 2
            confirmed = close < neck
            found.append({"name": "Head & Shoulders", "type": "bearish",
                          "confidence": round(0.5 + (0.35 if confirmed else 0.1), 2),
                          "status": "confirmed" if confirmed else "forming",
                          "neckline": round(neck, 2),
                          "target": round(neck - (head - neck), 2),
                          "note": "Three peaks, middle highest; breaks down below the neckline."})

    # ---- Inverse H&S: L H L H L ----
    if len(z) >= 5 and [p[1] for p in z[-5:]] == ["L", "H", "L", "H", "L"]:
        ls, t1, head, t2, rs = [p[2] for p in z[-5:]]
        if head < ls and head < rs and _near(ls, rs, tol * 1.5):
            neck = (t1 + t2) / 2
            confirmed = close > neck
            found.append({"name": "Inverse Head & Shoulders", "type": "bullish",
                          "confidence": round(0.5 + (0.35 if confirmed else 0.1), 2),
                          "status": "confirmed" if confirmed else "forming",
                          "neckline": round(neck, 2),
                          "target": round(neck + (neck - head), 2),
                          "note": "Three troughs, middle lowest; breaks up above the neckline."})

    # ---- Triangles (last 2 highs + last 2 lows) ----
    if len(H) >= 2 and len(L) >= 2:
        h1, h2 = H[-2][2], H[-1][2]
        l1, l2 = L[-2][2], L[-1][2]
        flat_h, flat_l = _near(h1, h2, tol), _near(l1, l2, tol)
        if flat_h and l2 > l1 * (1 + tol):
            found.append({"name": "Ascending Triangle", "type": "bullish", "confidence": 0.55,
                          "status": "forming", "neckline": round(max(h1, h2), 2),
                          "target": round(max(h1, h2) + (max(h1, h2) - l1), 2),
                          "note": "Flat resistance with rising lows; bullish breakout bias."})
        elif flat_l and h2 < h1 * (1 - tol):
            found.append({"name": "Descending Triangle", "type": "bearish", "confidence": 0.55,
                          "status": "forming", "neckline": round(min(l1, l2), 2),
                          "target": round(min(l1, l2) - (h1 - min(l1, l2)), 2),
                          "note": "Flat support with falling highs; bearish breakdown bias."})
        elif h2 < h1 * (1 - tol) and l2 > l1 * (1 + tol):
            found.append({"name": "Symmetrical Triangle", "type": "neutral", "confidence": 0.45,
                          "status": "forming", "neckline": None, "target": None,
                          "note": "Converging highs and lows; breakout direction undecided."})

    # ---- Bull Flag: sharp pole then tight shallow consolidation ----
    if len(c) >= 25:
        pole_lo = c.iloc[-20:-6].min()
        pole_hi = c.iloc[-20:-6].max()
        flag = c.iloc[-6:]
        pole_gain = (pole_hi - pole_lo) / pole_lo if pole_lo else 0
        flag_range = (flag.max() - flag.min()) / flag.mean()
        if pole_gain >= 0.12 and flag_range <= 0.06 and flag.iloc[-1] <= pole_hi:
            found.append({"name": "Bull Flag", "type": "bullish",
                          "confidence": round(min(0.7, 0.4 + pole_gain), 2),
                          "status": "forming", "neckline": round(float(pole_hi), 2),
                          "target": round(float(flag.iloc[-1] + (pole_hi - pole_lo)), 2),
                          "note": "Strong pole then tight consolidation; bullish continuation bias."})

    # ---- Falling Wedge: lower highs + lower lows, converging (bullish reversal) ----
    if len(H) >= 2 and len(L) >= 2:
        h1, h2 = H[-2][2], H[-1][2]
        l1, l2 = L[-2][2], L[-1][2]
        if h2 < h1 and l2 < l1 and (h2 - l2) < (h1 - l1) * 0.9:
            found.append({"name": "Falling Wedge", "type": "bullish", "confidence": 0.5,
                          "status": "forming", "neckline": round(h2, 2),
                          "target": round(h1, 2),
                          "note": "Lower highs and lows converging after a decline; bullish reversal bias."})

    found.sort(key=lambda p: p["confidence"], reverse=True)
    return found


def detect_rsi_divergence(close: pd.Series, rsi: pd.Series,
                          left: int = 5, right: int = 5,
                          lookback: int = 60, min_gap: int = 5,
                          max_gap: int = 60) -> dict:
    """Detect the most recent regular bullish/bearish RSI divergence.
    Returns {type, ...} with type in {'bearish','bullish',None}."""
    close = close.reset_index(drop=True)
    rsi = rsi.reset_index(drop=True)
    n = len(close)
    if n < left + right + 2:
        return {"type": None, "reason": "not enough bars"}

    highs, lows = _pivots(close, left, right)
    recent_cut = n - lookback

    def _pair(pivots):
        pts = [i for i in pivots if i >= recent_cut and not pd.isna(rsi[i])]
        if len(pts) < 2:
            return None
        a, b = pts[-2], pts[-1]            # two most recent comparable swings
        if not (min_gap <= (b - a) <= max_gap):
            return None
        return a, b

    result = {"type": None}

    # --- bearish: higher price high, lower RSI high ---
    hp = _pair(highs)
    if hp:
        a, b = hp
        if close[b] > close[a] and rsi[b] < rsi[a]:
            result = {
                "type": "bearish",
                "label": "Bearish RSI divergence",
                "note": (f"Price made a higher high ({close[a]:.2f}→{close[b]:.2f}) "
                         f"while RSI made a lower high ({rsi[a]:.1f}→{rsi[b]:.1f}) "
                         f"— upward momentum is fading; watch for a pullback."),
                "price_from": round(float(close[a]), 2), "price_to": round(float(close[b]), 2),
                "rsi_from": round(float(rsi[a]), 1), "rsi_to": round(float(rsi[b]), 1),
                "bars_ago": int(n - 1 - b),
            }

    # --- bullish: lower price low, higher RSI low ---
    lp = _pair(lows)
    if lp:
        a, b = lp
        if close[b] < close[a] and rsi[b] > rsi[a]:
            bull = {
                "type": "bullish",
                "label": "Bullish RSI divergence",
                "note": (f"Price made a lower low ({close[a]:.2f}→{close[b]:.2f}) "
                         f"while RSI made a higher low ({rsi[a]:.1f}→{rsi[b]:.1f}) "
                         f"— selling momentum is easing; watch for a bounce."),
                "price_from": round(float(close[a]), 2), "price_to": round(float(close[b]), 2),
                "rsi_from": round(float(rsi[a]), 1), "rsi_to": round(float(rsi[b]), 1),
                "bars_ago": int(n - 1 - b),
            }
            # prefer the more recent of the two signals
            if result["type"] is None or bull["bars_ago"] < result.get("bars_ago", 1e9):
                result = bull

    return result
