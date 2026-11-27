"""Enrich stops early when Yahoo refuses every lookup (HTTP 401 / 429), and leaves the untouched records unmarked."""
import time
import unittest
from unittest import mock

import config
import enrich_stocks as enrich
from tests import helpers

SYMS = [f"S{i:02d}" for i in range(40)]


class EnrichAbort(unittest.TestCase):
    def test_stops_when_nothing_comes_back(self):
        helpers.seed_file(SYMS)
        calls = []

        def refused(ticker):
            calls.append(ticker)
            time.sleep(0.02)                              # a real lookup takes time; an instant stub would finish before the loop can cancel
            return {}
        with mock.patch.object(config, "ENRICH_ABORT_AFTER", 5):
            self.assertEqual(enrich.main(["--force", "--workers", "1"], info_fn=refused), 0)
        self.assertLessEqual(len(calls), 7)                                       # 5 lookups + at most the one in flight
        marked = [r for r in helpers.read() if r.get("enrich_status") == "NO_INFO"]
        self.assertLessEqual(len(marked), 7)                                      # the rest stay unmarked: retried next run

    def test_keeps_going_when_some_lookups_succeed(self):
        helpers.seed_file(SYMS)
        calls = []

        def mixed(ticker):
            calls.append(ticker)
            return {"marketCap": 5e11, "sector": "Energy"} if len(calls) == 3 else {}
        with mock.patch.object(config, "ENRICH_ABORT_AFTER", 5):
            enrich.main(["--force", "--workers", "1"], info_fn=mixed)
        self.assertEqual(len(calls), len(SYMS))                                   # one success -> no abort, every name looked up

    def test_abort_can_be_switched_off(self):
        helpers.seed_file(SYMS)
        calls = []
        with mock.patch.object(config, "ENRICH_ABORT_AFTER", 0):
            enrich.main(["--force", "--workers", "1"], info_fn=lambda t: calls.append(t) or {})
        self.assertEqual(len(calls), len(SYMS))


if __name__ == "__main__":
    unittest.main()
