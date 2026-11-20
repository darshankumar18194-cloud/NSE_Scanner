"""Make SAMPLE data for the headless-browser check: overwrites stocks with synthetic base-pattern shapes (all 21 bases, 1D and 1H).

!!  THIS OVERWRITES shared-data/ IN THE FOLDER IT RUNS IN.  Run it ONLY on a throw-away COPY of the project, never on
!!  your real repository folder.  It refuses to run unless you add --yes-this-is-a-copy.

    python tests/browser/make_sample_data.py --yes-this-is-a-copy
"""
import copy
import json
import os
import sys

if "--yes-this-is-a-copy" not in sys.argv:
    sys.exit(__doc__)
sys.path.insert(0, ".")
import numpy as np
import pandas as pd

import build_board
import config
import detail_store
import scan_market_structure_combined as scan
from common import atomic_write_text, dumps_strict, load_stocks
from tests import base_shapes as S

P1D, P1H = config.PROFILES["1d"], config.PROFILES["1h"]
V = [  # (label, builder) - the shapes, with breakouts and failures
    ("flat forming", lambda s: S.flat_base(seed=s)), ("flat BREAKOUT", lambda s: S.flat_base(seed=s).bar(101.5, vol=2.0)),
    ("flat FAILED", lambda s: S.flat_base(seed=s).bar(84, vol=1.5)), ("cup forming", lambda s: S.cup(seed=s)),
    ("cup BREAKOUT", lambda s: S.cup(seed=s).bar(100.5, vol=2.0)), ("vcp forming", lambda s: S.vcp(seed=s)),
    ("vcp BREAKOUT", lambda s: S.vcp(seed=s).bar(97.5, vol=2.2)), ("double bottom", lambda s: S.double_bottom(seed=s)),
    ("htf", lambda s: S.htf(seed=s)), ("htf BREAKOUT", lambda s: S.htf(seed=s).bar(87.2, vol=2.0)), ("power play", lambda s: S.power_play(seed=s)),
    ("ascending", lambda s: S.ascending(seed=s)), ("darvas", lambda s: S.darvas(seed=s)), ("ledge", lambda s: S.ledge(seed=s)),
    ("triangle asc", lambda s: S.triangle_asc(seed=s)), ("triangle asc BREAKOUT", lambda s: S.triangle_asc(seed=s).bar(101.5, vol=2.0)),
    ("triangle desc", lambda s: S.triangle_desc(seed=s)), ("triangle sym", lambda s: S.triangle_sym(seed=s)),
    ("wedge falling", lambda s: S.wedge_falling(seed=s)), ("wedge rising", lambda s: S.wedge_rising(seed=s)),
    ("flag bull", lambda s: S.flag_bull(seed=s)), ("pennant", lambda s: S.pennant_bull(seed=s)), ("flag bear", lambda s: S.flag_bear(seed=s)),
    ("rectangle", lambda s: S.rectangle(seed=s)), ("rectangle BREAKOUT up", lambda s: S.rectangle(seed=s).bar(101.9, vol=2.0)),
    ("rectangle BREAKOUT down", lambda s: S.rectangle(seed=s).bar(88.2, vol=2.0)), ("diamond", lambda s: S.diamond(seed=s)),
    ("rounding", lambda s: S.rounding_bottom(seed=s)), ("broadening", lambda s: S.broadening(seed=s)),
    ("three pushes", lambda s: S.three_pushes_up(seed=s)), ("three pushes BREAKOUT", lambda s: S.three_pushes_up(seed=s).bar(105.0, vol=1.5)),
    ("bump and run", lambda s: S.bump_and_run(seed=s)), ("ross hook", lambda s: S.ross_hook_bull(seed=s)),
    ("wyckoff", lambda s: S.wyckoff(seed=s)), ("demand", lambda s: S.demand_zone(seed=s)), ("supply", lambda s: S.supply_zone(seed=s)),
]


def hourly(df):
    n = len(df)
    days = pd.bdate_range(end="2026-11-12", periods=(n + 6) // 7)
    idx = [pd.Timestamp(d) + pd.Timedelta(hours=9, minutes=15 + 60 * k) for d in days for k in range(7)][-n:]
    out = df.copy(); out["Date"] = idx
    return out


recs = load_stocks()
ok = [r for r in recs if r.get("scanner_status") == "OK" and not r["symbol"].startswith("^")]
stamp = "2026-11-14T00:00:00+00:00"
made = []
for k, r in enumerate(ok[:150]):                                    # 1D: every shape, several times
    lab, f = V[k % len(V)]
    df = f(1000 + k).df()
    summary, detail = scan.compute_signals(P1D, df, "BULLISH")
    detail_store.write_detail(r["symbol"], "1d", detail, stamp)
    r.update(summary); r["current_price"] = round(float(df["Close"].iloc[-1]), 2)
    made.append((r["symbol"], lab))
made1h = []
for k, r in enumerate(ok[150:210]):                                  # 1H: the same shapes counted in hourly candles
    lab, f = V[k % len(V)]
    df = hourly(f(3000 + k).df())
    _, detail = scan.compute_signals(P1H, df, "BULLISH")
    detail_store.write_detail(r["symbol"], "1h", detail, stamp)
    made1h.append((r["symbol"], lab))

# ---- crafted stocks for the SMC + pattern + base tab (prices are irrelevant: the signals are written by hand)
DATES = [d.strftime("%Y-%m-%d") for d in pd.bdate_range(end="2026-11-12", periods=50)]


def candles():
    cs, prev = [], 125.0
    for i in range(45):
        c = 125 - 0.55 * i
        cs.append([DATES[i], round(prev, 2), round(max(prev, c) + 0.5, 2), round(min(prev, c) - 0.5, 2), round(c, 2), 1_000_000]); prev = c
    cs.append([DATES[45], 100.6, 100.9, 98.2, 100.7, 1_500_000])
    for k, c in enumerate([101.2, 101.6, 101.9, 102.2]):
        cs.append([DATES[46 + k], cs[-1][4], round(c + 0.4, 2), round(cs[-1][4] - 0.3, 2), c, 1_000_000])
    return cs


def candles_bear():     # a steady advance, a bearish candle with a tall upper wick, then closes below it: a confirmed bearish pattern
    cs, prev = [], 80.0
    for i in range(45):
        c = 80 + 0.55 * i
        cs.append([DATES[i], round(prev, 2), round(max(prev, c) + 0.5, 2), round(min(prev, c) - 0.5, 2), round(c, 2), 1_000_000]); prev = c
    cs.append([DATES[45], 104.9, 107.8, 104.7, 105.0, 1_500_000])
    for k, c in enumerate([104.5, 104.0, 103.5, 103.0]):
        cs.append([DATES[46 + k], cs[-1][4], round(cs[-1][4] + 0.3, 2), round(c - 0.4, 2), c, 1_000_000])
    return cs


def candle_sig(name, d):
    return {"name": name, "group": "2-candle", "dir": d, "len": 1, "stop": 98.2 if d == "bull" else 107.8, "since": 4, "time": DATES[45], "price": 100.7 if d == "bull" else 105.0,
            "vol": 1.5, "confirm": "confirmed", "score": 70, "parts": [24, 25, 10, 11, 0]}


def base_sig(name, d, status, since, score, pivot, **kw):
    g = {"name": name, "group": "base", "dir": d, "len": 30, "stop": 99.0 if d == "bull" else 108.0, "since": since, "time": DATES[49 - since], "price": 102.2 if d == "bull" else 103.0,
         "vol": 2.2 if status == "breakout" else 0.8, "confirm": {"forming": "pending", "breakout": "confirmed", "failed": "failed"}[status], "score": score,
         "parts": [20, 25, 20, 10, 0], "status": status, "pivot": pivot, "depth": 9.1, "formed": since + 2, "base_no": 1, "climactic": False, "quality": 70}
    g.update(kw)
    return g


CRAFT = [  # (label, SMC trend, candle pattern, base signal)
    ("triple forming", "BULLISH", candle_sig("Hammer", "bull"), base_sig("Flat Base", "bull", "forming", 2, 72, 103.0)),
    ("triple breakout", "BULLISH", candle_sig("Hammer", "bull"), base_sig("Flat Base", "bull", "breakout", 0, 81, 101.8, vol_x=2.2)),
    ("no candle", "BULLISH", None, base_sig("Flat Base", "bull", "forming", 2, 72, 103.0)),
    ("smc disagrees", "BEARISH", candle_sig("Hammer", "bull"), base_sig("Flat Base", "bull", "forming", 2, 72, 103.0)),
    ("triple bear", "BEARISH", candle_sig("Bearish Engulfing", "bear"), base_sig("Bump and Run", "bear", "forming", 1, 66, 99.0, stop=108.0)),
    ("failed base", "BULLISH", candle_sig("Hammer", "bull"), base_sig("Flat Base", "bull", "failed", 0, 60, 103.0)),
]
crafted = []
for k, (lab, trend, cand, base) in enumerate(CRAFT):
    r = ok[210 + k]; sym = r["symbol"]
    d = copy.deepcopy(detail_store.read_detail(sym).get("1d") or {"context": {}, "scores": {}})
    d["candles"] = candles_bear() if lab == "triple bear" else candles(); d["last_bar_time"] = DATES[49]; d["bars"] = 50
    d["signals"] = ([cand] if cand else []) + [base]
    d.setdefault("context", {}).update({"atr": 2.5, "atr_pct": 2.4, "stage": 2, "stage_label": "Stage 2 - advancing", "ma_slope_pct": 3.1, "price_vs_ma": "above",
                                        "base_count": 0, "base_next": 1, "uptrend_bars": 120, "ret_6m": 40.0, "turnover_cr": 12.0})
    detail_store.write_detail(sym, "1d", d, stamp)
    r.update({"current_price": "103.0" if lab == "triple bear" else "102.2", "trend": trend})
    crafted.append((sym, lab))
atomic_write_text("shared-data/stocks.json", dumps_strict(recs, False))
build_board.main()
json.dump({"made": made, "made1h": made1h, "crafted": crafted}, open(os.path.join(os.path.dirname(__file__), "sample_made.json"), "w"))
print("overwrote", len(made), "1D stocks,", len(made1h), "1H stocks and", len(crafted), "crafted stocks")
