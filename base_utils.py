"""Shared building blocks for the base-pattern detectors (bases.py, bases_ext.py): the per-stock arrays, swing points,
trendline fits, RSI. Nothing in here looks at a candle after the one being tested."""
from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

import config as C
import patterns as P

def _r(v, nd=4):
    try:
        if v is None or not np.isfinite(v):
            return None
        return round(float(v), nd)
    except (TypeError, ValueError):
        return None


class Arr:
    """OHLCV arrays + the few series every detector shares, computed once per stock."""

    def __init__(self, x: P.Candles):
        self.x = x
        self.n = x.n
        self.h, self.l, self.c, self.v, self.volr = x.h, x.l, x.c, x.v, x.volr
        self.o, self.atr = x.o, x.atr
        self._rsi = None
        hs = pd.Series(x.h)
        self.hh130 = hs.rolling(130, min_periods=1).max().to_numpy()
        self.hh250 = hs.rolling(C.DARVAS_HIGH_WINDOW, min_periods=1).max().to_numpy()
        cs = pd.Series(x.c)
        self.sma = cs.rolling(C.STAGE_MA_BARS).mean().to_numpy()  # NaN until 150 candles exist
        # candles whose close is too far below the recent high cannot be inside a forming base: skipped (speed)
        self.gate = x.c >= (1 - C.BASE_GATE_PCT / 100.0) * self.hh130
        self.all_true = np.ones(x.n, bool)

    @property
    def rsi(self) -> np.ndarray:
        if self._rsi is None:
            self._rsi = rsi(self.c)
        return self._rsi



def _prior_rise(a: Arr, end: int, win: int) -> float:
    """Advance INTO the highest high of the `win` candles ending at `end`: peak / (lowest low before the peak) - 1."""
    lo = max(0, end - win)
    seg_h = a.h[lo:end + 1]
    if seg_h.size < 5:
        return 0.0
    k = int(np.argmax(seg_h))
    low = float(np.min(a.l[lo:lo + k + 1]))
    return float(seg_h[k]) / low - 1.0 if low > 0 else 0.0


def _zigzag(h: np.ndarray, l: np.ndarray, s: int, e: int, pct: float, first: Optional[str] = "H",
            conf: Optional[list] = None) -> List[Tuple[int, float, str]]:
    """Confirmed swing points between candles s and e. A swing is confirmed once price has reversed by `pct`.

    first="H": candle s is a known swing high. first=None: the first swing is found automatically.
    A candle that makes a new extreme never confirms the opposite swing on the same candle (no look-ahead).
    If `conf` is a list, the candle on which each swing was confirmed is appended to it (same order as the result).
    """
    out: List[Tuple[int, float, str]] = []

    def emit(k, p, t, j):
        out.append((k, float(p), t))
        if conf is not None:
            conf.append(j)

    mode: Optional[str] = None  # "L" = tracking a low after a high, "H" = tracking a high after a low
    hi, hp, li, lp = s, h[s], s, l[s]
    if first == "H":
        emit(s, h[s], "H", s)
        mode, li, lp = "L", s, np.inf
    for j in range(s + 1, e + 1):
        if mode is None:  # find the first swing
            if h[j] > hp:
                hi, hp = j, h[j]
            elif hp > 0 and l[j] <= hp * (1 - pct) and hi < j:
                emit(hi, hp, "H", j)
                mode, li, lp = "L", j, l[j]
                continue
            if l[j] < lp:
                li, lp = j, l[j]
            elif lp > 0 and h[j] >= lp * (1 + pct) and li < j:
                emit(li, lp, "L", j)
                mode, hi, hp = "H", j, h[j]
            continue
        if mode == "L":
            if l[j] < lp:
                li, lp = j, l[j]
            elif li < j and h[j] >= lp * (1 + pct) and np.isfinite(lp):
                emit(li, lp, "L", j)
                mode, hi, hp = "H", j, h[j]
        else:
            if h[j] > hp:
                hi, hp = j, h[j]
            elif l[j] <= hp * (1 - pct):
                emit(hi, hp, "H", j)
                mode, li, lp = "L", j, l[j]
    return out


def _level_len(c: np.ndarray, i: int, max_len: int, drift: float) -> int:
    """Longest window ending at i, no longer than max_len, whose close barely moves from its first to its last candle."""
    if max_len <= 0:
        return 0
    starts = np.arange(i - max_len + 1, i + 1)  # window starts, longest first
    seg = c[i - max_len + 1:i + 1]
    means = np.cumsum(seg[::-1])[::-1] / np.arange(max_len, 0, -1)  # average close of each window
    ok = (np.abs(c[i] / c[starts] - 1.0) <= drift) & (c[starts] >= C.BASE_LEVEL_START_RATIO * means)
    k = np.flatnonzero(ok)
    return int(i - starts[k[0]] + 1) if k.size else 0




# ----------------------------------------------------------------------------- swing points, lines, RSI
def swings(a: "Arr", s: int, e: int, pct: float) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:
    """(highs, lows) = the confirmed swing points with candle index in s..e, as they stood on candle e: each (index, price).

    The swing points of the whole series are found ONCE in a single forward pass (the first swing found is dropped: it only
    marks where the data starts). Each carries the candle on which it was confirmed, so "the swings visible on candle e" is a
    filter and can never use a later candle."""
    cache = a.__dict__.setdefault("_pv", {})
    pv = cache.get(pct)
    if pv is None:
        conf: list = []
        zz = _zigzag(a.h, a.l, 0, a.n - 1, pct, None, conf)
        pv = cache[pct] = [(k, p, t, j) for (k, p, t), j in zip(zz, conf)][1:]
    return ([(k, p) for k, p, t, j in pv if t == "H" and s <= k and j <= e],
            [(k, p) for k, p, t, j in pv if t == "L" and s <= k and j <= e])


def fit(points: List[Tuple[int, float]]) -> Optional[Tuple[float, float]]:
    """Least-squares line through (index, price) points -> (slope per candle, intercept). Needs 2+ points.
    Closed form on plain floats: np.polyfit is ~30x slower on the handful of swing points this is used on."""
    n = len(points)
    if n < 2:
        return None
    sx = sy = sxx = sxy = 0.0
    for k, p in points:
        sx += k; sy += p; sxx += k * k; sxy += k * p
    den = n * sxx - sx * sx
    if den == 0:
        return None
    m = (n * sxy - sx * sy) / den
    return m, (sy - m * sx) / n


def at(line: Tuple[float, float], x: float) -> float:
    return line[0] * x + line[1]


def max_dev(points: List[Tuple[int, float]], line: Tuple[float, float]) -> float:
    """Largest relative distance of the points from the line (0.01 = 1%)."""
    return max(abs(p - at(line, k)) / max(abs(at(line, k)), 1e-9) for k, p in points)


def rsi(c: np.ndarray, n: int = 14) -> np.ndarray:
    """Wilder RSI; NaN until n+1 candles exist."""
    out = np.full(len(c), np.nan)
    if len(c) <= n:
        return out
    d = np.diff(c)
    up, dn = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    au, ad = up[:n].mean(), dn[:n].mean()
    out[n] = 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)
    for k in range(n, len(d)):
        au, ad = (au * (n - 1) + up[k]) / n, (ad * (n - 1) + dn[k]) / n
        out[k + 1] = 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)
    return out
