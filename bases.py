"""Base patterns: the named bases of the Pre-Breakout guides (1D and, when BASE_1H_ON, 1H), plus Stage Analysis and the Base Count.

SIGNALS (group "base"). The first nine are in this file, the other twelve in bases_ext.py:
    VCP, Cup with Handle, Flat Base, Double Bottom, High Tight Flag, Power Play, Ascending Base, Darvas Box, The Ledge,
    Triangles, Flags and Pennants, Wedges, Rectangle, Diamond, Rounding Bottom, Broadening Wedge, Three Pushes,
    Bump and Run, Ross Hook, Wyckoff Accumulation, Supply & Demand Zones
Direction: most are bullish; Bump and Run, Descending Triangle, Rising Wedge, bearish Flags / Hooks / Pushes / Supply zones are
bearish; Rectangle, Diamond and the Symmetrical Triangle are "two-sided" (the side that breaks decides: neutral while forming);
the Broadening Wedge is a warning (no trade level).
READINGS (stored once per stock in `context`, never hidden or filtered by themselves):
    Stage Analysis (Weinstein stage 1-4) and the Base Count (Base 1, 2, 3+ inside one uptrend)

How a signal is built - and why it cannot repaint
-------------------------------------------------
Every detector `det_*(a, i)` looks ONLY at candles 0..i and answers: "is a complete base standing at candle i?"
If yes it returns the pivot (breakout level), the stop and the base's start. A small state machine walks candle by
candle through the recent window:

    armed    a base is standing and the close is within BASE_NEAR_PIVOT_PCT below its pivot
    breakout a later candle CLOSES above the pivot of the base armed on the candle before, on enough volume
    failed   a later candle closes below the stop (or a breakout falls back below its pivot within a few candles)

Nothing that happens at candle j can change what was decided at candle i < j; later candles only add the next event.
`since` / `time` of a signal are those of its latest event: the candle it became armed (status "forming"), the candle
that broke out ("breakout", which keeps that candle even if it fails later: `fail_since` says when) or the candle that
failed ("failed"). `formed` is how long ago the base first became armed. A close above the pivot on weak volume is not
a breakout: the base stays "forming" with `lowvol` set and its pivot does not move up.

`confirm` carries the status in the vocabulary the dashboard already understands:
    forming -> "pending", breakout -> "confirmed", failed -> "failed".

Code-detected chart patterns produce false signals. The thresholds are in config.py (BASE_*, VCP_*, CUP_* ...).
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

import config as C
import patterns as P
from bases_ext import DETECTORS_EXT, META_EXT

NAN = np.nan

# name -> (group, stars). Merged into signals.EVENT_META.
BASE_META: Dict[str, Tuple[str, int]] = {
    "VCP": ("base", 4), "Cup with Handle": ("base", 4), "Flat Base": ("base", 3), "Double Bottom": ("base", 3),
    "High Tight Flag": ("base", 5), "Power Play": ("base", 4), "Ascending Base": ("base", 3),
    "Darvas Box": ("base", 3), "The Ledge": ("base", 3),
}
BASE_META.update(META_EXT)
STATUS_TO_CONFIRM = {"forming": "pending", "breakout": "confirmed", "failed": "failed"}
STAGE_LABEL = {1: "Stage 1 - basing", 2: "Stage 2 - advancing", 3: "Stage 3 - topping", 4: "Stage 4 - declining"}


from base_utils import Arr, _r, _prior_rise, _zigzag, _level_len, swings, fit, at, max_dev, rsi  # noqa: F401  (re-exported for tests)


# ----------------------------------------------------------------------------- the nine detectors
# Each returns None or {"pivot", "stop", "start", "depth"(%), "len", ...extras}. They only read candles 0..i.
def det_flat(a: Arr, i: int) -> Optional[dict]:
    lo = max(0, i - C.FLAT_MAX_BARS + 1)
    hs, ls = a.h[lo:i + 1][::-1], a.l[lo:i + 1][::-1]
    mx, mn = np.maximum.accumulate(hs), np.minimum.accumulate(ls)
    ok = (mx - mn) / mx <= C.FLAT_MAX_DEPTH / 100.0  # depth only grows as the window grows: True...True False...
    L = _level_len(a.c, i, int(ok.sum()), C.FLAT_MAX_DRIFT_PCT / 100.0)
    if L < C.FLAT_MIN_BARS:
        return None
    start = i - L + 1
    top, bot = float(mx[L - 1]), float(mn[L - 1])
    if _prior_rise(a, start, C.BASE_PRIOR_WINDOW) < C.FLAT_PRIOR_RISE_PCT / 100.0:
        return None
    return {"pivot": top, "stop": bot, "start": start, "depth": (top - bot) / top * 100, "len": L}


def det_ledge(a: Arr, i: int) -> Optional[dict]:
    lo = max(0, i - C.LEDGE_MAX_BARS + 1)
    hs, ls = a.h[lo:i + 1][::-1], a.l[lo:i + 1][::-1]
    mx, mn = np.maximum.accumulate(hs), np.minimum.accumulate(ls)
    L = _level_len(a.c, i, int(((mx - mn) / mx <= C.LEDGE_MAX_DEPTH / 100.0).sum()), C.LEDGE_MAX_DRIFT_PCT / 100.0)
    if L < C.LEDGE_MIN_BARS:
        return None
    start = i - L + 1
    top, bot = float(mx[L - 1]), float(mn[L - 1])
    w0 = max(0, i - C.LEDGE_WINDOW + 1)
    big = float(np.max(a.h[w0:i + 1]))
    if top < big * (1 - C.LEDGE_NEAR_HIGH_PCT / 100.0):
        return None
    if start - w0 < 5:
        return None
    run_hi = np.maximum.accumulate(a.h[w0:start])
    if float(((run_hi - a.l[w0:start]) / run_hi).max()) < C.LEDGE_PRIOR_PULLBACK_PCT / 100.0:
        return None  # a ledge is the last pause of a larger base: that base must have had a real peak-to-trough pullback
    if _prior_rise(a, start, C.BASE_PRIOR_WINDOW) < C.BASE_PRIOR_RISE_PCT / 100.0:
        return None
    vr = a.volr[start:i + 1]
    vr = vr[~np.isnan(vr)]
    if vr.size < L // 2 or float(np.mean(vr)) > 1.0:
        return None  # low-volume pause
    half = max(1, vr.size // 2)
    if float(np.mean(vr[half:])) > float(np.mean(vr[:half])):
        return None  # volume must shrink, not grow
    return {"pivot": top, "stop": bot, "start": start, "depth": (top - bot) / top * 100, "len": L}


def det_darvas(a: Arr, i: int) -> Optional[dict]:
    lo = max(0, i - C.DARVAS_MAX_BARS)
    t = lo + int(np.argmax(a.h[lo:i + 1]))  # box top candle: the highest high of the window
    if i - t < C.DARVAS_MIN_BARS or i - t < C.DARVAS_CONFIRM_BARS:
        return None
    top = float(a.h[t])
    if top < a.hh250[i] * (1 - C.DARVAS_NEAR_HIGH_PCT / 100.0):
        return None
    seg = a.l[t + 1:i + 1]
    b = t + 1 + int(np.argmin(seg))
    if i - b < C.DARVAS_CONFIRM_BARS:
        return None  # the bottom is only confirmed when 3 candles have failed to undercut it
    bot = float(a.l[b])
    if (top - bot) / top > C.DARVAS_MAX_HEIGHT / 100.0:
        return None
    return {"pivot": top, "stop": bot, "start": t, "depth": (top - bot) / top * 100, "len": i - t + 1}


def _flag(a: Arr, i: int, rise: float, rally_min: int, rally_max: int, flag_min: int, flag_max: int,
          max_pb: float) -> Optional[dict]:
    """Rally of `rise` within rally_max candles, then a flag of flag_min..flag_max candles pulling back <= max_pb."""
    lo = max(0, i - flag_max)
    p = lo + int(np.argmax(a.h[lo:i + 1]))  # the peak the flag hangs from
    fl = i - p
    if fl < flag_min or fl > flag_max:
        return None
    top = float(a.h[p])
    flag_low = float(np.min(a.l[p:i + 1]))
    if (top - flag_low) / top > max_pb / 100.0:
        return None
    a0 = p - rally_max
    if a0 < 0:
        return None
    seg = a.l[a0:p - rally_min + 1]
    if seg.size == 0:
        return None
    low = float(seg.min())
    if low <= 0 or top / low - 1.0 < rise / 100.0:
        return None
    return {"pivot": top, "stop": flag_low, "start": p, "depth": (top - flag_low) / top * 100, "len": fl + 1,
            "rally_pct": (top / low - 1.0) * 100}


def det_htf(a: Arr, i: int) -> Optional[dict]:
    return _flag(a, i, C.HTF_RISE_PCT, C.HTF_RALLY_MIN, C.HTF_RALLY_MAX, C.HTF_FLAG_MIN, C.HTF_FLAG_MAX, C.HTF_MAX_PULLBACK)


def det_power_play(a: Arr, i: int) -> Optional[dict]:
    d = _flag(a, i, C.PP_RISE_PCT, C.PP_RALLY_MIN, C.PP_RALLY_MAX, C.PP_FLAG_MIN, C.PP_FLAG_MAX, C.PP_MAX_PULLBACK)
    if d is None or a.c[i] < a.hh250[i] * (1 - C.PP_NEAR_HIGH_PCT / 100.0):
        return None  # a Power Play is a market leader: it stays near its high
    return d


def det_double_bottom(a: Arr, i: int) -> Optional[dict]:
    s2 = max(0, i - 40 + 1)
    j2 = s2 + int(np.argmin(a.l[s2:i + 1]))  # second low: the lowest low of the last 40 candles
    if i - j2 < 3:
        return None  # not yet confirmed by 3 higher candles
    lo_a, lo_b = j2 - C.DB_LOW_GAP_MAX, j2 - C.DB_LOW_GAP_MIN
    if lo_a < 0 or lo_b <= lo_a:
        return None
    j1 = lo_a + int(np.argmin(a.l[lo_a:lo_b + 1]))  # first low: lowest low 15-60 candles before the second
    l1, l2 = float(a.l[j1]), float(a.l[j2])
    if j1 - C.DB_SWING_BARS < 0 or float(np.min(a.l[j1 - C.DB_SWING_BARS:j1])) < l1:
        return None  # the first low must be a swing low, not price passing through on its way up
    undercut = (l1 - l2) / l1 * 100
    if not (C.DB_UNDERCUT_MIN <= undercut <= C.DB_UNDERCUT_MAX):
        return None  # no undercut, or a deep one: lower quality, so no signal
    length = i - j1 + 1
    if not (C.DB_MIN_BARS <= length <= C.DB_MAX_BARS):
        return None
    if j2 - j1 < 2:
        return None
    mid = float(np.max(a.h[j1 + 1:j2]))  # the middle of the W
    if (mid / l1 - 1.0) * 100 < C.DB_PEAK_MIN_RISE:
        return None
    if _prior_rise(a, j1, C.BASE_PRIOR_WINDOW) < C.BASE_PRIOR_RISE_PCT / 100.0:
        return None
    return {"pivot": mid, "stop": l2, "start": j1, "depth": (mid - l2) / mid * 100, "len": length,
            "undercut_pct": undercut}


def det_cup(a: Arr, i: int) -> Optional[dict]:
    lo = max(0, i - C.HANDLE_MAX_BARS)
    r = lo + int(np.argmax(a.h[lo:i + 1]))  # right rim = start of the handle
    hl = i - r
    if hl < C.HANDLE_MIN_BARS or hl > C.HANDLE_MAX_BARS:
        return None
    rim_r = float(a.h[r])
    handle_low = float(np.min(a.l[r:i + 1]))
    if (rim_r - handle_low) / rim_r > C.HANDLE_MAX_PULLBACK / 100.0:
        return None
    w0 = r - C.CUP_MAX_BARS
    if w0 < 0:
        return None
    lr = w0 + int(np.argmax(a.h[w0:r - 2 * C.CUP_SIDE_MIN + 1]))  # left rim: highest high, at least 20 candles before the right rim
    cup_len = r - lr
    if cup_len < C.CUP_MIN_BARS:
        return None
    b = lr + 1 + int(np.argmin(a.l[lr + 1:r - C.CUP_SIDE_MIN + 1]))  # cup bottom: lowest low AFTER the left rim
    if b - lr < C.CUP_SIDE_MIN or r - b < C.CUP_SIDE_MIN:
        return None
    rim_l, bottom = float(a.h[lr]), float(a.l[b])
    depth = (rim_l - bottom) / rim_l * 100
    if not (C.CUP_DEPTH_MIN <= depth <= C.CUP_DEPTH_MAX):
        return None
    if rim_r < rim_l * (1 - C.CUP_RIM_RECOVERY / 100.0):
        return None
    rim = max(rim_l, rim_r)
    if rim <= bottom:
        return None
    u = (float(np.mean(a.c[lr:r + 1])) - bottom) / (rim - bottom)
    if u > C.CUP_U_MEAN_MAX:
        return None  # V-shaped, not a rounded cup
    if handle_low < bottom + 0.5 * (rim - bottom):
        return None  # handle in the lower half of the cup: weaker, prone to failure
    if float(np.mean(a.v[r + 1:i + 1])) > float(np.mean(a.v[lr:r + 1])):
        return None  # the handle must dry up
    if _prior_rise(a, lr, C.BASE_PRIOR_WINDOW) < C.BASE_PRIOR_RISE_PCT / 100.0:
        return None
    return {"pivot": rim_r, "stop": handle_low, "start": lr, "depth": depth, "len": i - lr + 1, "handle_bars": hl}


def det_vcp(a: Arr, i: int) -> Optional[dict]:
    lo = max(0, i - C.VCP_MAX_BARS + 1)
    s = lo + int(np.argmax(a.h[lo:i + 1]))  # the base's left peak
    if i - s + 1 < C.VCP_MIN_BARS:
        return None
    zz = _zigzag(a.h, a.l, s, i, C.VCP_SWING_PCT / 100.0, "H")
    pairs = [(zz[k], zz[k + 1]) for k in range(0, len(zz) - 1, 2) if zz[k][2] == "H" and zz[k + 1][2] == "L"]
    if len(pairs) < 2:
        return None
    d = [(p[1] - t[1]) / p[1] * 100 for p, t in pairs]
    if any(d[k + 1] >= d[k] for k in range(len(d) - 1)):
        return None  # a later pullback bigger than (or equal to) the one before: selling is increasing
    if not (C.VCP_FIRST_MIN <= d[0] <= C.VCP_FIRST_MAX) or d[-1] > C.VCP_LAST_MAX:
        return None
    p_last, t_last = pairs[-1]
    first_vol = float(np.mean(a.v[s:pairs[0][1][0] + 1]))
    last_vol = float(np.mean(a.v[p_last[0]:i + 1]))
    if last_vol > first_vol:
        return None  # volume must shrink as the pullbacks shrink
    if _prior_rise(a, s, C.BASE_PRIOR_WINDOW) < C.BASE_PRIOR_RISE_PCT / 100.0:
        return None
    return {"pivot": p_last[1], "stop": t_last[1], "start": s, "depth": d[0], "len": i - s + 1,
            "contractions": [round(x, 1) for x in d]}


def det_ascending(a: Arr, i: int) -> Optional[dict]:
    s = max(0, i - C.ASC_MAX_BARS + 1)
    zz = _zigzag(a.h, a.l, s, i, C.ASC_SWING_PCT / 100.0, None)
    while zz and zz[0][2] != "H":
        zz = zz[1:]
    pairs = [(zz[k], zz[k + 1]) for k in range(0, len(zz) - 1, 2) if zz[k][2] == "H" and zz[k + 1][2] == "L"]
    if len(pairs) < C.ASC_MIN_PULLBACKS:
        return None
    step = 1 + C.ASC_LOW_STEP_PCT / 100.0
    run = 1  # longest run of valid steps that ends at the last pair
    for k in range(len(pairs) - 1, -1, -1):
        hi_, lo_ = pairs[k][0][1], pairs[k][1][1]
        dep = (hi_ - lo_) / hi_ * 100
        if not (C.ASC_PULLBACK_MIN <= dep <= C.ASC_PULLBACK_MAX):
            break
        if k < len(pairs) - 1 and not (pairs[k + 1][1][1] >= lo_ * step and pairs[k + 1][0][1] >= hi_):
            break
        run = len(pairs) - k
    if run < C.ASC_MIN_PULLBACKS:
        return None
    use = pairs[-run:]
    start = use[0][0][0]
    if not (C.ASC_MIN_BARS <= i - start + 1 <= C.ASC_MAX_BARS):
        return None
    last_low_idx, last_low = use[-1][1][0], use[-1][1][1]
    pivot = use[-1][0][1]
    if zz and zz[-1][2] == "H" and zz[-1][0] > last_low_idx:
        pivot = zz[-1][1]  # a higher high already printed after the last low
    if _prior_rise(a, start, C.BASE_PRIOR_WINDOW) < C.BASE_PRIOR_RISE_PCT / 100.0:
        return None
    return {"pivot": float(pivot), "stop": float(last_low), "start": start,
            "depth": max((p[0][1] - p[1][1]) / p[0][1] * 100 for p in use), "len": i - start + 1, "steps": run}


# name -> (detector, breakout volume ratio)
DETECTORS: Dict[str, Tuple[Callable[[Arr, int], Optional[dict]], str]] = {
    "VCP": (det_vcp, "std"), "Cup with Handle": (det_cup, "std"), "Flat Base": (det_flat, "easy"),
    "Double Bottom": (det_double_bottom, "std"), "High Tight Flag": (det_htf, "std"),
    "Power Play": (det_power_play, "easy"), "Ascending Base": (det_ascending, "std"),
    "Darvas Box": (det_darvas, "std"), "The Ledge": (det_ledge, "std"),
}
DETECTORS.update(DETECTORS_EXT)
# bearish / two-sided / warning candidates are normalised here: every candidate ends up with dir, up, dn, stop
def _norm(cand: Optional[dict]) -> Optional[dict]:
    if cand is None:
        return None
    if "dir" not in cand:                       # the first nine are bullish and return pivot / stop
        cand["dir"], cand["up"] = "bull", cand["pivot"]
    cand.setdefault("up", None)
    cand.setdefault("dn", None)
    cand.setdefault("stop", None)
    return cand


def _vol_need(kind: str) -> float:
    return {"std": C.BASE_BREAKOUT_VOL, "easy": C.BASE_BREAKOUT_VOL_EASY, "none": 0.0}[kind]


def _near_ok(b: dict, price: float) -> bool:
    """Is the price close enough to the trigger for the base to count as 'forming'?"""
    d, near = b["dir"], b.get("near", C.BASE_NEAR_PIVOT_PCT) / 100.0
    if d == "warn":
        return b["lower"] * 0.98 <= price <= b["upper"] * 1.02
    if d == "both":
        return b["dn"] * 0.99 <= price <= b["up"] * 1.01
    if d == "bull":
        return price >= b["up"] * (1 - near) and (b["stop"] is None or price >= b["stop"])
    return price <= b["dn"] * (1 + near) and (b["stop"] is None or price <= b["stop"])


def _fast(a: Arr, i: int) -> bool:
    """A 'fast break': the breakout candle is at least FAST_BREAK_ATR tall on at least FAST_BREAK_VOL volume."""
    return bool(i >= 1 and not np.isnan(a.atr[i - 1]) and a.h[i] - a.l[i] >= C.FAST_BREAK_ATR * a.atr[i - 1]
                and not np.isnan(a.volr[i]) and a.volr[i] >= C.FAST_BREAK_VOL)


# ----------------------------------------------------------------------------- the state machine
# Patterns whose stop (the handle / flag low) can deepen inside the allowed pullback: a close below the old stop only
# fails them when the shape no longer fits the rules. For every other pattern the base low IS the stop.
SOFT_STOP = {"Cup with Handle", "High Tight Flag", "Power Play", "Flags and Pennants"}
# speed filter: these only form near the highs of the last 130 candles; every other pattern is checked on every candle
NEAR_HIGH_ONLY = {"VCP", "Cup with Handle", "Flat Base", "Double Bottom", "High Tight Flag", "Power Play", "Ascending Base", "Darvas Box",
                  "The Ledge", "Rounding Bottom"}


# How many candles before the stored window the walk starts, per pattern: at least its longest window, so a decision at a
# given candle never depends on where the walk began (tests/test_bases.py checks this on random prices).
LEAD_BARS = {"Cup with Handle": 135, "Double Bottom": 125, "Rectangle": 155, "Diamond": 105, "Rounding Bottom": 255,
             "Wyckoff Accumulation": 125, "Bump and Run": 125, "Supply & Demand Zones": 90, "Triangles": 85, "Broadening Wedge": 85,
             "Three Pushes": 85, "Ascending Base": 85, "The Ledge": 85}


def run_detector(a: Arr, name: str, first: int) -> List[dict]:
    """Walk candles first..n-1 and return the events of one pattern: breakouts, failures and the base standing now.

    A base is "armed" on a candle when it stands there and the price is near its trigger. The NEXT candle decides: a close beyond
    the trigger on enough volume is a breakout, a close beyond the stop a failure. A close beyond the trigger on weak volume is not
    a breakout: the base stays forming (flagged low volume) and its trigger is whatever the base looks like on the new candle.
    Only the previous candle's base matters (plus which candle last ended a base), so the result barely depends on `first`.
    """
    det, vol_kind = DETECTORS[name]
    need = _vol_need(vol_kind) if vol_kind in ("std", "easy", "none") else C.BASE_BREAKOUT_VOL
    c, n, volr = a.c, a.n, a.volr
    gate = a.gate if name in NEAR_HIGH_ONLY else a.all_true
    soft = name in SOFT_STOP
    far = C.BASE_NEAR_PIVOT_PCT / 100.0
    armed: Optional[dict] = None
    last_end = -1
    out: List[dict] = []
    for i in range(first, n):
        cand, searched, lowvol = None, False, False
        if armed is not None:
            b = armed["base"]
            d, up, dn, stop = b["dir"], b["up"], b["dn"], b["stop"]
            vol_ok = need == 0 or (not np.isnan(volr[i]) and volr[i] >= need)
            beyond_up = d in ("bull", "both") and up is not None and c[i] > up
            beyond_dn = d in ("bear", "both") and dn is not None and c[i] < dn
            if (beyond_up or beyond_dn) and vol_ok:
                out.append({"status": "breakout", "bar": i, "base": b, "formed": armed["formed"], "bdir": "bull" if beyond_up else "bear",
                            "vol_x": None if np.isnan(volr[i]) else float(volr[i]), "fast": _fast(a, i)})
                last_end, armed = i, None
            elif stop is not None and ((d == "bull" and c[i] < stop) or (d == "bear" and c[i] > stop)):
                if soft:  # the handle / flag may legitimately deepen: it has only failed if the shape is gone
                    cand, searched = _norm(det(a, i)) if gate[i] else None, True
                if not soft or cand is None or cand["start"] <= last_end:
                    out.append({"status": "failed", "bar": i, "base": b, "formed": armed["formed"], "vol_x": None, "bdir": d})
                    last_end, armed = i, None
            elif beyond_up or beyond_dn:
                if (beyond_up and c[i] > up * (1 + far)) or (beyond_dn and c[i] < dn * (1 - far)):
                    last_end, armed = i, None          # ran away without volume: this base is over
                else:
                    lowvol = True                       # beyond the trigger on weak volume: still forming, flagged
        if not searched:
            cand = _norm(det(a, i)) if gate[i] else None
        if cand is not None and cand["depth"] < C.BASE_MIN_DEPTH_PCT:
            cand = None  # no real range: a price that never moves is not a base
        if cand is not None and cand["start"] > last_end and _near_ok(cand, c[i]):
            armed = {"base": cand, "formed": armed["formed"] if armed is not None else i, "lowvol": lowvol}
        else:
            armed = None  # shape lost (or price drifted away from the trigger): not forming any more
    # a breakout that falls straight back (or loses its stop) has failed
    for ev in out:
        if ev["status"] != "breakout":
            continue
        b, j0, bd = ev["base"], ev["bar"], ev["bdir"]
        lvl = b["up"] if bd == "bull" else b["dn"]
        stp = b["stop"] if b["dir"] == bd else (b["dn"] if bd == "bull" else b["up"])   # a two-sided base: the opposite boundary
        for j in range(j0 + 1, n):
            bad = (j - j0 <= C.BASE_FAIL_BARS and (c[j] < lvl if bd == "bull" else c[j] > lvl)) or \
                  (stp is not None and (c[j] < stp if bd == "bull" else c[j] > stp))
            if bad:
                ev["status"], ev["fail_bar"] = "failed", j   # the breakout keeps its candle; the failure is a second fact
                break
    if armed is not None:
        out.append({"status": "forming", "bar": armed["formed"], "base": armed["base"], "formed": armed["formed"],
                    "vol_x": None, "lowvol": bool(armed.get("lowvol")), "bdir": armed["base"]["dir"]})
    return out


# ----------------------------------------------------------------------------- Stage Analysis
def stage_reading(a: Arr) -> Optional[dict]:
    """Weinstein stage 1-4 from the 30-week (150-candle) average and its 20-candle slope."""
    i = a.n - 1
    k = C.STAGE_SLOPE_BARS
    ma = a.sma
    if i < C.STAGE_MA_BARS + 3 * k or np.isnan(ma[i]) or np.isnan(ma[i - k]) or np.isnan(ma[i - 3 * k]):
        return None
    thr = C.STAGE_SLOPE_PCT / 100.0

    def slope(j):
        return ma[j] / ma[j - k] - 1.0

    sl = slope(i)
    above = bool(a.c[i] > ma[i])
    if sl >= thr:
        stage = 2
    elif sl <= -thr and not above:
        stage = 4
    else:  # the average is flat, or falling slightly with price above it: topping if it was RISING earlier, basing if not
        was_rising = any(slope(j) >= thr for j in range(i - k, C.STAGE_MA_BARS + k - 1, -k))
        stage = 3 if was_rising else 1
    entry = None
    for s in range(0, C.STAGE_ENTRY_BARS):  # crossed above the average on volume, average no longer falling
        j = i - s
        if j >= 1 and a.c[j] > ma[j] and a.c[j - 1] <= ma[j - 1] and slope(j) >= -thr and \
                not np.isnan(a.volr[j]) and a.volr[j] >= C.BASE_BREAKOUT_VOL:
            entry = s
            break
    return {"stage": stage, "stage_label": STAGE_LABEL[stage], "ma_slope_pct": _r(sl * 100, 2),
            "price_vs_ma": "above" if above else "below", "stage2_entry_since": entry}


# ----------------------------------------------------------------------------- Base Count
def base_breakouts(a: Arr) -> Tuple[int, List[int]]:
    """-> (uptrend_start, completed-base breakout candles since then).

    The uptrend starts after the last close below the 150-candle average. A completed base = at least
    BASE_COUNT_BARS candles of consolidation (a high made early, depth <= BASE_COUNT_MAX_DEPTH) followed by a close above
    that high, with at least that many candles since the previous breakout.
    """
    n = a.n
    below = np.flatnonzero((a.c < a.sma) & ~np.isnan(a.sma))
    u = int(below[-1]) if below.size else -1
    W = C.BASE_COUNT_BARS
    out: List[int] = []
    last = u
    for j in range(max(u + 1, W + 1), n):
        if j - last <= W:
            continue
        hh = a.h[j - W:j]
        top = float(hh.max())
        if a.c[j] <= top or int(np.argmax(hh)) > int(0.6 * W):
            continue
        if (top - float(a.l[j - W:j].min())) / top > C.BASE_COUNT_MAX_DEPTH / 100.0:
            continue
        out.append(j)
        last = j
    return u, out


# ----------------------------------------------------------------------------- public API
def _first_candle(n: int, store_bars: int, name: Optional[str] = None) -> int:
    return max(P.MIN_CONTEXT, n - 1 - (store_bars + LEAD_BARS.get(name, C.BASE_LEAD_BARS)))


def _quality(a: Arr, name: str, b: dict, i: int) -> int:
    """0-100: how clean the shape is. Tight for its type (less deep than the pattern's limit) and drying-up volume. A heuristic."""
    limit = QUAL_DEPTH_MAX.get(name, 30.0)
    tight = 1.0 - min(1.0, max(0.0, b["depth"]) / limit)
    seg = a.volr[max(b["start"], 0):i + 1]
    seg = seg[~np.isnan(seg)]
    dry = float(np.clip(1.0 - seg.mean(), 0.0, 1.0)) if seg.size else 0.5
    return int(round(100 * (0.6 * tight + 0.4 * dry)))


# the depth (%) at which a base of this type is no longer "tight": the limit of its own rule
QUAL_DEPTH_MAX = {"VCP": 35, "Cup with Handle": 33, "Flat Base": 15, "Double Bottom": 35, "High Tight Flag": 25, "Power Play": 12,
                  "Ascending Base": 20, "Darvas Box": 15, "The Ledge": 10, "Triangles": 25, "Flags and Pennants": 30, "Wedges": 25,
                  "Rectangle": 25, "Diamond": 40, "Rounding Bottom": 50, "Broadening Wedge": 40, "Three Pushes": 30, "Bump and Run": 60,
                  "Ross Hook": 12, "Wyckoff Accumulation": 40, "Supply & Demand Zones": 12}
DIR_OUT = {"bull": "bull", "bear": "bear", "both": "neutral", "warn": "neutral"}


def _row_levels(ev: dict) -> Tuple[str, Optional[float], Optional[float], Optional[float]]:
    """-> (dir, pivot, pivot_lo, stop) of one event. For a breakout the pivot is the level that broke."""
    b, st, bd = ev["base"], ev["status"], ev.get("bdir")
    if b["dir"] == "warn":
        return "neutral", None, None, None
    if st == "forming":
        if b["dir"] == "both":
            return "neutral", b["up"], b["dn"], None
        return DIR_OUT[b["dir"]], (b["up"] if b["dir"] == "bull" else b["dn"]), None, b["stop"]
    if st == "failed" and ev.get("fail_bar") is None:           # failed before it ever broke
        return DIR_OUT[b["dir"]], (b["up"] if b["dir"] == "bull" else b["dn"]), (b["dn"] if b["dir"] == "both" else None), b["stop"]
    d = "bull" if bd == "bull" else "bear"                      # broke out (and maybe failed afterwards)
    pivot = b["up"] if d == "bull" else b["dn"]
    stop = b["stop"] if b["dir"] == d else (b["dn"] if d == "bull" else b["up"])
    return d, pivot, None, stop


def base_signals(x: P.Candles, store_bars: int, a: Optional[Arr] = None, date_fmt: Optional[str] = None) -> List[dict]:
    """All base signals of one stock (no score yet; signals.analyze adds it). Never raises for odd data."""
    if not C.BASE_ON or x.n < P.MIN_CONTEXT + 20:
        return []
    a = a or Arr(x)
    fmt = date_fmt or C.DAILY_DATE_FMT
    u, brk = base_breakouts(a) if not np.isnan(a.sma[-1]) else (-1, None)
    out: List[dict] = []
    darvas_prev, darvas_no = -10_000, 0
    for name in DETECTORS:
        events = run_detector(a, name, _first_candle(a.n, store_bars, name))
        events.sort(key=lambda e: e["bar"])
        for ev in events:
            i, b, status = ev["bar"], ev["base"], ev["status"]
            since = a.n - 1 - i
            if status != "forming" and since >= store_bars:
                continue   # breakouts / failures live in the stored window 0..store_bars-1; a base still forming may be older
            d, pivot, pivot_lo, stop = _row_levels(ev)
            row = {
                "name": name, "group": "base", "dir": d, "len": int(b["len"]), "stars": BASE_META[name][1],
                "stop": _r(stop), "since": since, "time": a.x.times[i].strftime(fmt),
                "price": _r(a.c[i]), "vol": _r(a.volr[i], 2), "confirm": STATUS_TO_CONFIRM[status],
                "status": status, "pivot": _r(pivot), "depth": _r(b["depth"], 1), "formed": a.n - 1 - ev["formed"],
                "quality": _quality(a, name, b, i),
            }
            if b["dir"] == "warn":
                row["warn"] = True
                row["upper"], row["lower"] = _r(b["upper"]), _r(b["lower"])
            if pivot_lo is not None:
                row["pivot_lo"] = _r(pivot_lo)
            if b.get("variant"):
                row["variant"] = b["variant"]
            if b.get("move") and pivot is not None and d in ("bull", "bear"):
                row["target"] = _r(pivot + b["move"] if d == "bull" else pivot - b["move"])
            if ev.get("vol_x") is not None:
                row["vol_x"] = _r(ev["vol_x"], 2)
            if ev.get("fast"):
                row["fast"] = True
            if "fail_bar" in ev:
                row["fail_since"] = a.n - 1 - ev["fail_bar"]
            if ev.get("lowvol"):
                row["lowvol"] = True
            if brk is not None:
                row["base_no"] = 1 + sum(1 for j in brk if u < j < b["start"])
                row["climactic"] = bool(_prior_rise(a, b["start"], C.CLIMAX_WINDOW) >= C.CLIMAX_RISE_PCT / 100.0)
            for k in ("contractions", "handle_bars", "undercut_pct", "rally_pct", "steps", "pole_pct", "r2"):
                if k in b:
                    row[k] = b[k]
            if name == "Darvas Box":
                row["box_no"] = darvas_no = (darvas_no + 1) if b["start"] - darvas_prev <= 30 else 1
                if status == "breakout":
                    darvas_prev = i
            out.append(row)
    return out


def base_context(x: P.Candles, a: Optional[Arr] = None) -> dict:
    """Stage Analysis, Base Count and the two numbers the Base Rank needs (6-month return, turnover). Information only."""
    if not C.BASE_ON:
        return {}
    a = a or Arr(x)
    ctx: dict = {}
    st = stage_reading(a)
    if st:
        ctx.update(st)
    if not np.isnan(a.sma[-1]):
        u, brk = base_breakouts(a)
        ctx["base_count"] = len(brk)
        ctx["base_next"] = len(brk) + 1
        ctx["uptrend_bars"] = a.n - 1 - u if u >= 0 else a.n
        ctx["climactic"] = bool(_prior_rise(a, a.n - 1, C.CLIMAX_WINDOW) >= C.CLIMAX_RISE_PCT / 100.0)
    if a.n > C.RS_BARS and a.c[-1 - C.RS_BARS] > 0:
        ctx["ret_6m"] = _r((a.c[-1] / a.c[-1 - C.RS_BARS] - 1.0) * 100, 1)
    tb = min(C.TURNOVER_BARS, a.n)
    if tb >= 5:
        ctx["turnover_cr"] = _r(float(np.mean(a.c[-tb:] * a.v[-tb:])) / 1e7, 2)    # average value traded per candle, in Rs crore
    return ctx
