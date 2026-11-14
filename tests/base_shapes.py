"""Synthetic daily price series that BUILD each base pattern on purpose - and near-miss shapes that must be rejected.

Everything is made of legs between price levels, so a test can say "this is a 20% deep cup" and mean it. There is no
real market data here: passing these tests shows the rules do what they say, not that the signals make money.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

VOL = 1_000_000.0


class Builder:
    def __init__(self, start=40.0, seed=7, noise=0.0015, rng=0.004, end="2026-11-12"):
        self.c = [float(start)]
        self.v = [VOL]
        self.seed = seed
        self.noise, self.rng, self.end = noise, rng, end

    @property
    def last(self):
        return self.c[-1]

    def leg(self, to, bars, ease="lin", vol=1.0):
        """Move from the last close to `to` in `bars` candles. ease: lin | down_u (flat at the end) | up_u (flat at the start)."""
        a = self.c[-1]
        for k in range(1, bars + 1):
            t = k / bars
            f = {"lin": t, "down_u": 1 - (1 - t) ** 2, "up_u": t * t}[ease]
            self.c.append(a + (to - a) * f)
            self.v.append(VOL * vol)
        return self

    def flat(self, price, bars, vol=1.0, wiggle=0.0):
        """Hold `price` (optionally wiggling +-wiggle, as a fraction) for `bars` candles."""
        for k in range(bars):
            self.c.append(price * (1 + wiggle * np.sin(k * 1.3)))
            self.v.append(VOL * vol)
        return self

    def bar(self, close, vol=1.0):
        self.c.append(float(close))
        self.v.append(VOL * vol)
        return self

    def df(self) -> pd.DataFrame:
        n = len(self.c)
        c = np.array(self.c) * (1 + np.random.default_rng(self.seed).normal(0, self.noise, n))  # same noise every call: a cut series is a true prefix
        c[0] = self.c[0]
        o = np.concatenate([[c[0]], c[:-1]])
        h = np.maximum(o, c) * (1 + self.rng)
        l = np.minimum(o, c) * (1 - self.rng)
        idx = pd.bdate_range(end=self.end, periods=n)
        return pd.DataFrame({"Date": idx, "Open": o, "High": h, "Low": l, "Close": c, "Volume": np.array(self.v)})


def lead(top=100.0, start=40.0, base_bars=100, ramp_bars=120, seed=7):
    """A quiet stock at `start`, then a steady advance to `top` (satisfies every 'prior advance' rule)."""
    b = Builder(start, seed)
    b.flat(start, base_bars, wiggle=0.01)
    b.leg(top, ramp_bars)
    return b


# ----------------------------------------------------------------------------- the nine patterns (valid shapes)
def flat_base(depth=0.10, bars=30, seed=7):
    b = lead(100, seed=seed)
    lo = 100 * (1 - depth)
    mid, amp = (100 + lo) / 2, (100 - lo) / 2 * 0.92
    for k in range(bars):
        b.bar(mid + amp * np.sin(k * 0.45 + 1.0) * 0.9, vol=0.7)
    b.leg(99.0, 2, vol=0.7)
    return b


def cup(depth=0.20, down=40, up=40, handle=8, handle_drop=0.03, handle_vol=0.6, v_shape=False, seed=7):
    b = lead(100, seed=seed)
    bottom = 100 * (1 - depth)
    b.leg(bottom, down, "lin" if v_shape else "down_u", vol=1.0)
    b.leg(99.0, up, "lin" if v_shape else "up_u", vol=1.0)
    b.leg(99.0 * (1 - handle_drop), handle, "lin", vol=handle_vol)
    return b


def vcp(depths=(0.22, 0.12, 0.06), peaks=(100.0, 98.0, 96.0), leg_bars=9, vols=(1.5, 1.0, 0.5), seed=7):
    """One pullback + recovery per contraction; every recovery stops a little under the next (lower) peak.
    The pivot is the last peak. The last recovery ends 0.8% under it, so the base is 'forming'."""
    b = lead(peaks[0], seed=seed)
    for k, (d, vol) in enumerate(zip(depths, vols)):
        b.leg(peaks[k] * (1 - d), leg_bars, vol=vol)
        b.leg(peaks[k + 1] if k + 1 < len(depths) else peaks[k] * 0.992, leg_bars, vol=vol)
    return b


def double_bottom(undercut=0.02, gap=30, seed=7):
    b = lead(100, seed=seed)
    b.leg(80, 15)
    b.leg(92, gap // 2)
    b.leg(80 * (1 - undercut), gap // 2)
    b.leg(90.5, 14)
    return b


def htf(rally=1.12, ramp_bars=25, flag_bars=12, pullback=0.15, seed=7):
    b = Builder(40, seed)
    b.flat(40, 120, wiggle=0.01)
    top = 40 * (1 + rally)
    b.leg(top, ramp_bars)
    n1 = flag_bars * 2 // 3
    b.leg(top * (1 - pullback), n1)
    b.leg(top * (1 - 0.035), flag_bars - n1)
    return b


def power_play(rally=0.62, ramp_bars=20, flag_bars=8, pullback=0.07, seed=7):
    b = Builder(40, seed)
    b.flat(40, 120, wiggle=0.01)
    top = 40 * (1 + rally)
    b.leg(top, ramp_bars)
    n1 = flag_bars // 2
    b.leg(top * (1 - pullback), n1)
    b.leg(top * (1 - 0.025), flag_bars - n1)
    return b


def ascending(lows=(90, 94, 98.5), highs=(100, 104, 108), leg=8, final=106.0, seed=7):
    b = lead(100, seed=seed)
    for lo, hi in zip(lows, highs):
        if hi != highs[0]:
            b.leg(hi, leg)
        b.leg(lo, leg)
    b.leg(final, leg)
    return b


def darvas(height=0.087, bars=15, seed=7):
    b = lead(100, seed=seed)
    top = 100 * 1.0
    lo = top * (1 - height) * 1.004
    b.leg(top * 0.985, 2)
    b.leg(lo * 1.01, 5, vol=0.8)
    b.leg(top * 0.985, bars - 8, vol=0.8)
    b.flat(top * 0.98, 3, vol=0.8, wiggle=0.004)
    return b


def ledge(pullback=0.12, ledge_bars=8, ledge_vol=0.5, seed=7):
    b = lead(100, seed=seed)
    b.leg(100 * (1 - pullback), 10)
    b.leg(99.0, 12)
    for k in range(ledge_bars):
        b.bar(98.2 + 0.6 * np.sin(k * 0.9), vol=ledge_vol * (1.2 - 0.05 * k))
    return b


# ----------------------------------------------------------------------------- helpers for the tests
def with_breakout(b: Builder, pivot_close: float, vol=2.0):
    b.bar(pivot_close, vol=vol)
    return b
