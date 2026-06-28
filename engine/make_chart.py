#!/usr/bin/env python3
"""
make_chart.py — TradingView-style candlestick chart from local OHLC
===================================================================
Builds a self-contained HTML chart for a symbol using TradingView's free
"lightweight-charts" library (loaded from CDN when you open the file):

  - candlesticks + volume
  - SMA20 / SMA50 / EMA20 overlays
  - a synced RSI(14) pane with 70/30 guides

USAGE
  python make_chart.py MLCF
  open stocks/MLCF/reports/MLCF_chart.html
"""

from __future__ import annotations
import sys
import json
import argparse

import pandas as pd

from engine.layout import StockPaths
from engine import technical as tech
from engine import indicators as ind
from engine import patterns as pat


def _series(dates, values):
    out = []
    for d, v in zip(dates, values):
        if pd.isna(v):
            continue
        out.append({"time": d, "value": round(float(v), 4)})
    return out


def build(symbol: str) -> str:
    p = StockPaths(symbol).ensure()
    if not p.historical_csv.exists():
        raise FileNotFoundError(f"missing {p.historical_csv}")
    df = tech.load_historical(p.historical_csv)
    dates = [d.strftime("%Y-%m-%d") for d in df.index]

    candles = [{"time": t, "open": round(float(o), 2), "high": round(float(h), 2),
                "low": round(float(l), 2), "close": round(float(c), 2)}
               for t, o, h, l, c in zip(dates, df["open"], df["high"], df["low"], df["close"])]

    up = "#26a69a"; down = "#ef5350"
    volume = []
    if "volume" in df.columns:
        for t, v, o, c in zip(dates, df["volume"], df["open"], df["close"]):
            if pd.isna(v):
                continue
            volume.append({"time": t, "value": float(v),
                           "color": (up + "80") if c >= o else (down + "80")})

    sma20 = _series(dates, ind.sma(df["close"], 20))
    sma50 = _series(dates, ind.sma(df["close"], 50))
    ema20 = _series(dates, ind.ema(df["close"], 20))
    rsi = _series(dates, ind.rsi(df["close"], 14))

    # trendlines: upper through recent swing highs, lower through recent swing lows
    piv = pat._zigzag(df, 4, 4, min(len(df), 120))
    highs = [(p[0], p[2]) for p in piv if p[1] == "H"]
    lows = [(p[0], p[2]) for p in piv if p[1] == "L"]
    last_idx = len(df) - 1

    import numpy as np

    def _trendline(anchors):
        """Least-squares fit through the last up-to-3 touches, drawn from the
        first touch to the current bar (so breakouts are visible)."""
        pts = anchors[-3:]
        if len(pts) < 2:
            return None
        xs = np.array([p[0] for p in pts], dtype=float)
        ys = np.array([p[1] for p in pts], dtype=float)
        m, b = np.polyfit(xs, ys, 1)
        start = int(xs.min())
        end = last_idx
        return [{"time": dates[start], "value": round(float(m * start + b), 2)},
                {"time": dates[end], "value": round(float(m * end + b), 2)}]

    trendlines = []
    if len(highs) >= 2:
        tl = _trendline(highs)
        if tl:
            trendlines.append(tl)
    if len(lows) >= 2:
        tl = _trendline(lows)
        if tl:
            trendlines.append(tl)

    detected = pat.detect_patterns(df)
    pat_label = "; ".join(f"{p['name']} ({p['status']}, {int(p['confidence']*100)}%)"
                          for p in detected[:2]) or "no clear pattern"

    data = {"candles": candles, "volume": volume, "sma20": sma20,
            "sma50": sma50, "ema20": ema20, "rsi": rsi, "trendlines": trendlines}
    last = candles[-1]
    title = f"{symbol} — {last['close']} ({last['time']})"

    html = """<!doctype html><html><head><meta charset="utf-8">
<title>__TITLE__</title>
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<style>
 body{margin:0;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#fff;color:#111}
 .hd{padding:10px 14px;font-weight:600}
 .legend{padding:0 14px 8px;font-size:.8em;color:#555}
 .legend b{font-weight:600}
 .sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 4px -1px 10px}
 #price{height:430px} #rsi{height:140px}
</style></head><body>
<div class="hd">__TITLE__</div>
<div class="legend">
 <span class="sw" style="background:#2962FF"></span>SMA20
 <span class="sw" style="background:#FF6D00"></span>SMA50
 <span class="sw" style="background:#AB47BC"></span>EMA20
 &nbsp;·&nbsp; lower pane: RSI(14)
 &nbsp;·&nbsp; <span class="sw" style="background:#FFD600"></span>pattern trendlines
 <br><b>Pattern:</b> __PATLABEL__
</div>
<div id="price"></div>
<div id="rsi"></div>
<script>
const D = __DATA__;
const opts = {layout:{background:{color:'#fff'},textColor:'#333'},
  grid:{vertLines:{color:'#f0f0f0'},horzLines:{color:'#f0f0f0'}},
  rightPriceScale:{borderColor:'#e0e0e0'}, timeScale:{borderColor:'#e0e0e0'},
  crosshair:{mode:0}};

const price = LightweightCharts.createChart(document.getElementById('price'), opts);
const candle = price.addCandlestickSeries({upColor:'#26a69a',downColor:'#ef5350',
  borderUpColor:'#26a69a',borderDownColor:'#ef5350',wickUpColor:'#26a69a',wickDownColor:'#ef5350'});
candle.setData(D.candles);
(D.trendlines || []).forEach(function(tl){
  var s = price.addLineSeries({color:'#FFD600', lineWidth:2, priceLineVisible:false,
    lastValueVisible:false, crosshairMarkerVisible:false});
  s.setData(tl);
});

const vol = price.addHistogramSeries({priceFormat:{type:'volume'},priceScaleId:'vol'});
price.priceScale('vol').applyOptions({scaleMargins:{top:0.82,bottom:0}});
vol.setData(D.volume);

function line(c,w,data){const s=price.addLineSeries({color:c,lineWidth:w,priceLineVisible:false,
  lastValueVisible:false}); s.setData(data); return s;}
line('#2962FF',2,D.sma20); line('#FF6D00',2,D.sma50); line('#AB47BC',2,D.ema20);

const rsiChart = LightweightCharts.createChart(document.getElementById('rsi'), opts);
const rsiS = rsiChart.addLineSeries({color:'#7E57C2',lineWidth:2,priceLineVisible:false});
rsiS.setData(D.rsi);
rsiS.createPriceLine({price:70,color:'#ef5350',lineStyle:2,lineWidth:1,axisLabelVisible:true,title:'70'});
rsiS.createPriceLine({price:30,color:'#26a69a',lineStyle:2,lineWidth:1,axisLabelVisible:true,title:'30'});

// sync the two panes' time axes
function sync(a,b){a.timeScale().subscribeVisibleLogicalRangeChange(r=>{if(r)b.timeScale().setVisibleLogicalRange(r);});}
sync(price,rsiChart); sync(rsiChart,price);
price.timeScale().fitContent(); rsiChart.timeScale().fitContent();
new ResizeObserver(()=>{price.applyOptions({width:document.getElementById('price').clientWidth});
  rsiChart.applyOptions({width:document.getElementById('rsi').clientWidth});}).observe(document.body);
price.applyOptions({width:document.getElementById('price').clientWidth});
rsiChart.applyOptions({width:document.getElementById('rsi').clientWidth});
</script></body></html>"""

    html = (html.replace("__TITLE__", title)
                .replace("__PATLABEL__", pat_label)
                .replace("__DATA__", json.dumps(data)))
    out = p.reports / f"{symbol}_chart.html"
    out.write_text(html)
    return str(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="+")
    args = ap.parse_args()
    for s in args.symbols:
        path = build(s.upper())
        print(f"{s.upper()}: chart -> {path}")


if __name__ == "__main__":
    main()
