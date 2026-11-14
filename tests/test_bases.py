"""Base patterns (bases.py): every shape is built from synthetic prices on purpose, and near-miss shapes must be rejected.

IMPORTANT: this only proves the rules do what config.py says. No real market data is used here, so how often a shape
that passes these rules goes on to work in the real market is NOT tested and no win rate is claimed.
"""
import numpy as np
import pandas as pd
import pytest

import bases as B
import config
import patterns as P
import signals as sg
from tests import base_shapes as S

PROF = config.PROFILES["1d"]
NAMES = list(B.DETECTORS)


def arr(b):
    return B.Arr(P.Candles(b.df(), 50))


def events(b, name):
    a = arr(b)
    return B.run_detector(a, name, B._first_candle(a.n, PROF.store_bars))


def sigs(b, name=None):
    out = B.base_signals(P.Candles(b.df(), 50), PROF.store_bars)
    return [r for r in out if name is None or r["name"] == name]


def live(b, name):
    """(the detector sees a base standing on the last candle, statuses of the events in the window)."""
    a = arr(b)
    return B.DETECTORS[name][0](a, a.n - 1) is not None, [e["status"] for e in events(b, name)]


GOOD = {
    "Flat Base": S.flat_base, "Cup with Handle": S.cup, "VCP": S.vcp, "Double Bottom": S.double_bottom,
    "High Tight Flag": S.htf, "Power Play": S.power_play, "Ascending Base": S.ascending, "Darvas Box": S.darvas,
    "The Ledge": S.ledge,
}


# ----------------------------------------------------------------------------- each pattern is found
@pytest.mark.parametrize("name", NAMES)
def test_valid_shape_is_found_as_forming(name):
    r = sigs(GOOD[name](), name)
    assert len(r) == 1, r
    g = r[0]
    assert g["group"] == "base" and g["dir"] == "bull" and g["status"] == "forming" and g["confirm"] == "pending"
    assert g["pivot"] > g["stop"] > 0
    assert g["pivot"] >= g["price"] >= g["pivot"] * (1 - config.BASE_NEAR_PIVOT_PCT / 100.0) - 1e-6  # inside the "near pivot" band
    assert g["len"] >= 5 and g["since"] >= 0


def test_pivots_and_stops_are_where_the_rules_put_them():
    f = sigs(S.flat_base(), "Flat Base")[0]
    assert f["pivot"] == pytest.approx(100.4, abs=0.6) and f["stop"] == pytest.approx(90.4, abs=1.0)   # base high / base low
    assert 8 < f["depth"] < 11.5 and f["len"] >= config.FLAT_MIN_BARS
    v = sigs(S.vcp(), "VCP")[0]
    assert v["pivot"] == pytest.approx(96.5, abs=0.8)            # the last contraction's high, not the base high (100)
    assert v["contractions"][0] > v["contractions"][1] > v["contractions"][2]
    assert v["contractions"][-1] <= config.VCP_LAST_MAX
    c = sigs(S.cup(), "Cup with Handle")[0]
    assert 12 <= c["depth"] <= 33 and c["handle_bars"] >= config.HANDLE_MIN_BARS
    d = sigs(S.double_bottom(), "Double Bottom")[0]
    assert config.DB_UNDERCUT_MIN <= d["undercut_pct"] <= config.DB_UNDERCUT_MAX
    assert d["pivot"] == pytest.approx(92.4, abs=0.8)            # the middle peak of the W
    h = sigs(S.htf(), "High Tight Flag")[0]
    assert h["rally_pct"] >= config.HTF_RISE_PCT and h["depth"] <= config.HTF_MAX_PULLBACK
    p = sigs(S.power_play(), "Power Play")[0]
    assert p["rally_pct"] >= config.PP_RISE_PCT and p["depth"] <= config.PP_MAX_PULLBACK
    a = sigs(S.ascending(), "Ascending Base")[0]
    assert a["steps"] >= config.ASC_MIN_PULLBACKS and a["stop"] > 97          # the last (highest) low
    dv = sigs(S.darvas(), "Darvas Box")[0]
    assert dv["depth"] <= config.DARVAS_MAX_HEIGHT and dv["box_no"] == 1
    l = sigs(S.ledge(), "The Ledge")[0]
    assert l["depth"] <= config.LEDGE_MAX_DEPTH and l["len"] >= config.LEDGE_MIN_BARS


# ----------------------------------------------------------------------------- near-misses are rejected
NEAR_MISS = [
    ("Flat Base", "17% deep (limit 15%)", lambda: S.flat_base(depth=0.17)),
    ("Flat Base", "only 14 candles (needs 25)", lambda: S.flat_base(bars=12)),
    ("Cup with Handle", "36% deep (limit 33%)", lambda: S.cup(depth=0.36)),
    ("Cup with Handle", "8% deep (needs 12%)", lambda: S.cup(depth=0.08)),
    ("Cup with Handle", "V-shaped, not rounded", lambda: S.cup(v_shape=True)),
    ("Cup with Handle", "handle in the lower half of the cup", lambda: S.cup(depth=0.15, handle_drop=0.095)),
    ("Cup with Handle", "handle volume rising", lambda: S.cup(handle_vol=1.8)),
    ("Cup with Handle", "handle only 3 candles", lambda: S.cup(handle=3)),
    ("VCP", "last pullback bigger than the one before", lambda: S.vcp(depths=(0.22, 0.12, 0.15))),
    ("VCP", "last pullback 12% (limit 10%)", lambda: S.vcp(depths=(0.30, 0.20, 0.12))),
    ("VCP", "only one contraction", lambda: S.vcp(depths=(0.20,), peaks=(100, 98), vols=(1.0,))),
    ("VCP", "volume grows as it tightens", lambda: S.vcp(vols=(0.5, 1.0, 1.5))),
    ("Double Bottom", "second low does not undercut the first", lambda: S.double_bottom(undercut=-0.02)),
    ("Double Bottom", "undercut 9% (limit 5%)", lambda: S.double_bottom(undercut=0.09)),
    ("Double Bottom", "lows only 8 candles apart", lambda: S.double_bottom(gap=8)),
    ("High Tight Flag", "rally only +80%", lambda: S.htf(rally=0.80)),
    ("High Tight Flag", "flag pulls back 30% (limit 25%)", lambda: S.htf(pullback=0.30)),
    ("High Tight Flag", "rally took 60 candles (limit 40)", lambda: S.htf(ramp_bars=60)),
    ("Power Play", "flag pulls back 18% (limit 12%)", lambda: S.power_play(pullback=0.18)),
    ("Power Play", "rally only +30%", lambda: S.power_play(rally=0.30)),
    ("Ascending Base", "lows are not rising", lambda: S.ascending(lows=(90, 89, 91))),
    ("Ascending Base", "only two steps", lambda: S.ascending(lows=(90, 94), highs=(100, 104), final=102.5)),
    ("Darvas Box", "box 25% tall (limit 15%)", lambda: S.darvas(height=0.25)),
    ("The Ledge", "loud volume instead of a quiet pause", lambda: S.ledge(ledge_vol=2.5)),
    ("The Ledge", "the larger base never pulled back 10%", lambda: S.ledge(pullback=0.04)),
]


@pytest.mark.parametrize("name,why,make", NEAR_MISS, ids=[f"{n}: {w}" for n, w, _ in NEAR_MISS])
def test_near_miss_is_rejected(name, why, make):
    standing, statuses = live(make(), name)
    assert not standing, f"{name} accepted although: {why}"
    assert "forming" not in statuses and "breakout" not in statuses


def test_no_prior_advance_is_rejected():
    """A flat 12%-deep shape on a stock that has not risen is not a base: nothing came before it to consolidate."""
    b = S.Builder(100, 3)
    b.flat(100, 150, wiggle=0.01)
    for k in range(40):
        b.bar(95 + 4.5 * np.sin(k * 0.4), vol=0.7)
    assert sigs(b, "Flat Base") == []


def test_pure_noise_and_short_history_never_crash():
    rs = np.random.default_rng(0)
    n = 300
    c = 100 + np.cumsum(rs.normal(0, 1, n))
    df = pd.DataFrame({"Date": pd.bdate_range(end="2026-11-12", periods=n), "Open": c, "High": c + 1, "Low": c - 1,
                       "Close": c, "Volume": np.zeros(n)})                       # zero volume everywhere
    assert isinstance(B.base_signals(P.Candles(df, 50), PROF.store_bars), list)
    short = df.iloc[:70].reset_index(drop=True)
    assert B.base_signals(P.Candles(short, 50), PROF.store_bars) == []
    flat = df.copy(); flat[["Open", "High", "Low", "Close"]] = 100.0              # a stock that never moves
    assert B.base_signals(P.Candles(flat, 50), PROF.store_bars) == []


# ----------------------------------------------------------------------------- breakout / failure / volume rules
def test_breakout_needs_a_close_above_the_pivot_on_volume():
    b = S.flat_base(); b.bar(101.5, vol=2.0)
    g = sigs(b, "Flat Base")[0]
    assert (g["status"], g["confirm"], g["since"]) == ("breakout", "confirmed", 0)
    assert g["vol_x"] >= config.BASE_BREAKOUT_VOL_EASY


def test_a_close_above_the_pivot_on_weak_volume_is_not_a_breakout():
    b = S.flat_base(); b.bar(101.5, vol=0.9)
    got = sigs(b, "Flat Base")
    assert [g["status"] for g in got] == ["forming"] and got[0]["lowvol"] is True
    assert got[0]["pivot"] == pytest.approx(sigs(S.flat_base(), "Flat Base")[0]["pivot"])      # the pivot did not creep up


def test_weak_volume_then_a_real_breakout_is_still_a_breakout():
    b = S.flat_base(); b.bar(101.0, vol=0.9).bar(102.5, vol=2.2)
    assert [g["status"] for g in sigs(b, "Flat Base")] == ["breakout"]


def test_running_away_without_volume_ends_the_base():
    b = S.flat_base(); b.bar(101.0, vol=0.9).bar(106.5, vol=0.9)           # more than 5% beyond the pivot, never on volume
    assert sigs(b, "Flat Base") == []


def test_breakout_volume_threshold_differs_by_pattern():
    """Flat Base needs 1.2x, Cup needs 1.4x. 1.3x breaks out of the flat base only."""
    b = S.flat_base(); b.bar(101.5, vol=1.3)
    assert sigs(b, "Flat Base")[0]["status"] == "breakout"
    c = S.cup(); c.bar(100.5, vol=1.3)
    assert sigs(c, "Cup with Handle")[0]["status"] == "forming"
    c2 = S.cup(); c2.bar(100.5, vol=1.6)
    assert sigs(c2, "Cup with Handle")[0]["status"] == "breakout"


def test_close_below_the_stop_fails_the_base():
    b = S.flat_base(); b.bar(84, vol=1.5)
    assert [(g["status"], g["confirm"]) for g in sigs(b, "Flat Base")] == [("failed", "failed")]


def test_breakout_that_falls_straight_back_is_failed():
    b = S.flat_base(); b.bar(101.5, vol=2.0).bar(99.5)
    g = sigs(b, "Flat Base")[0]
    assert g["status"] == "failed" and g["since"] == 1 and g["fail_since"] == 0   # the breakout keeps its own candle


def test_breakout_that_holds_stays_a_breakout():
    b = S.flat_base(); b.bar(101.5, vol=2.0).bar(103).bar(104)
    g = sigs(b, "Flat Base")[0]
    assert g["status"] == "breakout" and g["since"] == 2


def test_cup_handle_that_deepens_inside_the_rules_is_not_failed():
    """The handle low is a moving stop: a lower close inside the allowed pullback must not be reported as a failure."""
    b = S.cup(handle=5, handle_drop=0.02); b.bar(94.5, vol=0.5)   # a deeper handle, still above the half-way line
    st = [g["status"] for g in sigs(b, "Cup with Handle")]
    assert "failed" not in st


def test_one_base_gives_one_signal_not_one_per_candle():
    b = S.flat_base(); b.flat(99.6, 3, vol=0.7, wiggle=0.002)
    assert len(sigs(b, "Flat Base")) == 1


def test_old_events_drop_out_of_the_window():
    b = S.flat_base(); b.bar(101.5, vol=2.0)
    for _ in range(PROF.store_bars + 3):
        b.bar(b.last * 1.001, vol=1.0)
    assert sigs(b, "Flat Base") == []          # the breakout is older than the stored window


# ----------------------------------------------------------------------------- no repaint
def _event_map(b, cut=None):
    df = b.df() if cut is None else b.df().iloc[:cut].reset_index(drop=True)
    x = P.Candles(df, 50)
    out = {}
    for g in B.base_signals(x, PROF.store_bars):
        out[(g["name"], g["time"], g["status"])] = g
    return out, len(df)


def test_decisions_never_change_when_later_candles_arrive():
    """Cut a series at many points. Every breakout / failure seen at the cut must still be there (same name and candle)
    when the later candles are added; it may only be downgraded breakout -> failed. Nothing is ever moved or erased."""
    series = []
    for seed in range(12):
        series.append(S.flat_base(seed=seed).bar(101.5, vol=2.0).bar(103).bar(104).bar(101))
        series.append(S.cup(seed=seed).bar(100.5, vol=2.0).bar(101).bar(99))
        series.append(S.vcp(seed=seed).bar(97.5, vol=2.2).bar(98.5))
        series.append(S.flat_base(seed=seed).bar(84, vol=1.5).bar(83))
        series.append(S.htf(seed=seed).bar(87, vol=2.0).bar(88.5))
    checked = 0
    for b in series:
        full, nfull = _event_map(b)
        times_full = {(n, t): s for (n, t, s) in full}
        for back in (1, 2, 3, 4):
            part, ncut = _event_map(b, nfull - back)
            for (name, t, status) in part:
                if status == "forming":
                    continue
                key = (name, t)
                if key not in times_full:      # fell outside the full window or the shape was rebuilt: must not happen here
                    pytest.fail(f"{name} {status} at {t} vanished when {back} later candles were added")
                assert times_full[key] in ({"breakout": ("breakout", "failed"), "failed": ("failed",)}[status])
                checked += 1
    assert checked > 100


def test_a_forming_base_keeps_its_pivot_until_something_happens():
    b = S.flat_base()
    f1 = sigs(b, "Flat Base")[0]
    b.bar(99.4, vol=0.7)
    f2 = sigs(b, "Flat Base")[0]
    assert f1["status"] == f2["status"] == "forming" and f2["pivot"] == pytest.approx(f1["pivot"], rel=0.01)


# ----------------------------------------------------------------------------- Stage Analysis and Base Count
def _stage(prices):
    b = S.Builder(prices[0][0], 5)
    for to, bars in prices:
        b.leg(to, bars)
    return B.stage_reading(arr(b))


def test_stage_2_advancing():
    st = _stage([(50, 1), (100, 300)])
    assert st["stage"] == 2 and st["price_vs_ma"] == "above" and st["ma_slope_pct"] > config.STAGE_SLOPE_PCT


def test_stage_4_declining():
    st = _stage([(100, 1), (50, 300)])
    assert st["stage"] == 4 and st["price_vs_ma"] == "below"


def test_stage_1_basing_after_a_decline():
    st = _stage([(100, 1), (50, 150), (50.5, 150)])
    assert st["stage"] == 1


def test_stage_3_topping_after_an_advance():
    st = _stage([(50, 1), (100, 150), (100.5, 150)])
    assert st["stage"] == 3


def test_stage_needs_enough_history():
    assert _stage([(50, 1), (60, 100)]) is None


def test_stage_2_entry_is_flagged_on_a_volume_cross():
    b = S.Builder(100, 5)
    b.leg(60, 100); b.flat(60, 230, wiggle=0.004)          # a decline, then a long flat base: the average flattens
    ma_now = float(pd.Series(b.c).rolling(config.STAGE_MA_BARS).mean().iloc[-1])
    b.bar(ma_now * 0.99); b.bar(ma_now * 1.05, vol=2.0)    # a close above the average on 2x volume
    st = B.stage_reading(arr(b))
    assert st["stage2_entry_since"] == 0


def test_base_count_counts_earlier_completed_bases_in_the_same_uptrend():
    b = S.lead(100)
    for k in range(30):                                       # base 1: a flat base
        b.bar(95 + 4.5 * np.sin(k * 0.5), vol=0.7)
    b.leg(99.0, 2, vol=0.7); b.bar(102, vol=2.0)              # ... that breaks out
    b.leg(122, 25, vol=1.2)                                   # advance
    for k in range(30):                                       # base 2
        b.bar(116 + 5.5 * np.sin(k * 0.5), vol=0.7)
    b.leg(121, 2, vol=0.7)
    flat = [g for g in sigs(b, "Flat Base") if g["status"] == "forming"]
    assert flat and flat[-1]["base_no"] == 2
    ctx = B.base_context(P.Candles(b.df(), 50))
    assert ctx["base_count"] >= 1 and ctx["base_next"] == ctx["base_count"] + 1
    assert S.flat_base(), "sanity"
    assert sigs(S.flat_base(), "Flat Base")[0]["base_no"] == 1


def test_base_count_is_information_it_never_hides_a_signal():
    b = S.lead(100)
    for _ in range(3):                                        # three bases in a row: base 4 would be 'late stage'
        for k in range(30):
            b.bar(b.last * 0.9992 + 0.05 * np.sin(k), vol=0.7)
        b.bar(b.last * 1.04, vol=2.0); b.leg(b.last * 1.18, 20)
    got = sigs(b)
    assert all("base_no" in g for g in got)                   # present on every signal, filtered by nothing


def test_climactic_run_up_is_flagged():
    htf = sigs(S.htf(), "High Tight Flag")[0]
    assert htf["climactic"] is True                           # +112% rally inside 60 candles
    assert sigs(S.flat_base(), "Flat Base")[0]["climactic"] is False


def test_darvas_boxes_stack():
    b = S.darvas()
    b.bar(101.5, vol=2.0).leg(112, 5)
    b.leg(110.5, 3, vol=0.7); b.leg(104.5, 3, vol=0.7); b.leg(110.2, 4, vol=0.7); b.flat(109.5, 3, vol=0.7, wiggle=0.002)
    boxes = sigs(b, "Darvas Box")
    assert len(boxes) >= 1 and max(g.get("box_no", 1) for g in boxes) >= 1


# ----------------------------------------------------------------------------- wiring: analyze(), scoring, board
def _analyze(b, prof=PROF):
    return sg.analyze(b.df(), prof, "BULLISH")


def test_analyze_adds_scored_base_signals_and_context_on_1d():
    sigs_, ctx, scores = _analyze(S.flat_base().bar(101.5, vol=2.0))
    base = [g for g in sigs_ if g["group"] == "base"]
    assert base and all(0 <= g["score"] <= 100 and len(g["parts"]) == 5 for g in base)
    assert "stars" not in base[0]
    assert ctx["stage"] in (1, 2, 3, 4) and "base_count" in ctx
    assert scores["bull"] >= max(g["score"] for g in base if g["dir"] == "bull")   # the confluence score sees them


def test_scores_follow_the_existing_formula_and_the_star_rating():
    five = max(g["score"] for g in _analyze(S.htf().bar(87, vol=2.5))[0] if g["name"] == "High Tight Flag")
    three = max(g["score"] for g in _analyze(S.flat_base().bar(101.5, vol=2.5))[0] if g["name"] == "Flat Base")
    assert five > three                                        # 5 stars out-scores 3 stars, everything else being similar


def test_base_signals_are_1d_only():
    n = 400
    idx = pd.date_range("2026-01-01 09:15", periods=n, freq="h")
    c = 100 + np.cumsum(np.random.default_rng(1).normal(0, 0.3, n))
    df = pd.DataFrame({"Date": idx, "Open": c, "High": c + 0.3, "Low": c - 0.3, "Close": c, "Volume": 1e5})
    sigs_, ctx, _ = sg.analyze(df, config.PROFILES["1h"], "BULLISH")
    assert not [g for g in sigs_ if g["group"] == "base"]
    assert "stage" not in ctx and "base_count" not in ctx


def test_switch_off(monkeypatch):
    monkeypatch.setattr(config, "BASE_ON", False)
    sigs_, ctx, _ = _analyze(S.flat_base().bar(101.5, vol=2.0))
    assert not [g for g in sigs_ if g["group"] == "base"] and "stage" not in ctx


def test_metadata_covers_every_detector():
    assert set(B.BASE_META) == set(B.DETECTORS) == set(NAMES) and len(NAMES) == 9
    assert all(sg.EVENT_META[n][0] == "base" for n in NAMES) and "base" in sg.GROUPS
    assert all(2 <= B.BASE_META[n][1] <= 5 for n in NAMES)


def test_board_carries_base_fields_only_on_base_signals():
    import build_board
    sigs_, ctx, _ = _analyze(S.flat_base().bar(101.5, vol=2.0))
    block = {"signals": sigs_, "context": ctx, "candles": []}
    out = build_board.compact(block)
    base = [g for g in out["signals"] if g["group"] == "base"]
    other = [g for g in out["signals"] if g["group"] != "base"]
    assert base and all({"status", "pivot", "stop", "since", "score"} <= set(g) for g in base)
    assert all("pivot" not in g and "status" not in g for g in other)     # every other signal stays as small as before
    assert out["context"]["stage"] in (1, 2, 3, 4) and "base_count" in out["context"]


def _walk(seed, n=360):
    r = np.random.default_rng(seed)
    vol, drift = r.uniform(0.008, 0.03), r.normal(0.0009, 0.001)
    c = 100 * np.exp(np.cumsum(r.normal(drift, vol, n)))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * (1 + abs(r.normal(0, vol / 3, n)))
    l = np.minimum(o, c) * (1 - abs(r.normal(0, vol / 3, n)))
    return pd.DataFrame({"Date": pd.bdate_range(end="2026-11-12", periods=n), "Open": o, "High": h, "Low": l, "Close": c,
                         "Volume": r.integers(200_000, 2_000_000, n).astype(float)})


def test_no_repaint_on_random_walks():
    """Same property as above on random prices, where the nine detectors fire in odd combinations. Seeds 83 and 244 once
    failed because the walk started too late (BASE_LEAD_BARS was 25): kept as regression cases."""
    def decided(df, cut):
        x = P.Candles(df.iloc[:cut].reset_index(drop=True), 50)
        return {(g["name"], g["time"]): (g["status"], g["since"]) for g in B.base_signals(x, PROF.store_bars) if g["status"] != "forming"}
    checked = 0
    for seed in [83, 244] + list(range(100, 140)):
        df = _walk(seed)
        full = decided(df, len(df))
        for back in (1, 2, 3, 5, 8):
            for key, (status, since) in decided(df, len(df) - back).items():
                if since + back >= PROF.store_bars:     # scrolled out of the stored window: not a repaint
                    continue
                checked += 1
                assert key in full, (seed, back, key)
                assert full[key][0] == status or (status == "breakout" and full[key][0] == "failed"), (seed, back, key)
    assert checked > 20


# ----------------------------------------------------------------------------- the publish gate (validate_data.py)
def _validate(df):
    import detail_store
    import scan_market_structure_combined as scan
    import validate_data
    _, detail = scan.compute_signals(PROF, df, "BULLISH")
    errors = []
    validate_data._check_block("TEST", PROF, detail_store.sanitize(detail), errors)
    return detail, errors


def test_breakout_window_boundary_matches_the_stored_window():
    """Breakouts / failures are stored for since 0..store_bars-1 (19). One candle older is dropped, never stored."""
    def brk(extra):
        b = S.flat_base(); b.bar(101.5, vol=2.0)
        for _ in range(extra):
            b.bar(b.last * 1.002, vol=1.0)
        return sigs(b, "Flat Base")
    kept = brk(PROF.store_bars - 1)
    assert kept and kept[0]["since"] == PROF.store_bars - 1
    assert brk(PROF.store_bars) == []


def test_a_base_that_has_been_forming_for_a_long_time_is_kept_and_passes_the_validator():
    b = S.flat_base(); b.flat(99.4, 30, vol=0.7, wiggle=0.003)       # still coiling just under its pivot, 30+ candles later
    g = sigs(b, "Flat Base")[0]
    assert g["status"] == "forming" and g["since"] >= PROF.store_bars
    _, errors = _validate(b.df())
    assert errors == []


def test_everything_the_scanner_produces_passes_the_publish_validator():
    """Regression: the first real GitHub run failed validation with \"since=26 outside 0..19\" because older forming bases
    were stored. Random walks and the exact shapes, through compute_signals and the real validator."""
    frames = [_walk(seed) for seed in range(60)]
    for seed in range(8):
        frames += [S.flat_base(seed=seed).df(), S.cup(seed=seed).df(), S.vcp(seed=seed).df(), S.darvas(seed=seed).df(),
                   S.flat_base(seed=seed).flat(99.4, 40, vol=0.7, wiggle=0.003).df(),
                   S.ledge(seed=seed).flat(98.5, 25, vol=0.5, wiggle=0.002).df()]
    seen_old = False
    for df in frames:
        detail, errors = _validate(df)
        assert errors == [], errors[:3]
        seen_old |= any(g["group"] == "base" and g["status"] == "forming" and g["since"] >= PROF.store_bars for g in detail["signals"])
    assert seen_old      # the test really did produce the old-forming case that used to be rejected
