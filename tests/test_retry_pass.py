"""Names Yahoo refuses or has no candles for are retried inside the run, and the reason is kept for the dashboard."""
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


class RetryPass(unittest.TestCase):
    def setUp(self):
        helpers.seed_file(["OKONE", "GONE", "LIMITED"])
        self._patches = [mock.patch.object(config, "RETRY_BASE", 0.0), mock.patch.object(config, "RETRY_PASS_PAUSE", 0),
                         mock.patch.object(scan.time, "sleep", lambda s: None)]
        for p in self._patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self._patches])

    def test_run_scan_reports_what_failed_and_keeps_the_reason(self):
        def hist(ticker, interval, start):
            if ticker == "OKONE.NS":
                return helpers.synth(1, 400)
            raise _rate_limit() if ticker == "LIMITED.NS" else _no_data(ticker)
        retry = {}
        scan.run_scan(common.load_stocks(), lambda s: ["1d"], workers=2, history_fn=hist, progress_every=1000, retry_out=retry)
        self.assertEqual(retry, {"GONE": ["1d"], "LIMITED": ["1d"]})
        d = {r["symbol"]: r for r in helpers.read()}
        self.assertEqual(d["OKONE"]["scanner_status"], "OK")
        self.assertTrue(d["GONE"]["scan_error"].startswith("NO_DATA"))        # not just "too few candles"
        self.assertEqual(d["LIMITED"]["scanner_status"], "ERROR")
        self.assertIn("Too Many Requests", d["LIMITED"]["scan_error"])

    def test_main_retries_a_rate_limited_name_and_recovers_it(self):
        calls = {"LIMITED.NS": 0}

        def hist(ticker, interval, start):
            if ticker == "LIMITED.NS":
                calls[ticker] += 1
                if calls[ticker] <= config.MAX_RETRIES:        # the whole first pass is refused
                    raise _rate_limit()
            elif ticker == "GONE.NS":
                raise _no_data(ticker)
            return helpers.synth(len(ticker), 400)
        with mock.patch.object(market_data, "_history", hist):
            self.assertEqual(scan.main(["--force", "--timeframes", "1d", "--workers", "2"]), 0)
        d = {r["symbol"]: r for r in helpers.read()}
        self.assertEqual(d["LIMITED"]["scanner_status"], "OK")                # recovered by the retry pass
        self.assertEqual(d["OKONE"]["scanner_status"], "OK")
        self.assertNotEqual(d["GONE"]["scanner_status"], "OK")                # still no data: stays an issue, with its reason
        self.assertTrue(d["GONE"]["scan_error"].startswith("NO_DATA"))

    def test_retry_can_be_switched_off(self):
        calls = {"n": 0}

        def hist(ticker, interval, start):
            if ticker == "LIMITED.NS":
                calls["n"] += 1
                raise _rate_limit()
            return helpers.synth(2, 400)
        with mock.patch.object(config, "RETRY_PASSES", 0), mock.patch.object(market_data, "_history", hist):
            scan.main(["--force", "--timeframes", "1d", "--workers", "2"])
        self.assertEqual(calls["n"], config.MAX_RETRIES)                       # only the in-fetch retries, no extra pass


if __name__ == "__main__":
    unittest.main()
