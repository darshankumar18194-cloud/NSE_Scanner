"""Retry policy: dead tickers (NO_DATA) are not retried by default, and retrying stops when a pass recovers nothing."""
import unittest
from unittest import mock

import config
import common
import market_data
import scan_market_structure_combined as scan
from tests import helpers


def _rate_limit():
    return type("YFRateLimitError", (Exception,), {})("Too Many Requests. Rate limited. Try after a while.")


def _no_data(ticker):
    return type("YFPricesMissingError", (Exception,), {})(f"{ticker}: possibly delisted; no price data found")


class RetryPolicy(unittest.TestCase):
    def setUp(self):
        helpers.seed_file(["OKONE", "GONE", "LIMITED"])
        self._patches = [mock.patch.object(config, "RETRY_BASE", 0.0), mock.patch.object(config, "RETRY_PASS_PAUSE", 0),
                         mock.patch.object(scan.time, "sleep", lambda s: None)]
        for p in self._patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self._patches])

    def _hist(self, calls):
        def hist(ticker, interval, start):
            calls[ticker] = calls.get(ticker, 0) + 1
            if ticker == "GONE.NS":
                raise _no_data(ticker)
            if ticker == "LIMITED.NS":
                raise _rate_limit()
            return helpers.synth(1, 400)
        return hist

    def test_no_data_is_not_retried_by_default(self):
        calls = {}
        with mock.patch.object(config, "RETRY_NO_DATA", False), mock.patch.object(market_data, "_history", self._hist(calls)):
            scan.main(["--force", "--timeframes", "1d", "--workers", "2"])
        self.assertEqual(calls["GONE.NS"], 1)                                  # one download, no retry pass for a dead ticker

    def test_no_data_can_be_retried_when_switched_on(self):
        calls = {}
        with mock.patch.object(config, "RETRY_NO_DATA", True), mock.patch.object(market_data, "_history", self._hist(calls)):
            scan.main(["--force", "--timeframes", "1d", "--workers", "2"])
        self.assertGreater(calls["GONE.NS"], 1)

    def test_retrying_stops_when_a_pass_recovers_nothing(self):
        calls = {}
        with mock.patch.object(config, "RETRY_PASSES", 5), mock.patch.object(market_data, "_history", self._hist(calls)):
            scan.main(["--force", "--timeframes", "1d", "--workers", "2"])
        # first pass + ONE retry pass (recovered 0 of 1 -> stop), each costing MAX_RETRIES attempts
        self.assertEqual(calls["LIMITED.NS"], 2 * config.MAX_RETRIES)

    def test_run_scan_still_reports_no_data_by_default(self):
        retry = {}
        scan.run_scan(common.load_stocks(), lambda s: ["1d"], workers=2, history_fn=self._hist({}), progress_every=1000, retry_out=retry)
        self.assertEqual(retry, {"GONE": ["1d"], "LIMITED": ["1d"]})


if __name__ == "__main__":
    unittest.main()
