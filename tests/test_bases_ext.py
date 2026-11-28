"""The 12 further bases (bases_ext.py): each shape is BUILT from synthetic prices on purpose, near-misses must be rejected, and
breakouts must go the right way. Synthetic prices only: nothing here says how often a shape that passes works in a real market."""
import numpy as np
import pandas as pd
import pytest

import bases as B
import config
import patterns as P
import signals as sg
from tests import base_shapes as S
from tests.test_bases import _walk, _validate

PROF = config.PROFILES["1d"]
EXT = list(B.DETECTORS_EXT)


def sigs(b, name=None, variant=None):
    out = B.base_signals(P.Candles(b.df(), 50), PROF.store_bars)
    return [r for r in out if (name is None or r["name"] == name) and (variant is None or r.get("variant") == variant)]


def live(b, name):
    return [r for r in sigs(b, name) if r["status"] in ("forming", "breakout")]


# (name, variant, direction while forming, shape)
VALID = [
    ("Triangles", "Ascending", "bull", S.triangle_asc), ("Triangles", "Descending", "bear", S.triangle_desc),
    ("Triangles", "Symmetrical", "neutral", S.triangle_sym), ("Wedges", "Falling", "bull", S.wedge_falling),
    ("Wedges", "Rising", "bear", S.wedge_rising), ("Flags and Pennants", "Flag", "bull", S.flag_bull),
    ("Flags and Pennants", "Pennant", "bull", S.pennant_bull), ("Flags and Pennants", "Flag", "bear", S.flag_bear),
    ("Rectangle", None, "neutral", S.rectangle), ("Diamond", None, "neutral", S.diamond),
    ("Rounding Bottom", None, "bull", S.rounding_bottom), ("Broadening Wedge", None, "neutral", S.broadening),
    ("Three Pushes", "Three Pushes up", "bear", S.three_pushes_up), ("Bump and Run", None, "bear", S.bump_and_run),
    ("Ross Hook", "Bullish hook", "bull", S.ross_hook_bull), ("Wyckoff Accumulation", None, "bull", S.wyckoff),
    ("Supply & Demand Zones", "Demand zone", "bull", S.demand_zone), ("Supply & Demand Zones", "Supply zone", "bear", S.supply_zone),
]


@pytest.mark.parametrize("name,variant,direction,make", VALID, ids=[f"{n} {v or ''} {d}".replace("  ", " ") for n, v, d, _ in VALID])
def test_valid_shape_is_found_as_forming(name, variant, direction, make):
    got = [g for g in sigs(make(), name, variant) if g["status"] == "forming"]
    assert len(got) == 1, got
    g = got[0]
    assert g["group"] == "base" and g["dir"] == direction and g["confirm"] == "pending"
    if name == "Broadening Wedge":                          # a warning: shown, but with no trade level
        assert g["warn"] is True and g["pivot"] is None and g["stop"] is None and g["upper"] > g["lower"]
    elif direction == "neutral":                            # two-sided: both boundaries, no stop until one breaks
        assert g["pivot"] > g["pivot_lo"] > 0 and g["stop"] is None
    else:
        assert g["pivot"] > 0 and g["stop"] > 0 and (g["stop"] < g["pivot"]) == (direction == "bull")
    assert g["quality"] is not None and 0 <= g["quality"] <= 100


# (name, shape, close of the breakout candle, volume multiple, expected direction)
BREAKS = [
    ("Triangles", S.triangle_asc, 101.5, 2.0, "bull"), ("Triangles", S.triangle_desc, 88.6, 2.0, "bear"),
    ("Triangles", S.triangle_sym, 98.2, 2.0, "bull"), ("Triangles", S.triangle_sym, 91.5, 2.0, "bear"),
    ("Wedges", S.wedge_falling, 92.5, 2.0, "bull"), ("Wedges", S.wedge_rising, 98.5, 2.0, "bear"),
    ("Flags and Pennants", S.flag_bull, 127.0, 2.0, "bull"), ("Flags and Pennants", S.flag_bear, 73.0, 2.0, "bear"),
    ("Rectangle", S.rectangle, 101.9, 2.0, "bull"), ("Rectangle", S.rectangle, 88.2, 2.0, "bear"),
    ("Diamond", S.diamond, 106.0, 2.0, "bull"), ("Diamond", S.diamond, 94.0, 2.0, "bear"),
    ("Rounding Bottom", S.rounding_bottom, 101.8, 2.0, "bull"), ("Three Pushes", S.three_pushes_up, 105.0, 1.5, "bear"),
    ("Bump and Run", S.bump_and_run, 112.0, 1.5, "bear"), ("Ross Hook", S.ross_hook_bull, 121.5, 1.0, "bull"),
    ("Wyckoff Accumulation", S.wyckoff, 86.0, 2.0, "bull"), ("Supply & Demand Zones", S.demand_zone, 103.0, 1.5, "bull"),
    ("Supply & Demand Zones", S.supply_zone, 97.0, 1.5, "bear"),
]


@pytest.mark.parametrize("name,make,close,vol,direction", BREAKS, ids=[f"{n} {d} {c}" for n, _, c, _, d in BREAKS])
def test_breakout_goes_the_way_it_broke(name, make, close, vol, direction):
    b = make(); b.bar(close, vol=vol)
    got = [g for g in sigs(b, name) if g["since"] == 0 and g["status"] == "breakout"]
    assert got, sigs(b, name)
    assert got[0]["dir"] == direction and got[0]["confirm"] == "confirmed"


def test_a_two_sided_base_has_no_stop_until_it_breaks_then_the_other_boundary_is_the_stop():
    b = S.rectangle(); b.bar(101.9, vol=2.0)
    g = [g for g in sigs(b, "Rectangle") if g["status"] == "breakout"][0]
    assert g["dir"] == "bull" and g["pivot"] == pytest.approx(100.4, abs=0.7) and g["stop"] == pytest.approx(89.5, abs=1.0)
    d = S.rectangle(); d.bar(88.2, vol=2.0)
    g = [g for g in sigs(d, "Rectangle") if g["status"] == "breakout"][0]
    assert g["dir"] == "bear" and g["pivot"] == pytest.approx(89.5, abs=1.0) and g["stop"] == pytest.approx(100.4, abs=0.7)


def test_rectangle_has_a_measured_move_target_and_a_fast_break_tag():
    b = S.rectangle(); b.bar(101.9, vol=2.0)
    g = [g for g in sigs(b, "Rectangle") if g["status"] == "breakout"][0]
    assert g["target"] == pytest.approx(g["pivot"] + (100.4 - 89.5), abs=1.5)        # the box height projected from the break
    assert g["fast"] is True                                                         # a tall candle on volume
    d = S.rectangle(); d.bar(88.2, vol=2.0)
    assert [g for g in sigs(d, "Rectangle") if g["status"] == "breakout"][0]["target"] < 89.5   # downwards for a bearish break


def test_a_close_beyond_the_boundary_on_weak_volume_is_not_a_breakout():
    b = S.rectangle(); b.bar(101.9, vol=0.8)
    assert all(g["status"] != "breakout" for g in sigs(b, "Rectangle"))


def test_failed_breakout_of_a_two_sided_base_falls_back_inside():
    b = S.rectangle(); b.bar(101.9, vol=2.0).bar(99.0)
    g = [g for g in sigs(b, "Rectangle") if g["since"] == 1][0]
    assert g["status"] == "failed" and g["dir"] == "bull" and g["fail_since"] == 0


def test_failed_bearish_breakout_rises_back_inside():
    b = S.rectangle(); b.bar(88.2, vol=2.0).bar(91.5)
    assert [g["status"] for g in sigs(b, "Rectangle") if g["since"] == 1] == ["failed"]


def test_the_ross_hook_does_not_need_volume():
    b = S.ross_hook_bull(); b.bar(121.5, vol=0.3)
    assert [g["status"] for g in sigs(b, "Ross Hook") if g["since"] == 0] == ["breakout"]


def test_broadening_wedge_is_only_ever_a_warning():
    b = S.broadening(); b.bar(112, vol=3.0)
    assert all(g["status"] != "breakout" for g in sigs(b, "Broadening Wedge"))


# ----------------------------------------------------------------------------- near-misses are rejected
NEAR_MISS = [
    ("Triangles", "parallel rising lines (a channel)", S.channel_up), ("Triangles", "flat top AND flat floor (a box)", S.rectangle),
    ("Wedges", "parallel rising lines (a channel)", S.channel_up),
    ("Flags and Pennants", "pole only 12% (limit 15%)", lambda: S.flag_bull(pole=12, drop=2)),
    ("Flags and Pennants", "pole 60% (that is a Power Play / High Tight Flag)", lambda: S.flag_bull(pole=60, drop=8)),
    ("Flags and Pennants", "retraces 55% of the pole (limit 50%)", lambda: S.flag_bull(drop=16)),
    ("Flags and Pennants", "flag lasts 28 candles (limit 20)", lambda: S.flag_bull(flag=28)),
    ("Rectangle", "35% tall (limit 25%)", lambda: S.rectangle(low=65)), ("Rectangle", "ceiling touched only once", lambda: S.rectangle(top_touches=1)),
    ("Diamond", "a flagpole then calm is a trend, not a diamond", S.flag_bull),
    ("Rounding Bottom", "V-shaped", lambda: S.rounding_bottom(v=True)), ("Rounding Bottom", "only 8% deep", lambda: S.rounding_bottom(depth=0.08)),
    ("Rounding Bottom", "only 40 candles", lambda: S.rounding_bottom(bars=40)),
    ("Broadening Wedge", "rising lows (a triangle)", S.triangle_asc), ("Broadening Wedge", "a flat box", S.rectangle),
    ("Three Pushes", "only two pushes", lambda: S._zig(S.lead(100), [(110, 4), (104, 4), (113, 8), (108, 4)])),
    ("Bump and Run", "bump only 4% above the lead-in line", lambda: S.bump_and_run(peak=112, end=106)),
    ("Ross Hook", "a 4-candle pullback is not a hook", lambda: S.ross_hook_bull(hook=(120.2, 119.7, 119.4, 119.1))),
    ("Ross Hook", "point 3 stops 5% short of point 1", lambda: S.ross_hook_bull(point3=115)),
    ("Wyckoff Accumulation", "no prior decline (only 8%)", lambda: S.wyckoff(decline=8)),
    ("Wyckoff Accumulation", "the Spring undercuts support by 9% (limit 5%)", lambda: S.wyckoff(spring_under=0.09)),
    ("Wyckoff Accumulation", "price never reclaims support", lambda: S.wyckoff(reclaim=False)),
    ("Supply & Demand Zones", "the move away is weak (2 points)", lambda: S.demand_zone(impulse=2)),
    ("Supply & Demand Zones", "price closed under the zone: it is broken", lambda: S.demand_zone(broken=True)),
]


@pytest.mark.parametrize("name,why,make", NEAR_MISS, ids=[f"{n}: {w}" for n, w, _ in NEAR_MISS])
def test_near_miss_is_rejected(name, why, make):
    assert live(make(), name) == [], f"{name} accepted although: {why}"


def test_flat_or_halted_price_makes_no_base():
    b = S.Builder(50, 3); b.flat(50, 300)
    assert sigs(b) == []


# ----------------------------------------------------------------------------- scoring, direction, 1H
def _analyze(b, prof=PROF):
    return sg.analyze(b.df(), prof, "BULLISH")


def test_bearish_and_neutral_bases_are_scored_and_carry_their_direction():
    sigs_, ctx, _ = _analyze(S.bump_and_run())
    g = [g for g in sigs_ if g["name"] == "Bump and Run"][0]
    assert g["dir"] == "bear" and 0 <= g["score"] <= 100 and g["group"] == "base"
    sigs_, _, _ = _analyze(S.rectangle())
    assert [g for g in sigs_ if g["name"] == "Rectangle"][0]["dir"] == "neutral"


def test_context_has_the_numbers_the_rank_needs():
    _, ctx, _ = _analyze(S.flat_base())
    assert ctx["ret_6m"] is not None and ctx["turnover_cr"] > 0


def _hourly(b):
    """The same prices on hourly candles (7 per trading day): the rules are counted in candles of the timeframe."""
    df = b.df()
    n = len(df)
    days = pd.bdate_range(end="2026-11-12", periods=(n + 6) // 7)
    idx = [pd.Timestamp(d) + pd.Timedelta(hours=9, minutes=15 + 60 * k) for d in days for k in range(7)][-n:]
    df = df.copy(); df["Date"] = idx
    return df


def test_base_patterns_also_run_on_1h():
    df = _hourly(S.flat_base())
    sigs_, ctx, _ = sg.analyze(df, config.PROFILES["1h"], "BULLISH")
    base = [g for g in sigs_ if g["group"] == "base" and g["name"] == "Flat Base"]
    assert base and ":" in base[0]["time"] and "stage" not in ctx          # hourly time stamp; Stage / Base count stay 1D-only


def test_1h_switch(monkeypatch):
    monkeypatch.setattr(config, "BASE_1H_ON", False)
    sigs_, _, _ = sg.analyze(_hourly(S.flat_base()), config.PROFILES["1h"], "BULLISH")
    assert not [g for g in sigs_ if g["group"] == "base"]


# ----------------------------------------------------------------------------- no repaint, publish gate, robustness
def test_no_repaint_for_all_21_bases_on_random_walks():
    """Every breakout / failure seen on one day must still be there, on the same candle, when later candles arrive."""
    def decided(df, cut):
        x = P.Candles(df.iloc[:cut].reset_index(drop=True), 50)
        return {(g["name"], g["time"], g.get("dir")): g["status"] for g in B.base_signals(x, PROF.store_bars) if g["status"] != "forming"}
    checked = bad = 0
    for seed in range(200, 250):
        df = _walk(seed, 420)
        full = decided(df, len(df))
        for back in (1, 2, 4, 7):
            for (name, t, d), status in decided(df, len(df) - back).items():
                since = len(df) - back - 1 - list(df["Date"].dt.strftime("%Y-%m-%d")).index(t)
                if since + back >= PROF.store_bars:
                    continue
                checked += 1
                ok = (name, t, d) in full and (full[(name, t, d)] == status or (status == "breakout" and full[(name, t, d)] == "failed"))
                bad += 0 if ok else 1
    assert checked > 30 and bad <= 1, (checked, bad)    # statistical guard: at most one stray difference in the whole sample


def test_everything_passes_the_publish_validator_on_1d_and_1h():
    import detail_store
    import scan_market_structure_combined as scan
    import validate_data
    for prof, frames in ((PROF, [_walk(s, 420) for s in range(300, 330)] + [S.rectangle().df(), S.rounding_bottom().df(), S.diamond().df()]),
                         (config.PROFILES["1h"], [_hourly(S.flat_base()), _hourly(S.triangle_asc()), _hourly(S.rectangle())])):
        for df in frames:
            _, detail = scan.compute_signals(prof, df, "BULLISH")
            errors = []
            validate_data._check_block("T", prof, detail_store.sanitize(detail), errors)
            assert errors == [], errors[:3]


def test_scanner_survives_malformed_series():
    import scan_market_structure_combined as scan
    rs = np.random.default_rng(9)
    for kind in range(12):
        n = int(rs.choice([30, 90, 260, 420]))
        c = 100 * np.exp(np.cumsum(rs.normal(0.0005, 0.02, n)))
        o = np.r_[c[0], c[:-1]]; h = np.maximum(o, c) * 1.01; l = np.minimum(o, c) * 0.99; v = rs.integers(1e5, 1e6, n).astype(float)
        if kind == 1: v[:] = 0
        if kind == 2: v[rs.random(n) < 0.3] = np.nan
        if kind == 3: c[rs.random(n) < 0.05] = np.nan
        if kind == 4: o[:] = h[:] = l[:] = c[:] = 50.0
        if kind == 5: c *= 1e-4; o *= 1e-4; h *= 1e-4; l *= 1e-4
        if kind == 6: h, l = l, h
        df = pd.DataFrame({"Date": pd.bdate_range(end="2026-11-12", periods=n), "Open": o, "High": h, "Low": l, "Close": c, "Volume": v})
        scan.compute_signals(PROF, df, "BULLISH")   # must not raise
