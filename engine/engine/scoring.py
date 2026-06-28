"""
scoring.py
----------
Converts normalized metrics + technical snapshot into:
  - fundamental_score (0-100) with pillar breakdown
  - technical_score (0-100)  [passed in from technical.py]
  - overall_score (70/30)  -> rating
  - risk (Low/Medium/High)

All thresholds/weights come from config.py.
"""

from __future__ import annotations
from . import config as C


def _band_score(value, thresholds, higher_better=True):
    """Map a value to 0/33/66/100 by ascending thresholds (t1,t2,t3)."""
    if value is None:
        return None
    t1, t2, t3 = thresholds
    if higher_better:
        if value >= t3: return 100.0
        if value >= t2: return 66.0
        if value >= t1: return 33.0
        return 0.0
    else:
        if value <= t1: return 100.0
        if value <= t2: return 66.0
        if value <= t3: return 33.0
        return 0.0


def _pillar_score(metrics, metric_names):
    """Average of available metric sub-scores in a pillar. None if none available."""
    scores, used, missing = [], [], []
    for name in metric_names:
        spec = C.FUND_THRESHOLDS.get(name)
        if not spec:
            continue
        s = _band_score(metrics.get(name), spec["t"], spec["higher_better"])
        if s is None:
            missing.append(name)
        else:
            scores.append(s); used.append(name)
    if not scores:
        return None, used, missing
    return sum(scores) / len(scores), used, missing


def score_fundamental(metrics: dict) -> dict:
    pillar_scores, coverage = {}, {}
    weighted_sum, weight_used = 0.0, 0.0
    for pillar, weight in C.FUNDAMENTAL_PILLARS.items():
        ps, used, missing = _pillar_score(metrics, C.PILLAR_METRICS[pillar])
        pillar_scores[pillar] = ps
        coverage[pillar] = {"used": used, "missing": missing}
        if ps is not None:
            weighted_sum += ps * weight
            weight_used += weight
    # re-normalize over the pillars we actually had data for
    fscore = round(weighted_sum / weight_used, 1) if weight_used > 0 else None
    return {
        "fundamental_score": fscore,
        "pillars": pillar_scores,
        "coverage": coverage,
        "weight_covered": round(weight_used, 2),
    }


def _risk(metrics, tech_snapshot):
    """Higher risk_score = safer. Then map to band. Considers leverage,
    valuation stretch, and price volatility (ATR % of price)."""
    pts, total = 0.0, 0.0

    de = metrics.get("debt_to_equity")
    total += 1
    if de is not None:
        pts += 1 if de <= 0.5 else 0.6 if de <= 1.0 else 0.3 if de <= 2.0 else 0
    else:
        total -= 1

    pe = metrics.get("pe_ratio")
    total += 1
    if pe is not None:
        pts += 1 if 0 < pe <= 12 else 0.6 if pe <= 20 else 0.3 if pe <= 35 else 0
    else:
        total -= 1

    total += 1
    close = (tech_snapshot or {}).get("close")
    atr = (tech_snapshot or {}).get("atr_14")
    if close and atr:
        vol = atr / close
        pts += 1 if vol <= 0.02 else 0.6 if vol <= 0.035 else 0.3 if vol <= 0.05 else 0
    else:
        total -= 1

    if total <= 0:
        return None, "Unknown"
    risk_score = pts / total * 100
    for thr, label in C.RISK_BANDS:
        if risk_score >= thr:
            return round(risk_score, 1), label
    return round(risk_score, 1), "High"


def _rating(overall):
    if overall is None:
        return "Unrated"
    for thr, label in C.RATING_BANDS:
        if overall >= thr:
            return label
    return "Sell"


def final_score(metrics: dict, technical: dict, tech_snapshot: dict | None = None) -> dict:
    fund = score_fundamental(metrics)
    fscore = fund["fundamental_score"]
    tscore = (technical or {}).get("technical_score")

    if fscore is not None and tscore is not None:
        overall = round(fscore * C.FUNDAMENTAL_WEIGHT + tscore * C.TECHNICAL_WEIGHT, 1)
    elif fscore is not None:
        overall = fscore
    elif tscore is not None:
        overall = tscore
    else:
        overall = None

    risk_score, risk_label = _risk(metrics, tech_snapshot)

    return {
        "fundamental_score": fscore,
        "technical_score": tscore,
        "overall_score": overall,
        "rating": _rating(overall),
        "risk": risk_label,
        "risk_score": risk_score,
        "weights": {"fundamental": C.FUNDAMENTAL_WEIGHT, "technical": C.TECHNICAL_WEIGHT},
        "fundamental_detail": fund,
    }
