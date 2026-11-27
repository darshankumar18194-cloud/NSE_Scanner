"""ADX: flat (zero-range) prices give NaN without a numpy warning, and normal series are unchanged."""
import warnings

import numpy as np

import indicators as ind


def test_flat_prices_do_not_warn():
    flat = np.full(80, 50.0)
    with warnings.catch_warnings():
        warnings.simplefilter("error")                    # any RuntimeWarning fails the test
        adx, pdi, mdi = ind.adx(flat, flat, flat)
    assert np.isnan(adx).all()


def test_normal_series_still_produce_values():
    rs = np.random.default_rng(3)
    c = 100 * np.exp(np.cumsum(rs.normal(0, 0.01, 200)))
    h, l = c * 1.005, c * 0.995
    adx, _, _ = ind.adx(h, l, c)
    assert np.isfinite(adx[-1]) and 0 <= adx[-1] <= 100
