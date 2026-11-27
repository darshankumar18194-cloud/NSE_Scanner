# Upgrade notes (2026-11-27)

Fixes for the failed scheduled scan (run of 2026-11-26: scan finished, the push to `main` failed).

| Area | Change |
|---|---|
| `.github/workflows/scan.yml` | The commit step no longer does `git pull --rebase` (it conflicted on `stocks.json` / `stocks_1h.json` when `main` moved during the ~1 h scan). It now puts this run's generated files (`stocks.json`, `stocks_1h.json`, `board_*.json`, `detail/`) on top of the newest `origin/main` and pushes, with 5 retries. Other files in `shared-data` (e.g. `holidays.txt`) are never touched. |
| `.github/workflows/daily-scan.yml` | **Removed.** A second workflow that pushed the same data files without sharing `scan.yml`'s concurrency group; the likely source of the conflicting push. |
| `scan_market_structure_combined.py`, `config.py` | Only real download errors are retried; dead tickers (`NO_DATA`) no longer are (`NSE_RETRY_NO_DATA=1` restores the old behaviour). Retrying stops when a pass recovers < `RETRY_MIN_RECOVERY` (5 %). In the failed run the two retry passes took ~43 min and recovered 15 of 614 symbols. |
| `enrich_stocks.py`, `config.py` | Enrich stops after `ENRICH_ABORT_AFTER` (60) lookups with zero data (Yahoo refusing the IP: HTTP 401 / 429). Remaining records stay unmarked and are retried on the next run. The to-do list is shuffled so the check sees a representative sample. |
| `indicators.py` | ADX seed guard: removes the `Mean of empty slice` warning for flat/zero-range stocks. Results are identical (checked on 2,000 random series). |
| `tests/` | New: `test_retry_policy.py`, `test_enrich_abort.py`, `test_indicators_adx.py`. |

Test suite: 254 tests before, 263 after, all passing.
Not changed: the detection engine, dashboards, schedule, data files. Generated data (`stock/`, `signals/`, `shared-data/detail`, `stocks*.json`, `board_*.json`) is not part of this package.
