# NSE SMC + Pattern Scanner and Dashboard

Scans the whole NSE universe on two timeframes and shows the result in a static dashboard:

* **Market structure (Smart Money Concepts):** swing highs/lows, BOS / CHoCH, Strong/Weak High/Low.
* **Candlestick patterns (60) and 15 other signals:** squeeze, volume, trend and structure events, each scored 0-100.

| Timeframe | Scans per day | When (IST) | Candle used |
|---|---|---|---|
| **1D** | **1** | 15:50 (the daily candle is final at 15:45) | closed daily candle |
| **1H** | **7** | 10:20 11:20 12:20 13:20 14:20 15:20 15:35 | the hourly candle that just closed (10:15 ... 15:15, plus the 15-minute 15:15-15:30 candle) |

Only **closed** candles are analysed, so a signal never appears and then vanishes when the candle closes.

## Layout

```
config.py                            all settings, incl. the per-timeframe PROFILES (1D / 1H)
common.py                            IST clock, atomic strict-JSON store, locks, retry, logging
smc_engine.py                        the structure engine (pure functions, no I/O)
indicators.py                        ATR, Bollinger, Keltner, ADX, OBV, CMF, Ichimoku ...
patterns.py                          60 candlestick pattern detectors
signals.py                           15 events, current-state readings, confirmation rule, 0-100 score
bases.py, bases_ext.py, base_utils.py the 21 base patterns + Stage Analysis + Base Count (see "Base patterns" below)
schedule.py                          exactly when each timeframe is due
detail_store.py                      per-stock detail files  shared-data/detail/<SYMBOL>.json
market_data.py                       Yahoo access; drops the unfinished candle; keeps Volume
scan_market_structure_combined.py    1D + 1H scan: structure + patterns + signals
refresh_all_prices.py                fast batch price refresh
enrich_stocks.py                     sector / market cap / index membership / cap class
update_universe.py                   keep stocks.json in sync with NSE's official lists
update_index_lists.py                refresh the index-constituent lists
index_data.py, universe_data.py      static fallback lists
add_stock.py                         add one symbol
validate_data.py                     strict publish gate (see below)
master_sync_all.py                   runs the pipeline steps in order
cleanup_legacy_child_pages.py        one-off: remove old per-stock HTML folders
index.html                           home page linking both dashboards
signals/index.html, detail.html      Signals dashboard: top setups, filters, chart, score breakdown
signals/signals.css, signals.js      its stylesheet and helpers
main-dashboard/index.html            the US-style dashboard (tabs, Top 20 boards, SMC + pattern, 1D/1H switch)
stock/index.html                     one per-stock page
assets/style.css, common.js          the dashboard's stylesheet and data adapter
levels.py                            support / resistance level finder (1H)
build_board.py                       dashboard extras per timeframe -> shared-data/board_1d.json, board_1h.json
shared-data/stocks.json              the data (seed is [] - run the universe step; stocks_1h.json, detail/, board_*.json are generated)
shared-data/holidays.txt             optional NSE holiday list
tests/                               unit + pipeline + schedule + signal + validation tests (no network)
tests/base_shapes.py, test_bases*.py synthetic price shapes that build each base pattern, and near-misses that must be rejected
tests/browser/                       optional headless-browser check of the dashboard (Playwright, not run by pytest)
.github/workflows/scan.yml           the 8 daily GitHub runs, history trim, site deploy
.github/workflows/pages.yml          publishes the site when you push changes
.github/workflows/tests.yml          tests on every push
.nojekyll                            lets GitHub Pages serve the folders as they are
*.bat                                Windows launchers
```

## The dashboard (US-style)

`index.html` opens `main-dashboard/index.html`, the same dashboard as the US scanner, on NSE data:

* **Tabs (8):** SMC + pattern, SMC + pattern + base, SMC signals, Pattern signals, Base patterns, All symbols, Signal feed, Watchlist, with the Top 20 boards and filters. The 1D / 1H switch changes the whole dashboard.
* **1D / 1H switch** in the header. The choice is remembered. "Signals (detailed)" opens the separate Signals pages.
* **SMC + pattern tab, candle strips, relative volume:** read from `shared-data/board_1d.json` / `board_1h.json`,
  built after every scan by `build_board.py` from the per-stock detail files. `stocks.json` itself stays small.
* **Support / resistance levels:** found on 1H candles by `levels.py` during the hourly scan and shown on the stock page.
  Switch off with `LEVELS_ON` in `config.py`.
* `stock/index.html` is the per-stock page (candle chart, signals, indicators, levels).

Currency is shown in rupees. Prices come from Yahoo, so values can differ slightly from NSE's own.

## Base patterns (21 bases, 1D and 1H)

Twenty-one named bases (group `base`), each with a **direction**, a **trigger level**, a **stop** reference, a **status** and a
0-100 score from the same formula as every other signal. They run on both timeframes; the rules are counted in candles of the
timeframe, so a 25-candle base lasts about five weeks on 1D and about 3.5 trading days on 1H. `BASE_ON` / `BASE_1H_ON` in
`config.py` switch the whole feature / the 1H part off. The first nine detectors are in `bases.py`, the other twelve in
`bases_ext.py`, shared helpers (swing points, line fits, RSI) in `base_utils.py`; every number is a constant in `config.py` with a
one-line comment saying whether it comes from the guides or is a choice made here.

| Base | Direction | What the code looks for (all numbers are in config.py) |
|---|---|---|
| VCP | bull | 2+ pullbacks, each shallower than the last (first 10-35%, last under 10%), volume drying up, 15-65 candles, after a 30%+ advance |
| Cup with Handle | bull | Cup 12-33% deep, 35-130 candles, rounded (not V); handle 5-25 candles, under 12% deep, in the upper half, on lower volume |
| Flat Base | bull | 25-65 candles, under 15% deep, sideways, after a 20%+ advance |
| Double Bottom | bull | Two swing lows 15-60 candles apart, the second undercutting the first by 0.1-5%, middle peak 8%+ above the lows |
| High Tight Flag | bull | +100% in 20-40 candles, then a 10-25 candle flag pulling back under 25% |
| Power Play | bull | +50% in 10-40 candles, then a 5-20 candle flag pulling back under 12%, near the 250-candle high |
| Ascending Base | bull | 3+ pullbacks of 5-20%, each low 1%+ higher, 30-80 candles |
| Darvas Box | bull | Top and bottom each confirmed by 3 candles, box at most 15% tall, 5-40 candles, near the 250-candle high |
| The Ledge | bull | A 5-15 candle pause under 10% deep on shrinking volume, near the high of a larger base that had pulled back 10%+ |
| Triangles | ascending bull, descending bear, symmetrical two-sided | 20-80 candles, lines through the swing highs / lows fit within 1.5%, the gap at the end at most half the gap at the start |
| Flags and Pennants | with the pole | Pole 15-50% at 1%+ per candle, then 5-20 candles retracing at most 50% of it; a flag is parallel, a pennant converges |
| Wedges | rising bear, falling bull | 20-60 candles, both lines moving the same way 3%+ and converging |
| Rectangle | two-sided | 25-150 candles, 5-25% tall, 2+ touches of the ceiling and of the floor (within 1.5%) |
| Diamond | two-sided | 40-100 candles: candle range widens 30%+ then narrows to 60% of the widest, little net price change |
| Rounding Bottom | bull | 60-250 candles, 10-50% deep, U-shaped (curve fit R2 0.7+, not V), back within 10% of where it began |
| Broadening Wedge | **warning** | Higher highs and lower lows, the gap grows 30%+. A warning sign: no trigger level, never a breakout |
| Three Pushes | up = bear, down = bull | Three successive highs (lows), each on weaker RSI; trigger = a close beyond the pullback between pushes 2 and 3 |
| Bump and Run | bear | A 40-candle lead-in trendline, then a bump 20%+ above it and 1.5x steeper; trigger = a close back under the line |
| Ross Hook | bull / bear | A 1-2-3 formation (reaction 5%+, point 3 within 3% of point 1) then a 1-3 candle hook; no volume rule |
| Wyckoff Accumulation | bull | Simplified: a 25%+ fall, a 30-120 candle range, then a Spring (undercuts support 0.5-5%, closes back above within 3 candles) on drying volume |
| Supply & Demand Zones | demand bull, supply bear | A tight 1-5 candle base then a 3-ATR move away; signal on the first return into the zone with compression |

**Direction.** Two-sided bases (Rectangle, Diamond, symmetrical Triangle) are neutral while forming; the side that breaks decides
(`dir` becomes bull or bear on the breakout). The stop of a two-sided base is the opposite boundary. A warning has no levels.
The Base tab hides bearish bases and warnings by default (Direction filter).

**Status.** *Forming*: the shape is complete and the close is near its trigger (within 5%, 15% for Wyckoff). *Breakout*: the next
candle closes beyond the trigger on volume of at least 1.4x the average (1.2x for Flat Base, Power Play, Three Pushes, Bump and Run,
Supply & Demand; any volume for the Ross Hook). A close beyond it on weaker volume is not a breakout: the base stays forming,
flagged low volume. *Failed*: a close beyond the stop, or a breakout that closes back inside within 5 candles. A breakout keeps
its own candle even if it fails later (`fail_since`). A breakout candle that is 1.5 ATR tall on 1.4x volume is tagged **fast**,
and Rectangle, Triangles, Flags, Diamond and Rounding Bottom carry a measured-move **target** (the pattern height projected).

**No repainting.** Only closed candles are used. Every decision at candle *i* uses candles up to *i* only (swing points are
found in one forward pass and carry the candle on which each was confirmed). A base armed on one candle is judged on the next;
later candles add the next event (forming, breakout, failed) but never move or erase an earlier one. Each pattern's walk starts at
least its longest window before the stored window (`LEAD_BARS` in bases.py). `tests/test_bases*.py` check this on random prices,
and also that shifting the start of the data changes nothing.

**How long a signal is kept.** A breakout or failure is stored for the profile's window (20 candles on 1D). A base still *forming* is
kept while it stands, so its `since` can be older (up to 275 candles for the Rounding Bottom); `validate_data.py` allows that for
forming base signals only.

**Dashboard.** *Base patterns* tab: 21 buttons (one per base, with its live count) group the bases; clicking one shows it alone.
Every row has a **Base Rank (0-100)**: pattern quality 25, entry timing 20, stage 15, relative strength 15, SMC trend agreeing 8, a
confirmed candle pattern in the same direction 7, base count 5, liquidity and risk 5 (hover a rank to see the parts). The **Trader
style** switch changes the weights and sets starting filters: Balanced, Breakout trader (weights entry timing, status = breakout),
Early (status = forming), Positional (stage 2, relative strength 60) and Conservative (stage 2, relative strength 70, risk 8%,
turnover 2 crore, min rank 60). Other filters: Direction, status, stage, recency, minimum turnover, maximum risk to the stop, minimum
relative strength, minimum rank, and two tick-boxes (SMC aligned, confirmed candle pattern). *SMC + pattern + base* tab: the bullish
or bearish bases where the SMC trend AND a confirmed candle pattern of the last 10 candles both point the same way. Base signals are
not listed in the Pattern signals tab. On 1H, stage, base count and relative strength are not available (daily readings), so the rank
is rescaled without them.

**History used.** 1D downloads `DAILY_LOOKBACK_DAYS` = 1,100 days (about 750 candles; the engine reads the newest 700). 1H downloads 700
days (Yahoo's limit is 730) and analyses the newest 1,000 candles. Stage Analysis needs about 210 daily candles.

**Two readings (information only):** *Stage Analysis* (Weinstein: the 150-candle average = 30 weeks, and its 20-candle slope; stage 2
rising, 4 falling with price below, 3 no longer rising after an advance, 1 no longer falling with no advance before it) and the
*Base Count* (completed 25+ candle consolidations since the stock last closed below its 150-candle average; "Base 1 / 2 / 3+" and a
climactic run-up flag). Also stored for the rank: the 6-month return and the average daily turnover.

**Be honest about what this is.** These are code-detected chart shapes. They produce false signals, and the noisy ones are the
trendline shapes and the Ross Hook. On pure random-walk prices, 55% of stocks show some live base on a given day and 25% a breakout
(Ross Hook 19%, Flat Base 13%, Rectangle 12%, most others under 5%). Real markets are not random, but the rank, the filters and the
trader styles exist because the raw list is long. The tests prove the rules do what `config.py` says on synthetic prices; how the signals
behave on real NSE data has not been tested and no win rate is claimed. Cost, measured on synthetic series of the real length:
about 34 ms of CPU per stock on 1D and 26 ms on 1H (about 3 minutes for 3,050 stocks on both), and about +2.3 MB on
`board_1d.json`, +1.1 MB on `board_1h.json` and +3.2 MB over all `detail/` files.

## Deploying to a new GitHub account

1. Create a new repository and upload everything in this folder (keep the folder structure; the `.github`
   folder must stay at the top level).
2. **Settings > Actions > General > Workflow permissions:** choose *Read and write permissions*.
3. **Settings > Pages > Build and deployment > Source: choose "GitHub Actions"** (not "Deploy from a branch").
   The `deploy` job in `scan.yml` publishes the site after every scan, and `pages.yml` publishes when you push
   changes yourself (scan commits made by the bot cannot trigger other workflows, which is why the scan workflow
   publishes by itself). The site opens at `https://<user>.github.io/<repo>/`.
4. **Actions > NSE scan > Run workflow** once, with steps `universe scan prices enrich board validate` and *force* ticked. The first
   run covers the whole universe and is the slow one (up to about two hours). After that, each run only does
   what a new candle made due.
5. The scheduled runs (Monday to Friday) take over. The workflow file lists the exact cron lines.

`shared-data/stocks.json` ships as an empty seed (`[]`). The `universe` step fills it with the real NSE lists. If NSE blocks GitHub's servers,
run `update_nse_universe.bat` (or `python update_universe.py`) on your own computer once and commit the result.
To rebuild from nothing: set `stocks.json` to `[]` and run `python master_sync_all.py --steps universe scan prices enrich board validate`.

## Running locally

```
install_requirements.bat                      # first time
python master_sync_all.py                     # scan, prices, enrich, validate
python master_sync_all.py --steps scan        # one step
python master_sync_all.py --force --workers 4 # gentler on Yahoo's rate limit
python scan_market_structure_combined.py              # only what is due right now
python scan_market_structure_combined.py --force      # everything, now
python scan_market_structure_combined.py --timeframes 1h --limit 20
python scan_market_structure_combined.py --no-signals # structure only (the old behaviour)
python validate_data.py                       # the publish gate (--strict makes warnings errors)
python update_universe.py [--dry-run] [--prune]
python update_index_lists.py && python enrich_stocks.py --indices-only   # after March/September rebalancing
python add_stock.py TCS "Tata Consultancy Services"
python -m pytest -q tests
```

## Data contract

`stocks.json` is a flat array, so the existing dashboard keeps working. Existing fields are unchanged.
New fields use the same suffix convention (`name` for 1D, `name_1h` for 1H; `stocks_1h.json` exposes the 1H
ones under the plain name):

| Field | Meaning |
|---|---|
| `signal_status` | `OK`, `SKIPPED` (bonds / funds), `INSUFFICIENT_DATA` or `ERROR` |
| `bars`, `last_bar_time` | candles analysed, time of the newest closed candle |
| `sig_best_score`, `sig_bull_score`, `sig_bear_score` | 0-100 confluence scores |
| `sig_best_name`, `sig_best_dir`, `sig_best_since` | the best signal, its direction, candles ago |
| `sig_bull_name`, `sig_bull_since`, `sig_bear_name`, `sig_bear_since` | the best bullish and the best bearish signal and how many candles ago |
| `sig_bull_count`, `sig_bear_count` | number of stored signals per direction |
| `sig_top` | up to 3 best signals `{name, dir, since, score, confirm}` |
| `squeeze_state`, `compression_layers` | `off` / `on` / `fired`, number of compression layers on |

The heavy data is **not** in `stocks.json`. It lives in `shared-data/detail/<SYMBOL>.json`
(`M&M` is stored as `M~26M.json`, see `detail_store.safe_name`):

```json
{"symbol": "TCS", "updated_at": "2026-11-06 15:50:12 IST",
 "1d": {"last_bar_time", "bars", "signals": [...], "context": {...}, "scores": {...},
        "candles": [[time, open, high, low, close, volume], ...]},
 "1h": {...}}
```

## Timeframe settings (`config.PROFILES`) - starting values, tune after you watch real output

| Setting | 1H | 1D |
|---|---|---|
| History downloaded | 700 days | 540 days |
| Signals kept (formed within the last N candles) | 35 (5 sessions) | 20 (about a month) |
| Freshness score fades to 0 over | 20 candles | 10 candles |
| Inside Bar / NR4 / NR7 kept for | 7 candles | 3 candles |
| "Lowest 20% of history" window | 441 candles | 126 candles |
| OBV / A-D divergence window | 30 | 20 |
| Candles saved for the chart | 40 | 60 |
| Annualised-volatility factor | sqrt(7 x 252) | sqrt(252) |

The SMC swing length stays 50 on both timeframes. Bonds and funds (`SIGNAL_SKIP_GROUPS`) get the
structure scan only.

## What `validate_data.py` blocks

It runs before every commit and exits 1 (so nothing is published) when: `stocks.json` is not strict JSON
(NaN / Infinity), a symbol is duplicated or missing, a scanned record has an unknown status, a bad trend, a rank
score outside 0-110, a non-positive price or a malformed date; a signal has a bad direction, a `since`
outside the stored window or a score outside 0-100; a detail file or timeframe block is missing; or not one
symbol scanned OK. Stale records only warn.

## Design notes

* `scanner_status` per record: `PENDING_SCAN`, `OK`, `STALE` (Yahoo failed, showing the last good scan),
  `ERROR`, `INSUFFICIENT_DATA` (fewer than `config.MIN_BARS` candles), `NO_PIVOTS`.
* A failed Yahoo request never wipes good data; the record is kept and marked `STALE`.
* Cap classification defaults to rank (top 100 large, next 150 mid, rest small); change `CAP_METHOD` in `config.py`.
* `NSE_DASH_HOME` overrides where data and logs live (the tests use it to run against a throwaway folder).
* Only one pipeline run at a time (`shared-data/.pipeline.lock`).

## Things to know

* **Repo growth.** The 1H scan changes most detail files seven times a day, and every change is a commit. To stop
  the repository growing without limit, the last step of `scan.yml` keeps only the newest 10 commits (it rewrites
  history and force-pushes). Files are not affected, only old versions of them, so you cannot go back to an old
  data snapshot. This needs the `main` branch to have **no branch protection** (a protected branch refuses the
  force-push). GitHub frees the storage of the dropped commits with a delay, so the repository size shown in
  Settings can lag. The per-stock detail files (instead of one giant `stocks.json`) keep each commit small.
* **GitHub's runners and Yahoo.** Yahoo rate-limits shared cloud IPs more than home connections. The scan retries
  and never wipes good data, but if many rows turn `STALE`, lower the worker count (`--workers`).
* **Daily gap patterns.** Patterns the Handbook describes with a gap use the same relaxed rule on 1D as on 1H
  (see the docstring in `patterns.py`), so 1D may show a few extra, weaker matches.
* **Not modelled:** NSE holidays unless listed in `shared-data/holidays.txt`; special sessions.
* **Two dashboards.** `main-dashboard/` and `stock/` are your original pages and are untouched. The new **Signals**
  dashboard (`signals/`) reads the new fields and the detail files. It has the top ten bullish and bearish setups,
  filters (direction, minimum score, formed within N candles, squeeze, size, sector), a sortable table, and a stock
  page with a candlestick chart marking every signal, the score breakdown, the indicator readings and the full
  signal list. The home page (`index.html`) links to both. To test locally: `python -m http.server` in the project
  folder, then open `http://localhost:8000/`.

* **Base rules.** Every base has its own shape and breakout rules (for example Darvas Box needs 1.5x volume and a clean close, Flat Base only 1.2x). They are all listed in `BASE_RULES.md`, and the numbers live in `config.py`.
