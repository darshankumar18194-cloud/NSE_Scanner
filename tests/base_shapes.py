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


def lead(top=100.0, start=40.0, base_bars=100, ramp_bars=120, seed=7, rng=0.004):
    """A quiet stock at `start`, then a steady advance to `top` (satisfies every 'prior advance' rule)."""
    b = Builder(start, seed, rng=rng)
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


# ----------------------------------------------------------------------------- the 12 further bases
def _zig(b, legs):
    """legs: (price, bars) pairs from the current close."""
    for to, bars in legs:
        b.leg(to, bars)
    return b


def triangle_asc(seed=7):      # flat top, rising lows
    return _zig(lead(100, seed=seed), [(90, 8), (99.6, 8), (93.5, 7), (99.7, 7), (96.5, 5), (99.7, 4)])


def triangle_desc(seed=7):     # flat floor, falling highs
    return _zig(lead(100, seed=seed), [(90.3, 8), (98, 8), (90.4, 7), (95.5, 7), (90.3, 5), (93.2, 4)])


def triangle_sym(seed=7):      # lower highs, higher lows
    return _zig(lead(100, seed=seed), [(88, 10), (98, 8), (91, 7), (96.5, 6), (93.5, 5), (96.4, 4)])


def wedge_falling(seed=7):     # both lines falling and converging (bullish)
    return _zig(lead(100, seed=seed), [(92, 7), (96.4, 6), (89.6, 6), (92.4, 5), (88.2, 5), (90.0, 4)])


def wedge_rising(seed=7):      # both lines rising and converging (bearish)
    return _zig(lead(100, seed=seed), [(92, 6), (102.5, 6), (96.5, 6), (104.2, 6), (99.5, 5), (104.4, 4)])


def flag_bull(pole=25, flag=10, drop=5, seed=7):
    b = lead(100, seed=seed)
    return _zig(b, [(100 + pole, 12), (100 + pole - drop, flag)])


def pennant_bull(seed=7):
    return _zig(lead(100, seed=seed), [(125, 12), (115, 3), (123.5, 3), (117.5, 3), (122, 3), (119.5, 2), (121.2, 2)])


def flag_bear(pole=25, flag=10, bounce=3, seed=7):
    b = lead(100, seed=seed)
    return _zig(b, [(100 - pole, 12), (100 - pole + bounce, flag)])


def rectangle(seed=7, bars=6, low=90.2, top_touches=3):
    tops = [99.8, 99.7, 99.2] if top_touches >= 3 else [97.6, 96.8, 99.2]
    return _zig(lead(100, seed=seed), [(low, bars), (tops[0], bars), (low + .2, bars), (tops[1], bars), (low + .1, bars), (tops[2], bars - 1)])


def channel_up(seed=7):        # parallel rising lines: not converging, so not a triangle or a wedge
    return _zig(lead(100, seed=seed), [(90, 8), (102.5, 8), (93, 7), (105, 7), (95.5, 5), (104.7, 4)])


def diamond(seed=7, widest=6.0):
    b = lead(100, seed=seed)
    for t in range(60):
        amp = 0.8 + widest * np.sin(np.pi * t / 60) ** 2
        b.bar(100 + amp * np.sin(t * 1.05))
    return b


def rounding_bottom(depth=0.2, bars=85, v=False, seed=7):
    b = lead(100, seed=seed)
    bottom = 100 * (1 - depth)
    mid = bars / 2.0
    for t in range(1, bars + 1):
        b.bar(bottom + (100 - bottom) * (abs(t - mid) / mid if v else ((t - mid) / mid) ** 2))
    return b


def broadening(seed=7):
    return _zig(lead(100, seed=seed), [(95, 5), (104, 6), (91, 6), (108, 7), (87, 6), (104, 5)])


def three_pushes_up(seed=7):
    return _zig(lead(100, seed=seed), [(110, 4), (104, 4), (113, 8), (108, 4), (115.5, 12), (111.8, 4)])


def bump_and_run(seed=7, peak=135, end=120):
    b = lead(100, seed=seed)
    return _zig(b, [(peak, 15), (end, 15)])


def ross_hook_bull(seed=7, point3=121, hook=(120.2, 119.7)):
    b = lead(100, seed=seed)
    _zig(b, [(120, 10), (108, 6), (point3, 7)])
    for x in hook:
        b.bar(x)
    return b


def wyckoff(spring_under=0.026, decline=30, reclaim=True, seed=7):
    b = lead(100, seed=seed)
    floor = 100 - decline
    b.leg(floor, 40)
    for k in range(45):                                  # a range on normal volume
        b.bar(floor + 7.5 + 6.6 * np.sin(k * 0.55), vol=1.0)
    b.bar((floor + 0.3) * (1 - spring_under) + 0.3, vol=0.6)    # the Spring
    b.bar(floor + 1.5 if reclaim else floor - 3, vol=0.5)
    b.leg(floor + 6 if reclaim else floor - 4, 5, vol=0.5)
    return b


def demand_zone(seed=7, impulse=8, back=100.0, broken=False):
    b = lead(100, seed=seed, rng=0.0015)
    b.flat(100, 3)                                       # a tight base
    b.leg(100 + impulse, 3)                              # a strong move away
    b.leg(100 + impulse * 2, 12)
    b.leg(back, 14)                                      # back into the zone
    if broken:
        b.leg(96, 3)
    return b.flat(back if not broken else 96, 3)         # compression at the zone


def supply_zone(seed=7):
    b = lead(100, seed=seed, rng=0.0015)
    b.flat(100, 3)
    b.leg(92, 3)
    b.leg(84, 12)
    b.leg(99.9, 14)
    return b.flat(99.9, 3)
