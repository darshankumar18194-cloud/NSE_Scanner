"""The 12 further base patterns. Same contract as the first nine (see bases.py): every detector `det_*(a, i)` looks ONLY at
candles 0..i and answers "is a complete base standing at candle i?". It returns None or a candidate dict:

    dir     "bull" | "bear" | "both" (decided by which side breaks) | "warn" (a warning, no trade level)
    up      price a close above which is the bullish trigger   (bull, both)
    dn      price a close below which is the bearish trigger   (bear, both)
    stop    stop reference (bull: below, bear: above). For "both" the stop is the opposite boundary.
    start   first candle of the base         depth  % depth / width          len  candles
    move    optional measured-move distance (box height, flagpole ...): the row's `target` = level +- move
    near    optional "forming" band in %, default BASE_NEAR_PIVOT_PCT
    variant optional sub-type shown on the row (Ascending, Falling, Demand ...)

Everything is counted in candles of the timeframe being scanned: on 1D a "20 candle" triangle lasts a month, on 1H about
three trading days. Thresholds are in config.py. Trendline shapes (Triangles, Wedges, Diamond, Broadening, Bump and Run)
depend on fitted lines and are the noisiest of all: expect false signals.
"""
from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple

import numpy as np

import config as C
from base_utils import Arr, _prior_rise, at, fit, max_dev, swings


# ----------------------------------------------------------------------------- Triangles
SW_WIN = 80   # one swing computation per candle (window 80) is shared by Triangles, Wedges, Broadening Wedge and Three Pushes


LENS = (80, 60, 45, 35, 25, 20)   # window lengths tried (longest first); Triangles use all, Wedges 60 and below


def _lengths(lo: int, hi: int):
    return [L for L in LENS if lo <= L <= hi]


def _lines_at(a: Arr, i: int, L: int):
    """Two straight lines through the swing highs / lows of the last L candles, or None. Cached: Triangles and Wedges share it."""
    cache = a.__dict__.setdefault("_linec", {})
    key = (i, L)
    if key in cache:
        return cache[key]
    hi_all, lo_all = swings(a, max(0, i - SW_WIN + 1), i, C.TRI_SWING_PCT / 100.0)
    s = i - L + 1
    hi, lo = [p for p in hi_all if p[0] >= s], [p for p in lo_all if p[0] >= s]
    res = None
    if len(hi) >= 2 and len(lo) >= 2:
        first = min(hi[0][0], lo[0][0])
        fu, fl = fit(hi), fit(lo)
        tol = C.TRI_TOUCH_TOL / 100.0
        if fu is not None and fl is not None and max_dev(hi, fu) <= tol and max_dev(lo, fl) <= tol:
            up0, up1, lo0, lo1 = at(fu, first), at(fu, i), at(fl, first), at(fl, i)
            if up0 > 0 and lo0 > 0 and up0 - lo0 > 0 and up1 - lo1 > 0:
                res = {"first": first, "up0": up0, "up1": up1, "lo0": lo0, "lo1": lo1,
                       "chg_u": (up1 - up0) / up0 * 100, "chg_l": (lo1 - lo0) / lo0 * 100}
    cache[key] = res
    return res


def _two_lines(a: Arr, i: int, min_bars: int, max_bars: int):
    """The lines on the longest window (min_bars..max_bars) where both fit and the pattern is at least min_bars long."""
    for L in _lengths(min_bars, max_bars):
        t = _lines_at(a, i, L)
        if t is not None and i - t["first"] + 1 >= min_bars:
            return t
    return None


def det_triangle(a: Arr, i: int) -> Optional[dict]:
    t = _two_lines(a, i, C.TRI_MIN_BARS, C.TRI_MAX_BARS)
    if t is None:
        return None
    gap0, gap1 = t["up0"] - t["lo0"], t["up1"] - t["lo1"]
    if gap1 > C.TRI_SHRINK * gap0:
        return None  # the lines must converge
    if not (t["lo1"] * 0.99 <= a.c[i] <= t["up1"] * 1.01):
        return None
    flat, slope = C.TRI_FLAT_PCT, C.TRI_SLOPE_PCT
    base = {"start": t["first"], "depth": gap0 / t["up0"] * 100, "len": i - t["first"] + 1, "move": gap0}
    if abs(t["chg_u"]) <= flat and t["chg_l"] >= slope:
        return {**base, "dir": "bull", "variant": "Ascending", "up": t["up1"], "stop": t["lo1"]}
    if abs(t["chg_l"]) <= flat and t["chg_u"] <= -slope:
        return {**base, "dir": "bear", "variant": "Descending", "dn": t["lo1"], "stop": t["up1"]}
    if t["chg_u"] <= -slope and t["chg_l"] >= slope:
        return {**base, "dir": "both", "variant": "Symmetrical", "up": t["up1"], "dn": t["lo1"]}
    return None


# ----------------------------------------------------------------------------- Wedges
def det_wedge(a: Arr, i: int) -> Optional[dict]:
    t = _two_lines(a, i, C.WEDGE_MIN_BARS, C.WEDGE_MAX_BARS)
    if t is None:
        return None
    gap0, gap1 = t["up0"] - t["lo0"], t["up1"] - t["lo1"]
    if gap1 > C.WEDGE_SHRINK * gap0 or not (t["lo1"] * 0.99 <= a.c[i] <= t["up1"] * 1.01):
        return None
    s = C.WEDGE_SLOPE_PCT
    base = {"start": t["first"], "depth": gap0 / t["up0"] * 100, "len": i - t["first"] + 1, "move": gap0}
    if t["chg_u"] >= s and t["chg_l"] >= s:      # both lines rising, converging: bearish
        return {**base, "dir": "bear", "variant": "Rising", "dn": t["lo1"], "stop": t["up1"]}
    if t["chg_u"] <= -s and t["chg_l"] <= -s:    # both falling, converging: bullish
        return {**base, "dir": "bull", "variant": "Falling", "up": t["up1"], "stop": t["lo1"]}
    return None


# ----------------------------------------------------------------------------- Flags and Pennants
def _flag_dir(a: Arr, i: int, sgn: int) -> Optional[dict]:
    lo = max(0, i - 60)
    p = lo + int(np.argmax(a.h[lo:i + 1])) if sgn > 0 else lo + int(np.argmin(a.l[lo:i + 1]))   # the peak must be the extreme of the last 60 candles
    fl = i - p
    if fl < C.FLAG_MIN_BARS or fl > C.FLAG_MAX_BARS:
        return None
    a0 = p - C.FLAG_POLE_MAX_BARS
    if a0 < 0:
        return None
    if sgn > 0:
        ext = float(a.h[p])
        seg = a.l[a0:p - C.FLAG_POLE_MIN_BARS + 1]
        pole_bar = a0 + int(np.argmin(seg))
        start = float(seg.min())
        pole = ext - start
        flag_ext = float(a.l[p:i + 1].min())
        retrace = (ext - flag_ext) / pole if pole > 0 else 9.0
    else:
        ext = float(a.l[p])
        seg = a.h[a0:p - C.FLAG_POLE_MIN_BARS + 1]
        pole_bar = a0 + int(np.argmax(seg))
        start = float(seg.max())
        pole = start - ext
        flag_ext = float(a.h[p:i + 1].max())
        retrace = (flag_ext - ext) / pole if pole > 0 else 9.0
    if seg.size == 0 or start <= 0 or pole <= 0:
        return None
    if pole / start * 100 / max(1, p - pole_bar) < C.FLAG_POLE_MIN_SPEED:
        return None                                              # too slow to be a pole
    pole_pct = pole / start * 100
    if not (C.FLAG_POLE_MIN_PCT <= pole_pct <= C.FLAG_POLE_MAX_PCT) or retrace > C.FLAG_MAX_RETRACE / 100.0:
        return None
    xs = np.arange(p, i + 1)
    ref = float(np.mean(a.c[p:i + 1]))
    dh = np.polyfit(xs, a.h[p:i + 1], 1)[0] * fl / ref * 100   # how far each edge of the flag travels over the flag, in %
    dl = np.polyfit(xs, a.l[p:i + 1], 1)[0] * fl / ref * 100
    parallel = abs(dh - dl) <= C.FLAG_PARALLEL_PCT and ((dh <= 1 and dl <= 1) if sgn > 0 else (dh >= -1 and dl >= -1))
    half = p + fl // 2
    r1 = float(a.h[p:half + 1].max() - a.l[p:half + 1].min())
    r2 = float(a.h[half:i + 1].max() - a.l[half:i + 1].min())
    converge = r1 > 0 and r2 <= C.FLAG_PENNANT_RATIO * r1 and dh <= 0.5 and dl >= -0.5 if sgn > 0 else r1 > 0 and r2 <= C.FLAG_PENNANT_RATIO * r1 and dl >= -0.5 and dh <= 0.5
    if not (parallel or converge):
        return None
    base = {"start": p, "depth": retrace * pole_pct, "len": fl + 1, "move": pole, "pole_pct": pole_pct,
            "variant": "Pennant" if converge else "Flag", "stop": flag_ext}
    return {**base, "dir": "bull", "up": ext} if sgn > 0 else {**base, "dir": "bear", "dn": ext}


def det_flag(a: Arr, i: int) -> Optional[dict]:
    return _flag_dir(a, i, 1) or _flag_dir(a, i, -1)


# ----------------------------------------------------------------------------- Rectangle
def det_rectangle(a: Arr, i: int) -> Optional[dict]:
    tol = C.RECT_TOUCH_TOL / 100.0
    s0 = i - C.RECT_MIN_BARS + 1
    if s0 < 0 or (a.h[s0:i + 1].max() - a.l[s0:i + 1].min()) / a.h[s0:i + 1].max() * 100 > C.RECT_MAX_HEIGHT:
        return None            # even the shortest box would be too tall (a longer window only gets taller)
    swc = None
    for L in (150, 120, 90, 60, 40, 25):
        if not (C.RECT_MIN_BARS <= L <= C.RECT_MAX_BARS):
            continue
        s = i - L + 1
        if s < 0:
            continue
        top, bot = float(a.h[s:i + 1].max()), float(a.l[s:i + 1].min())
        height = (top - bot) / top * 100
        if not (C.RECT_MIN_HEIGHT <= height <= C.RECT_MAX_HEIGHT):
            continue
        if swc is None:        # the swing analysis is only done once a window has the right height
            swc = swings(a, max(0, i - C.RECT_MAX_BARS + 1), i, C.RECT_SWING_PCT / 100.0)
        hi_all, lo_all = swc
        if sum(1 for k, p in hi_all if k >= s and p >= top * (1 - tol)) < C.RECT_TOUCHES or \
                sum(1 for k, p in lo_all if k >= s and p <= bot * (1 + tol)) < C.RECT_TOUCHES:
            continue
        if float(a.c[s:i + 1].max()) > top * (1 + C.RECT_CLOSE_TOL / 100.0) or float(a.c[s:i + 1].min()) < bot * (1 - C.RECT_CLOSE_TOL / 100.0):
            continue
        return {"dir": "both", "up": top, "dn": bot, "start": s, "depth": height, "len": L, "move": top - bot}
    return None


# ----------------------------------------------------------------------------- Diamond
def det_diamond(a: Arr, i: int) -> Optional[dict]:
    cs = a.__dict__.get("_rngcs")
    if cs is None:
        cs = a._rngcs = np.concatenate([[0.0], np.cumsum(np.nan_to_num(a.h - a.l))])
    for L in (100, 80, 60, 40):
        if not (C.DIAMOND_MIN_BARS <= L <= C.DIAMOND_MAX_BARS):
            continue
        q = L // 4
        s = i + 1 - 4 * q
        if s < 0:
            continue
        v = [float(cs[s + (k + 1) * q] - cs[s + k * q]) / q for k in range(4)]   # average candle range of each quarter
        widest = max(v[1], v[2])
        if v[0] <= 0 or v[1] < C.DIAMOND_WIDEN * v[0] or v[2] < C.DIAMOND_WIDEN * v[0] or v[3] > C.DIAMOND_NARROW * widest:
            continue
        swing = float(a.h[s:i + 1].max() - a.l[s:i + 1].min())
        if abs(a.c[i] - a.c[s]) > C.DIAMOND_DRIFT * swing or swing / float(a.c[i]) < 0.06:
            continue                                             # a trend followed by calm is not a diamond
        last = slice(s + 3 * q, i + 1)
        up, dn = float(a.h[last].max()), float(a.l[last].min())
        if not (dn <= a.c[i] <= up):
            continue
        return {"dir": "both", "up": up, "dn": dn, "start": s, "depth": swing / up * 100, "len": 4 * q, "move": swing}
    return None


# ----------------------------------------------------------------------------- Rounding Bottom / Saucer
def det_round(a: Arr, i: int) -> Optional[dict]:
    lo = max(0, i - C.ROUND_MAX_BARS + 1)
    hi_end = i - C.ROUND_MIN_BARS + 1
    if hi_end <= lo:
        return None
    lr = lo + int(np.argmax(a.h[lo:hi_end + 1]))                # where the saucer begins: the left rim
    L = i - lr + 1
    rim = float(a.h[lr])
    b = lr + int(np.argmin(a.l[lr:i + 1]))
    bottom = float(a.l[b])
    depth = (rim - bottom) / rim * 100
    if not (C.ROUND_DEPTH_MIN <= depth <= C.ROUND_DEPTH_MAX):
        return None
    pos = (b - lr) / max(1, L - 1)
    if not (C.ROUND_BOTTOM_POS[0] <= pos <= C.ROUND_BOTTOM_POS[1]) or a.c[i] < rim * (1 - C.ROUND_RIM_RECOVERY / 100.0):
        return None
    y = a.c[lr:i + 1]
    coef = np.polyfit(np.arange(L), y, 2)
    if coef[0] <= 0:
        return None                                              # must curve upward: a U
    rim_c = max(float(y[0]), float(y[-1]))
    if rim_c <= bottom or (float(y.mean()) - bottom) / (rim_c - bottom) > C.ROUND_U_MEAN_MAX:
        return None                                              # V-shaped: not a rounded saucer
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - float(((y - np.polyval(coef, np.arange(L))) ** 2).sum()) / ss_tot if ss_tot > 0 else 0.0
    if r2 < C.ROUND_R2:
        return None
    stop = float(a.l[max(lr, i - 19):i + 1].min())
    return {"dir": "bull", "up": rim, "stop": stop, "start": lr, "depth": depth, "len": L, "move": rim - bottom, "r2": round(r2, 2)}


# ----------------------------------------------------------------------------- Broadening Wedge (a warning, not a setup)
def det_broaden(a: Arr, i: int) -> Optional[dict]:
    hi_all, lo_all = swings(a, max(0, i - SW_WIN + 1), i, C.TRI_SWING_PCT / 100.0)
    step = 1 + C.BROAD_STEP_PCT / 100.0
    for L in _lengths(C.BROAD_MIN_BARS, C.BROAD_MAX_BARS):
        s = i - L + 1
        hi, lo = [p for p in hi_all if p[0] >= s], [p for p in lo_all if p[0] >= s]
        if len(hi) < 2 or len(lo) < 2:
            continue
        first = min(hi[0][0], lo[0][0])
        if i - first + 1 < C.BROAD_MIN_BARS:
            continue
        if any(hi[k + 1][1] < hi[k][1] * step for k in range(len(hi) - 1)) or any(lo[k + 1][1] > lo[k][1] / step for k in range(len(lo) - 1)):
            continue                                             # higher highs AND lower lows
        fu, fl = fit(hi), fit(lo)
        if fu is None or fl is None:
            continue
        gap0, gap1 = at(fu, first) - at(fl, first), at(fu, i) - at(fl, i)
        if gap0 <= 0 or gap1 < C.BROAD_GROW * gap0 or not (at(fl, i) * 0.98 <= a.c[i] <= at(fu, i) * 1.02):
            continue
        return {"dir": "warn", "upper": at(fu, i), "lower": at(fl, i), "start": first, "depth": gap1 / at(fu, i) * 100, "len": i - first + 1}
    return None


# ----------------------------------------------------------------------------- Three Pushes
def det_pushes(a: Arr, i: int) -> Optional[dict]:
    hi, lo = swings(a, max(0, i - SW_WIN + 1), i, C.TRI_SWING_PCT / 100.0)
    step = C.PUSH_STEP_PCT / 100.0
    r = a.rsi
    if len(hi) >= 3:                                             # three higher highs, each on weaker RSI: exhaustion
        (k1, p1), (k2, p2), (k3, p3) = hi[-3:]
        if p2 >= p1 * (1 + step) and p3 >= p2 * (1 + step) and i - k1 + 1 >= C.PUSH_MIN_BARS and i - k3 <= C.PUSH_RECENT \
                and not np.isnan(r[[k1, k2, k3]]).any() and r[k1] > r[k2] > r[k3]:
            trig = float(a.l[k2:k3 + 1].min())                   # the pullback low between pushes 2 and 3
            if a.c[i] > trig:
                return {"dir": "bear", "dn": trig, "stop": p3, "start": k1, "depth": (p3 - trig) / p3 * 100, "len": i - k1 + 1, "variant": "Three Pushes up"}
    if len(lo) >= 3:                                             # three lower lows, each on stronger RSI
        (k1, p1), (k2, p2), (k3, p3) = lo[-3:]
        if p2 <= p1 / (1 + step) and p3 <= p2 / (1 + step) and i - k1 + 1 >= C.PUSH_MIN_BARS and i - k3 <= C.PUSH_RECENT \
                and not np.isnan(r[[k1, k2, k3]]).any() and r[k1] < r[k2] < r[k3]:
            trig = float(a.h[k2:k3 + 1].max())
            if a.c[i] < trig:
                return {"dir": "bull", "up": trig, "stop": p3, "start": k1, "depth": (trig - p3) / trig * 100, "len": i - k1 + 1, "variant": "Three Pushes down"}
    return None


# ----------------------------------------------------------------------------- Bump and Run (topping)
def det_bump(a: Arr, i: int) -> Optional[dict]:
    lo = max(0, i - 120)
    p = lo + int(np.argmax(a.h[lo:i + 1]))                       # the peak of the bump
    if not (3 <= i - p <= 40) or p - C.BUMP_MAX_BARS - C.BUMP_LEAD_BARS < 0:
        return None
    if a.h[p] < (1 + C.BUMP_HEIGHT_PCT / 100.0) * float(a.l[p - C.BUMP_MAX_BARS - C.BUMP_LEAD_BARS:p - C.BUMP_MIN_BARS].min()):
        return None                                              # the peak is not even 20% above the lead-in: no bump
    for bump in (30, 25, 20, 15, 10):                            # the bump begins `bump` candles before the peak
        if not (C.BUMP_MIN_BARS <= bump <= C.BUMP_MAX_BARS):
            continue
        end = p - bump
        ls = end - C.BUMP_LEAD_BARS
        if ls < 0:
            continue
        m, b0 = np.polyfit(np.arange(ls, end + 1), a.l[ls:end + 1], 1)   # the lead-in trendline
        line_p, line_i = m * p + b0, m * i + b0
        if m <= 0 or line_p <= 0 or line_i <= 0:
            continue
        if (a.h[p] - line_p) / line_p * 100 < C.BUMP_HEIGHT_PCT:
            continue
        if (a.c[p] - a.c[end]) / bump < C.BUMP_STEEP * m:
            continue
        if a.c[i] > line_i and a.c[i] <= line_i * (1 + C.BUMP_NEAR_PCT / 100.0):
            return {"dir": "bear", "dn": float(line_i), "stop": float(a.h[p]), "start": ls, "depth": (a.h[p] - line_p) / line_p * 100,
                    "len": i - ls + 1, "near": C.BUMP_NEAR_PCT}
    return None


# ----------------------------------------------------------------------------- Ross Hook
def _hook_dir(a: Arr, i: int, sgn: int) -> Optional[dict]:
    for k in range(1, C.HOOK_BARS_MAX + 1):                      # k candles of hook after point 3
        c3 = i - k
        s = max(0, c3 - C.HOOK_LOOKBACK)
        if c3 - 3 <= s:
            return None
        if sgn > 0:
            if a.h[c3 + 1:i + 1].max() >= a.h[c3] or a.h[c3] < a.h[c3 - 3:c3].max():
                continue                                         # point 3 must be a high with a hook of lower highs after it
            p1 = s + int(np.argmax(a.h[s:c3 - 2]))
            p2 = p1 + int(np.argmin(a.l[p1:c3])) if c3 > p1 else p1
            if p2 <= p1 or (a.h[p1] - a.l[p2]) / a.h[p1] * 100 < C.HOOK_PULLBACK_PCT or a.h[c3] < a.h[p1] * (1 - C.HOOK_TEST_PCT / 100.0):
                continue
            if _prior_rise(a, p1, 60) < C.HOOK_PRIOR_RISE_PCT / 100.0:
                continue
            level, stop = float(a.h[c3 + 1:i + 1].max()), float(a.l[c3 + 1:i + 1].min())
            return {"dir": "bull", "up": level, "stop": stop, "start": p1, "depth": (a.h[p1] - a.l[p2]) / a.h[p1] * 100, "len": i - p1 + 1, "variant": "Bullish hook"}
        if a.l[c3 + 1:i + 1].min() <= a.l[c3] or a.l[c3] > a.l[c3 - 3:c3].min():
            continue
        p1 = s + int(np.argmin(a.l[s:c3 - 2]))
        p2 = p1 + int(np.argmax(a.h[p1:c3])) if c3 > p1 else p1
        if p2 <= p1 or (a.h[p2] - a.l[p1]) / a.h[p2] * 100 < C.HOOK_PULLBACK_PCT or a.l[c3] > a.l[p1] * (1 + C.HOOK_TEST_PCT / 100.0):
            continue
        lo60 = max(0, p1 - 60)
        top = float(a.h[lo60:p1 + 1].max())
        if (top - a.l[p1]) / top * 100 < C.HOOK_PRIOR_RISE_PCT:
            continue
        level, stop = float(a.l[c3 + 1:i + 1].min()), float(a.h[c3 + 1:i + 1].max())
        return {"dir": "bear", "dn": level, "stop": stop, "start": p1, "depth": (a.h[p2] - a.l[p1]) / a.h[p2] * 100, "len": i - p1 + 1, "variant": "Bearish hook"}
    return None


def det_hook(a: Arr, i: int) -> Optional[dict]:
    return _hook_dir(a, i, 1) or _hook_dir(a, i, -1)


# ----------------------------------------------------------------------------- Wyckoff Accumulation (simplified: range + Spring)
def det_wyckoff(a: Arr, i: int) -> Optional[dict]:
    lo = max(0, i - 20)
    sp = lo + int(np.argmin(a.l[lo:i + 1]))                      # the Spring is the lowest low of the last 20 candles
    last = min(sp + C.SPRING_RECLAIM_BARS, i)
    if not (a.c[sp:last + 1] >= 0).any() or sp < C.WYCKOFF_MIN_BARS:
        return None
    for L in (30, 45, 60, 90, 120):                              # the shortest range that fits: its top is the pivot
        if not (C.WYCKOFF_MIN_BARS <= L <= C.WYCKOFF_MAX_BARS):
            continue
        s = sp - L
        if s < 0:
            continue
        support, res = float(a.l[s:sp].min()), float(a.h[s:sp].max())
        height = (res - support) / res * 100
        if not (C.WYCKOFF_HEIGHT_MIN <= height <= C.WYCKOFF_HEIGHT_MAX):
            continue
        under = (support - a.l[sp]) / support * 100
        if not (C.SPRING_UNDERCUT_MIN <= under <= C.SPRING_UNDERCUT_MAX):
            continue                                             # the Spring dips under support by a small amount only
        if not (a.c[sp:last + 1] >= support).any() or a.c[i] < support:
            continue                                             # ... and closes back above support quickly
        top = float(a.h[max(0, s - 120):s + 1].max())
        if (top - support) / top * 100 < C.WYCKOFF_PRIOR_FALL:
            continue                                             # accumulation follows a decline
        if float(np.mean(a.v[max(sp - 5, s):i + 1])) > float(np.mean(a.v[s:sp])):
            continue                                             # supply is drying up
        return {"dir": "bull", "up": res, "stop": float(a.l[sp]), "start": s, "depth": height, "len": i - s + 1, "move": res - support,
                "near": C.WYCKOFF_NEAR_PCT}
    return None


# ----------------------------------------------------------------------------- Supply & Demand zones
def _zones(a: Arr):
    """Every (base_end, zone_low, zone_high, 'up'|'down') in the series: a tight base followed by a strong move away.
    Uses candles up to base_end+3 only, so a zone is only ever used once those candles are closed. `imp` = size of the move away."""
    if getattr(a, "_zones", None) is not None:
        return a._zones
    out = []
    atr, h, l = a.atr, a.h, a.l
    rng = h - l
    for b in range(15, a.n - C.SD_IMPULSE_BARS):
        if np.isnan(atr[b]) or atr[b] <= 0:
            continue
        nb = 0
        while nb < C.SD_BASE_MAX_BARS and b - nb >= 0 and rng[b - nb] <= C.SD_BASE_RANGE_ATR * atr[b]:
            nb += 1
        if nb == 0:
            continue
        bh, bl = float(h[b - nb + 1:b + 1].max()), float(l[b - nb + 1:b + 1].min())
        nxt_h, nxt_l = h[b + 1:b + 1 + C.SD_IMPULSE_BARS], l[b + 1:b + 1 + C.SD_IMPULSE_BARS]
        if h[b + 1] > bh and nxt_h.max() - bh >= C.SD_IMPULSE_ATR * atr[b] and nxt_l.min() >= bl - 0.3 * atr[b]:
            out.append((b, bl, bh, "up", float(nxt_h.max() - bh)))
        elif l[b + 1] < bl and bl - nxt_l.min() >= C.SD_IMPULSE_ATR * atr[b] and nxt_h.max() <= bh + 0.3 * atr[b]:
            out.append((b, bl, bh, "down", float(bl - nxt_l.min())))
    a._zones = out
    return out


def det_sd(a: Arr, i: int) -> Optional[dict]:
    if i < 3 or np.isnan(a.atr[i]) or float(np.mean(a.h[i - 2:i + 1] - a.l[i - 2:i + 1])) > C.SD_COMPRESS_ATR * a.atr[i]:
        return None                                              # no mini-compression right now
    for b, zl, zh, kind, imp in reversed(_zones(a)):
        if b > i - C.SD_RETURN_MIN:
            continue
        if b < i - C.SD_LOOKBACK:
            break
        seg_l, seg_h = a.l[b + 4:i + 1], a.h[b + 4:i + 1]
        if seg_l.size == 0:
            continue
        hit = np.flatnonzero(seg_l <= zh) if kind == "up" else np.flatnonzero(seg_h >= zl)
        if hit.size == 0:
            continue
        t = b + 4 + int(hit[0])                                  # the first return into the zone
        if not (C.SD_RETURN_MIN <= t - b <= C.SD_RETURN_MAX) or i - t > 5:
            continue
        if kind == "up" and float(a.c[t:i + 1].min()) < zl:
            continue                                             # a close under the zone breaks it
        if kind == "down" and float(a.c[t:i + 1].max()) > zh:
            continue
        if kind == "up":
            level = float(a.h[i - 2:i + 1].max())
            return {"dir": "bull", "up": level, "stop": zl, "start": b, "depth": imp / zh * 100, "len": i - b + 1, "variant": "Demand zone"}
        level = float(a.l[i - 2:i + 1].min())
        return {"dir": "bear", "dn": level, "stop": zh, "start": b, "depth": imp / zh * 100, "len": i - b + 1, "variant": "Supply zone"}
    return None


# name -> (detector, breakout volume kind: std = 1.4x, easy = 1.2x, none = any volume, warn = no trade level)
DETECTORS_EXT: Dict[str, Tuple[Callable[[Arr, int], Optional[dict]], str]] = {
    "Triangles": (det_triangle, "std"), "Flags and Pennants": (det_flag, "std"), "Wedges": (det_wedge, "std"),
    "Rectangle": (det_rectangle, "std"), "Diamond": (det_diamond, "std"), "Rounding Bottom": (det_round, "std"),
    "Broadening Wedge": (det_broaden, "std"), "Three Pushes": (det_pushes, "easy"), "Bump and Run": (det_bump, "easy"),
    "Ross Hook": (det_hook, "none"), "Wyckoff Accumulation": (det_wyckoff, "std"), "Supply & Demand Zones": (det_sd, "easy"),
}
META_EXT: Dict[str, Tuple[str, int]] = {
    "Triangles": ("base", 3), "Flags and Pennants": ("base", 3), "Wedges": ("base", 3), "Rectangle": ("base", 3),
    "Diamond": ("base", 2), "Rounding Bottom": ("base", 3), "Broadening Wedge": ("base", 2), "Three Pushes": ("base", 3),
    "Bump and Run": ("base", 3), "Ross Hook": ("base", 2), "Wyckoff Accumulation": ("base", 3), "Supply & Demand Zones": ("base", 2),
}
