"""Make SAMPLE data for the headless-browser check: overwrites 60 stocks with synthetic base-pattern shapes.

!!  THIS OVERWRITES shared-data/ IN THE FOLDER IT RUNS IN.  Run it ONLY on a throw-away COPY of the project, never on
!!  your real repository folder.  It refuses to run unless you add --yes-this-is-a-copy.

    python tests/browser/make_sample_data.py --yes-this-is-a-copy
"""
import os
import sys

if "--yes-this-is-a-copy" not in sys.argv:
    sys.exit(__doc__)
import json; sys.path.insert(0, ".")
import config, detail_store, build_board
import scan_market_structure_combined as scan
from common import load_stocks, atomic_write_text, dumps_strict
from tests import base_shapes as S
prof=config.PROFILES["1d"]
variants=[
 ("flat forming",lambda s:S.flat_base(seed=s)),("flat BREAKOUT",lambda s:S.flat_base(seed=s).bar(101.5,vol=2.0)),
 ("flat FAILED",lambda s:S.flat_base(seed=s).bar(84,vol=1.5)),("cup forming",lambda s:S.cup(seed=s)),
 ("cup BREAKOUT",lambda s:S.cup(seed=s).bar(100.5,vol=2.0)),("vcp forming",lambda s:S.vcp(seed=s)),
 ("vcp BREAKOUT",lambda s:S.vcp(seed=s).bar(97.5,vol=2.2)),("db forming",lambda s:S.double_bottom(seed=s)),
 ("htf forming",lambda s:S.htf(seed=s)),("htf BREAKOUT",lambda s:S.htf(seed=s).bar(87.2,vol=2.0)),
 ("pp forming",lambda s:S.power_play(seed=s)),("asc forming",lambda s:S.ascending(seed=s)),
 ("darvas forming",lambda s:S.darvas(seed=s)),("ledge forming",lambda s:S.ledge(seed=s)),
 ("ledge FAILED",lambda s:S.ledge(seed=s).bar(80,vol=1.5)),
]
recs=load_stocks(); ok=[r for r in recs if r.get("scanner_status")=="OK"]
chosen=ok[:60]; stamp="2026-11-14T00:00:00+00:00"; made=[]
for k,r in enumerate(chosen):
    lab,f=variants[k%len(variants)]
    df=f(1000+k).df()
    summary,detail=scan.compute_signals(prof,df,"BULLISH")
    detail_store.write_detail(r["symbol"],"1d",detail,stamp)
    r.update(summary); r["current_price"]=round(float(df["Close"].iloc[-1]),2)
    made.append((r["symbol"],lab))

# ---- four crafted stocks for the SMC + pattern + base tab. Prices are built so that the existing "SMC + Pattern" rule passes
# ---- (a Hammer at a Strong Low, after a decline, confirmed, price within 2 ATR). Only the base pattern differs.
import pandas as pd, copy
DATES = [d.strftime("%Y-%m-%d") for d in pd.bdate_range(end="2026-11-12", periods=50)]
def crafted_candles():
    cs, prev = [], 125.0
    for i in range(45):                                   # a steady decline into the low
        c = 125 - 0.55 * i; cs.append([DATES[i], round(prev, 2), round(max(prev, c) + 0.5, 2), round(min(prev, c) - 0.5, 2), round(c, 2), 1_000_000]); prev = c
    cs.append([DATES[45], 100.6, 100.9, 98.2, 100.7, 1_500_000])   # the Hammer: its low (98.2) is the SMC level
    for k, c in enumerate([101.2, 101.6, 101.9, 102.2]):           # later candles close above the Hammer: confirmed
        i = 46 + k; cs.append([DATES[i], cs[-1][4], round(c + 0.4, 2), round(cs[-1][4] - 0.3, 2), c, 1_000_000])
    return cs
def hammer():
    return {"name": "Hammer", "group": "1-candle", "dir": "bull", "len": 1, "stop": 98.2, "since": 4, "time": DATES[45], "price": 100.7,
            "vol": 1.5, "confirm": "confirmed", "score": 70, "parts": [24, 25, 10, 11, 0]}
def base_sig(status, pivot, since, score):
    g = {"name": "Flat Base", "group": "base", "dir": "bull", "len": 30, "stop": 99.0, "since": since, "time": DATES[49 - since], "price": 102.2,
         "vol": 2.2 if status == "breakout" else 0.8, "confirm": {"forming": "pending", "breakout": "confirmed", "failed": "failed"}[status], "score": score,
         "parts": [20, 25, 20, 10, 0], "status": status, "pivot": pivot, "depth": 9.1, "formed": since + 2, "base_no": 1, "climactic": False}
    return g
CRAFT = [("forming", base_sig("forming", 103.0, 2, 72)), ("breakout", base_sig("breakout", 101.8, 0, 81)),
         ("no base", None), ("failed base", base_sig("failed", 103.0, 0, 60))]
crafted = []
for k, (lab, base) in enumerate(CRAFT):
    r = ok[60 + k]; sym = r["symbol"]
    d = copy.deepcopy(detail_store.read_detail(sym).get("1d") or {"context": {}, "scores": {}})
    d["candles"] = crafted_candles(); d["last_bar_time"] = DATES[49]; d["bars"] = 50
    d["signals"] = [hammer()] + ([base] if base else [])
    d.setdefault("context", {}).update({"atr": 2.5, "atr_pct": 2.4, "stage": 2, "stage_label": "Stage 2 - advancing", "ma_slope_pct": 3.1, "price_vs_ma": "above", "base_count": 0, "base_next": 1, "uptrend_bars": 120})
    detail_store.write_detail(sym, "1d", d, stamp)
    r.update({"current_price": "102.2", "bottom_signal": "STRONG_LOW", "bottom_signal_time": DATES[44], "bottom_signal_price": "98.2",
              "bottom_bars_since": 5, "bullish_rank_score": 80 - k})
    crafted.append((sym, lab))
atomic_write_text(str(config.STOCKS_FILE) if hasattr(config,"STOCKS_FILE") else "shared-data/stocks.json", dumps_strict(recs, False))
build_board.main()
json.dump({"made": made, "crafted": crafted}, open(os.path.join(os.path.dirname(__file__), "sample_made.json"), "w"))
print("overwrote",len(made),"stocks;", made[:4])
