"""
indicators.py
-------------
Pure-pandas technical indicators (no TA-Lib). All functions take/return
pandas Series aligned to the input index.
"""

import numpy as np
import pandas as pd


def sma(s, n):
    return s.rolling(n, min_periods=n).mean()


def ema(s, n):
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def _wilder(s, n):
    return s.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def rsi(close, n=14):
    d = close.diff()
    gain, loss = d.clip(lower=0), -d.clip(upper=0)
    ag, al = _wilder(gain, n), _wilder(loss, n)
    rs = ag / al.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    out[al == 0] = 100
    return out


def macd(close, fast=12, slow=26, signal=9):
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({"macd": line, "macd_signal": sig, "macd_hist": line - sig})


def true_range(h, l, c):
    pc = c.shift(1)
    return pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)


def atr(h, l, c, n=14):
    return _wilder(true_range(h, l, c), n)


def adx(h, l, c, n=14):
    up, dn = h.diff(), -l.diff()
    plus_dm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=h.index)
    minus_dm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=h.index)
    tr = _wilder(true_range(h, l, c), n)
    plus_di = 100 * _wilder(plus_dm, n) / tr
    minus_di = 100 * _wilder(minus_dm, n) / tr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return pd.DataFrame({"adx": _wilder(dx, n), "plus_di": plus_di, "minus_di": minus_di})


def bollinger(close, n=20, k=2.0):
    mid = sma(close, n)
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    return pd.DataFrame({"bb_upper": mid + k * sd, "bb_mid": mid, "bb_lower": mid - k * sd})


def obv(close, volume):
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    """df needs columns: open, high, low, close, (volume optional)."""
    out = df.copy()
    c, h, l = out["close"], out["high"], out["low"]
    out["sma_20"] = sma(c, 20)
    out["sma_50"] = sma(c, 50)
    out["sma_200"] = sma(c, 200)
    out["ema_20"] = ema(c, 20)
    out["ema_50"] = ema(c, 50)
    out["ema_100"] = ema(c, 100)
    out["ema_200"] = ema(c, 200)
    out["rsi_14"] = rsi(c, 14)
    out = out.join(macd(c))
    out = out.join(adx(h, l, c, 14))
    out = out.join(bollinger(c))
    out["atr_14"] = atr(h, l, c, 14)
    return out
