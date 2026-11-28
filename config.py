"""Central settings. Everything tunable lives here."""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

# NSE_DASH_HOME lets the tests (or you) point the whole system at another folder.
CODE_DIR = Path(__file__).resolve().parent
BASE_DIR = Path(os.environ.get("NSE_DASH_HOME") or CODE_DIR)
DATA_DIR = BASE_DIR / "shared-data"
LOG_DIR = BASE_DIR / "logs"
STOCKS_JSON = DATA_DIR / "stocks.json"
STOCKS_1H_JSON = DATA_DIR / "stocks_1h.json"  # derived view, always regenerated
INDEX_LISTS_JSON = DATA_DIR / "index_lists.json"  # optional, written by update_index_lists.py
DETAIL_DIR = DATA_DIR / "detail"  # one file per stock: signals, context, scores, candles (both timeframes)
HOLIDAYS_FILE = DATA_DIR / "holidays.txt"  # optional: one YYYY-MM-DD per line, NSE trading holidays
PIPELINE_LOCK = DATA_DIR / ".pipeline.lock"
WRITE_LOCK = DATA_DIR / ".write.lock"

# ---- Market-structure engine (same defaults as before) ----------------------
SWING_LEN = 50  # LuxAlgo "swings length"
MIN_BARS = SWING_LEN * 2 + 20  # fewer bars than this -> INSUFFICIENT_DATA
DAILY_LOOKBACK_DAYS = 1100          # about 750 daily candles: the longest base (250) + its trend check and the 30-week average need a long history; the engine reads the newest 700 (calc_bars)
# Yahoo refuses 1h requests that reach back more than ~730 days. The start date is a calendar date
# counted in IST, which can add up to a day (plus the 5h30 offset from UTC) to the real range, so 729
# can be rejected. 700 leaves a safe margin and still gives ~3,300 hourly bars.
HOURLY_LOOKBACK_DAYS = 700
DAILY_DATE_FMT = "%Y-%m-%d"
HOURLY_DATE_FMT = "%Y-%m-%d %H:%M"

# Only analyse candles that have finished. Set to False to restore the old behaviour (not recommended:
# a still-forming candle can show a break of structure that disappears when the candle closes).
CLOSED_CANDLES_ONLY = True

# ---- Market clock (IST, no DST) ---------------------------------------------
MARKET_OPEN = (9, 15)
MARKET_CLOSE = (15, 30)
FINAL_BAR_READY = (15, 45)  # after this the day's candle is final on Yahoo
SCAN_DELAY_MIN = 3  # an hourly candle is scanned this many minutes after it closes (Yahoo publish lag)

# ---- Signals: shared by both timeframes -------------------------------------
SQUEEZE_PCT = 0.20  # compression = in the lowest 20% of its own recent history
BB_LEN, BB_MULT = 20, 2.0
KC_MULT = 1.5  # Keltner channel width for the TTM squeeze
BREAKOUT_LOOKBACK = 20  # "recent range" used by breakout rules
VDU_RATIO = 0.6  # volume dry-up: typical relative volume below this
VOL_SPIKE_RATIO = 2.0  # volume spike: relative volume at or above this
PIVOT_VOL_LOOKBACK = 10  # pocket pivot: compare against down bars in the last N candles
FVG_MIN_ATR = 0.25  # fair value gap must be at least this many ATRs wide
MAX_SIGNALS = 60  # hard cap per symbol and timeframe
TOP_BOARD_SIZE = 20
# Instrument groups that only get the market-structure (SMC) scan: their volume/price data is not
# suitable for candlestick and volume signals.
SIGNAL_SKIP_GROUPS = {"DEBT", "FUND"}
STALE_WARN_FRACTION = 0.25  # validate step warns when more than this share of symbols is STALE/ERROR


@dataclass(frozen=True)
class Profile:
    """Everything that depends on the timeframe. One profile is passed through the signal code."""
    key: str  # "1d" | "1h"
    label: str  # "1D" | "1H"
    interval: str  # Yahoo interval
    suffix: str  # field-name suffix in stocks.json ("" for daily, "_1h" for hourly)
    stamp: str  # field that holds the last scan time
    lookback_days: int  # how far back to download
    date_fmt: str
    calc_bars: int  # newest candles fed to the pattern / indicator engine
    recent_candles: int  # candles saved per stock for the child-page chart
    store_bars: int  # keep every signal formed within the last N candles
    fresh_fade_bars: int  # freshness score falls from full marks to 0 over this many candles
    range_keep_bars: int  # Inside Bar / NR4 / NR7 are one-candle triggers: keep them only this long
    pct_lookback: int  # window for "lowest X% of recent history"
    div_lookback: int  # OBV / A-D divergence window
    periods_per_year: int  # candles per year, for annualised volatility
    top_board_window: int  # the Top bullish / Top bearish boards look at this many candles
    window_options: Tuple[int, ...]  # "formed within last" choices for the dashboard
    slot_vol_days: int = 50  # relative volume = volume / average of the same time-of-day slot over N sessions


PROFILES = {
    # 1 candle per day. The "same time-of-day slot" volume comparison becomes a plain 50-day average.
    "1d": Profile(key="1d", label="1D", interval="1d", suffix="", stamp="scanned_at",
                  lookback_days=DAILY_LOOKBACK_DAYS, date_fmt=DAILY_DATE_FMT,
                  calc_bars=700, recent_candles=60,
                  store_bars=20, fresh_fade_bars=10, range_keep_bars=3,
                  pct_lookback=126, div_lookback=20, periods_per_year=252,
                  top_board_window=10, window_options=(1, 2, 3, 5, 7, 10, 20)),
    # 7 candles per day on NSE (09:15 ... 15:15, the last one is 15 minutes long) - same count as the US scanner.
    "1h": Profile(key="1h", label="1H", interval="1h", suffix="_1h", stamp="scanned_at_1h",
                  lookback_days=HOURLY_LOOKBACK_DAYS, date_fmt=HOURLY_DATE_FMT,
                  calc_bars=1000, recent_candles=40,
                  store_bars=35, fresh_fade_bars=20, range_keep_bars=7,
                  pct_lookback=441, div_lookback=30, periods_per_year=7 * 252,
                  top_board_window=20, window_options=(3, 6, 7, 10, 14, 20, 35)),
}
TIMEFRAMES = ("1d", "1h")

# ---- Base patterns (1D only): VCP, Cup with Handle, Flat Base, Double Bottom, High Tight Flag, Power Play,
# ---- Ascending Base, Darvas Box, The Ledge + Stage Analysis and Base Count readings (see bases.py) --------------
# Every number below comes from the Pre-Breakout guides (Vol. I-III) unless the line says "chosen": the guides are
# vague there, so the value is this project's own decision. Distances are in trading days (5 per week), depths in %.
BASE_ON = True                    # False = switch every base signal and reading off
BASE_LEAD_BARS = 70               # chosen: the walk starts this many candles before the stored window (longest base 65 + 5), so a decision never depends on where the walk starts (measured: 25 gave rare differences, 70 gave none)
BASE_GATE_PCT = 30                # chosen: skip a candle whose close is more than 30% below its 130-candle high (no base can be forming)
BASE_PRIOR_WINDOW = 120           # chosen: candles before a base that are searched for the prior advance
BASE_PRIOR_RISE_PCT = 30          # chosen: the stock must have risen at least 30% into the base (VCP, Cup, Double Bottom, Ascending, Ledge)
BASE_BREAKOUT_VOL = 1.4           # guide: breakout volume 40-50% above the 50-day average
BASE_BREAKOUT_VOL_EASY = 1.2      # guide: Flat Base / Power Play are already shallow, so "modest" volume is enough (1.2x chosen)
BASE_NEAR_PIVOT_PCT = 5           # chosen: a base is "forming" while the close is within 5% below its pivot
BASE_MIN_DEPTH_PCT = 1.0          # chosen: a base must be at least 1% deep: a price that never moves (halted / illiquid stock) is not a base
BASE_FAIL_BARS = 5                # chosen: a breakout that closes back below its pivot within 5 candles has failed
VCP_MIN_BARS, VCP_MAX_BARS = 15, 65   # chosen: 3 to 13 weeks
VCP_SWING_PCT = 4                 # chosen: a swing is a move of at least 4%
VCP_FIRST_MIN, VCP_FIRST_MAX = 10, 35  # chosen: first pullback 10-35% deep
VCP_LAST_MAX = 10                 # guide: the last contraction is tight (example 25 -> 15 -> 8)
CUP_MIN_BARS, CUP_MAX_BARS = 35, 130   # chosen: 7 to 26 weeks
CUP_DEPTH_MIN, CUP_DEPTH_MAX = 12, 33  # guide: cup 12-33% deep
CUP_RIM_RECOVERY = 10             # chosen: the right rim must get back within 10% of the left rim
CUP_U_MEAN_MAX = 0.42             # chosen: U not V - the average close sits in the lower 42% of the cup (parabola 0.33, V 0.50)
CUP_SIDE_MIN = 10                 # chosen: the bottom is at least 10 candles from each rim
HANDLE_MIN_BARS, HANDLE_MAX_BARS = 5, 25   # chosen: 1 to 5 weeks
HANDLE_MAX_PULLBACK = 12          # chosen: the handle pulls back at most 12% and stays in the upper half of the cup (guide)
FLAT_MIN_BARS, FLAT_MAX_BARS = 25, 65  # guide: at least 5 weeks (65 chosen as the upper limit)
FLAT_MAX_DEPTH = 15               # guide: under 15% deep
FLAT_PRIOR_RISE_PCT = 20          # chosen: "moderate advance" before a flat base
BASE_LEVEL_START_RATIO = 0.99     # chosen: a flat base / ledge starts at its top: its first close is at least 99% of the window's average close
FLAT_MAX_DRIFT_PCT = 8            # chosen: sideways, not climbing: the close at the end is within 8% of the close at the start
DB_LOW_GAP_MIN, DB_LOW_GAP_MAX = 15, 60   # chosen: the two lows are 3 to 12 weeks apart
DB_UNDERCUT_MIN, DB_UNDERCUT_MAX = 0.1, 5.0  # guide: the second low undercuts the first "by a small amount" (0.1-5% chosen)
DB_PEAK_MIN_RISE = 8              # chosen: the middle of the W is at least 8% above the first low
DB_SWING_BARS = 10                # chosen: the first low must be a real swing low: no lower low in the 10 candles before it
DB_MIN_BARS, DB_MAX_BARS = 35, 120     # chosen: whole W is 7 to 24 weeks
HTF_RISE_PCT = 100                # guide: +100% ...
HTF_RALLY_MIN, HTF_RALLY_MAX = 20, 40  # guide: ... in 4 to 8 weeks
HTF_FLAG_MIN, HTF_FLAG_MAX = 10, 25    # chosen: flag of 2 to 5 weeks
HTF_MAX_PULLBACK = 25             # guide: pullback under 25% from the peak
PP_RISE_PCT = 50                  # chosen: an "explosive move" = +50% ...
PP_RALLY_MIN, PP_RALLY_MAX = 10, 40    # chosen: ... in 2 to 8 weeks
PP_FLAG_MIN, PP_FLAG_MAX = 5, 20       # chosen: tight pause of 1 to 4 weeks
PP_MAX_PULLBACK = 12              # guide: "often under 10-15%" (12% chosen)
PP_NEAR_HIGH_PCT = 10             # chosen: a market leader stays within 10% of its 250-candle high
ASC_MIN_PULLBACKS = 3             # chosen: a staircase needs 3 up-and-down steps
ASC_PULLBACK_MIN, ASC_PULLBACK_MAX = 5, 20  # chosen: "shallow" = each pullback 5-20% deep
ASC_LOW_STEP_PCT = 1              # chosen: each low must be at least 1% above the one before
ASC_SWING_PCT = 5                 # chosen: a swing is a move of at least 5%
ASC_MIN_BARS, ASC_MAX_BARS = 30, 80    # chosen: 6 to 16 weeks
DARVAS_CONFIRM_BARS = 3           # Darvas: a top / bottom stands once 3 candles fail to beat it
DARVAS_MIN_BARS, DARVAS_MAX_BARS = 5, 40   # guide: "several days or weeks"
DARVAS_MAX_HEIGHT = 15            # chosen: a box is at most 15% tall
DARVAS_NEAR_HIGH_PCT = 5          # chosen: the box top is within 5% of the 250-candle high (new-high stock)
DARVAS_HIGH_WINDOW = 250
LEDGE_MIN_BARS, LEDGE_MAX_BARS = 5, 15  # guide: one to three weeks
LEDGE_MAX_DEPTH = 10              # guide: typically under 10%
LEDGE_NEAR_HIGH_PCT = 5           # chosen: the ledge sits within 5% of the larger base's high
LEDGE_PRIOR_PULLBACK_PCT = 10     # chosen: the larger base had a pullback (peak to trough) of at least 10% first
LEDGE_MAX_DRIFT_PCT = 5           # chosen: a ledge is level: the close at the end is within 5% of the close at the start
LEDGE_WINDOW = 80
STAGE_MA_BARS = 150               # Weinstein 30-week average = 150 daily candles (daily candles avoid a half-finished week repainting)
STAGE_SLOPE_BARS = 20             # chosen: slope of the average over 20 candles ...
STAGE_SLOPE_PCT = 0.5             # chosen: ... within +-0.5% counts as flat
STAGE_ENTRY_BARS = 10             # chosen: "just entered Stage 2" = crossed above the average in the last 10 candles on 1.4x volume
BASE_COUNT_BARS = 25              # chosen: a base needs at least 5 weeks of consolidation before its breakout counts
BASE_COUNT_MAX_DEPTH = 33         # chosen: and is at most 33% deep (cups are the deepest named base)
CLIMAX_RISE_PCT = 100             # guide: "very sharp, climactic run-up" = +100% in the 60 candles before the base
CLIMAX_WINDOW = 60
BASE_1H_ON = True                 # False = base patterns on 1D only (the 1H view then shows a short message)
# ---- the 12 further bases (bases_ext.py). All counted in candles of the timeframe being scanned (1D or 1H). ----
TRI_MIN_BARS, TRI_MAX_BARS = 20, 80    # chosen: triangle length
TRI_SWING_PCT = 3                 # chosen: a swing is a move of at least 3%
TRI_FLAT_PCT = 2                  # chosen: a "flat" triangle line moves at most 2% over the pattern
TRI_SLOPE_PCT = 3                 # chosen: a sloping line moves at least 3% over the pattern
TRI_TOUCH_TOL = 1.5               # chosen: each swing lies within 1.5% of its line
TRI_SHRINK = 0.5                  # guide: lines converge; chosen: the gap at the end is at most 50% of the gap at the start
FLAG_POLE_MIN_PCT, FLAG_POLE_MAX_PCT = 15, 50   # chosen: flagpole of 15-50% (bigger poles are the High Tight Flag / Power Play)
FLAG_POLE_MIN_BARS, FLAG_POLE_MAX_BARS = 5, 20  # chosen: sharp pole = 1 to 4 weeks
FLAG_MIN_BARS, FLAG_MAX_BARS = 5, 20            # guide: one to three weeks (chosen 5-20 candles)
FLAG_POLE_MIN_SPEED = 1.0         # chosen: a pole is sharp: it gains at least 1% per candle on average (a slow run-up is a trend, not a pole)
FLAG_MAX_RETRACE = 50             # guide: more than 50% of the pole is a possible reversal, not a flag
FLAG_PARALLEL_PCT = 3             # chosen: flag = both edges slope together (edge gap changes by at most 3%)
FLAG_PENNANT_RATIO = 0.6          # chosen: pennant = the second half of the consolidation is at most 60% as tall as the first half
WEDGE_MIN_BARS, WEDGE_MAX_BARS = 20, 60   # chosen
WEDGE_SLOPE_PCT = 3               # chosen: both lines move at least 3% the same way
WEDGE_SHRINK = 0.7                # chosen: the gap at the end is at most 70% of the gap at the start
RECT_MIN_BARS, RECT_MAX_BARS = 25, 150    # guide: weeks to months
RECT_MIN_HEIGHT, RECT_MAX_HEIGHT = 5, 25  # chosen: box 5-25% tall
RECT_TOUCHES = 2                  # chosen: at least 2 touches of the ceiling and of the floor
RECT_TOUCH_TOL = 1.5              # chosen: a touch is within 1.5% of the level
RECT_CLOSE_TOL = 1                # chosen: no close more than 1% outside the box
RECT_SWING_PCT = 3
DIAMOND_MIN_BARS, DIAMOND_MAX_BARS = 40, 100   # chosen
DIAMOND_WIDEN = 1.3               # chosen: the first half's range widens by at least 30% ...
DIAMOND_NARROW = 0.6              # chosen: ... then the last quarter is at most 60% of the widest quarter (measured as the average candle range)
DIAMOND_DRIFT = 0.35              # chosen: net price change over the pattern is at most 35% of its widest swing (it is not a trend)
ROUND_MIN_BARS, ROUND_MAX_BARS = 60, 250  # guide: months
ROUND_DEPTH_MIN, ROUND_DEPTH_MAX = 10, 50 # chosen
ROUND_R2 = 0.7                    # chosen: a curve fit (parabola) must explain 70% of the closes
ROUND_RIM_RECOVERY = 10           # chosen: price back within 10% of where the saucer began
ROUND_BOTTOM_POS = (0.3, 0.7)     # chosen: the bottom sits in the middle 40% of the saucer
ROUND_U_MEAN_MAX = 0.42           # chosen: U not V - the average close sits in the lower 42% of the saucer (parabola 0.33, V 0.50)
BROAD_MIN_BARS, BROAD_MAX_BARS = 20, 80   # chosen
BROAD_GROW = 1.3                  # chosen: the gap between the lines grows by at least 30%
BROAD_STEP_PCT = 1                # chosen: each swing is at least 1% beyond the one before
PUSH_MIN_BARS, PUSH_MAX_BARS = 20, 80     # chosen
PUSH_SWING_PCT = 3                # chosen
PUSH_STEP_PCT = 0.5               # chosen: each push beats the last by at least 0.5%
PUSH_RECENT = 10                  # chosen: the third push is within the last 10 candles
BUMP_LEAD_BARS = 40               # chosen: the lead-in trendline is fitted on 40 candles
BUMP_HEIGHT_PCT = 20              # chosen: the bump peaks 20% above the lead-in line
BUMP_STEEP = 1.5                  # chosen: the bump is at least 1.5x steeper than the lead-in
BUMP_MIN_BARS, BUMP_MAX_BARS = 10, 30    # chosen: bump length
BUMP_NEAR_PCT = 8                 # chosen: "forming" while price is within 8% above the lead-in line
HOOK_PULLBACK_PCT = 5             # chosen: point 2 (the reaction) is at least 5% below point 1
HOOK_TEST_PCT = 3                 # chosen: point 3 comes within 3% of point 1 (or beyond it)
HOOK_BARS_MAX = 3                 # guide: the hook is a small pullback (1-3 candles)
HOOK_PRIOR_RISE_PCT = 10          # chosen: the move into point 1 is at least 10%
HOOK_LOOKBACK = 40                # chosen: the whole 1-2-3 + hook fits in 40 candles
WYCKOFF_PRIOR_FALL = 25           # chosen: a decline of at least 25% before the range
WYCKOFF_MIN_BARS, WYCKOFF_MAX_BARS = 30, 120   # chosen
WYCKOFF_HEIGHT_MIN, WYCKOFF_HEIGHT_MAX = 10, 40  # chosen
SPRING_UNDERCUT_MIN, SPRING_UNDERCUT_MAX = 0.5, 5.0  # chosen: the Spring undercuts support by 0.5-5% ...
SPRING_RECLAIM_BARS = 3           # guide: ... and quickly reverses (chosen: closes back above within 3 candles)
WYCKOFF_NEAR_PCT = 15             # chosen: "forming" while price is within 15% of the range top (the range is tall)
SD_BASE_MAX_BARS = 5              # chosen: the zone's base is 1-5 candles
SD_BASE_RANGE_ATR = 0.6           # chosen: each base candle is at most 0.6 ATR tall
SD_IMPULSE_ATR = 3                # chosen: the move away is at least 3 ATR ...
SD_IMPULSE_BARS = 3               # chosen: ... within 3 candles
SD_RETURN_MIN, SD_RETURN_MAX = 5, 60     # chosen: price returns to the zone 5-60 candles later
SD_LOOKBACK = 80                  # chosen: zones formed within the last 80 candles
SD_COMPRESS_ATR = 1.0             # guide: a mini-compression: the last 3 candles average at most 1 ATR
FAST_BREAK_ATR = 1.5              # chosen: a "fast break" candle is at least 1.5 ATR tall ...
FAST_BREAK_VOL = 1.4              # ... on at least 1.4x volume
RS_BARS = 126                     # chosen: relative strength = the 6-month (126-candle) return, ranked across all stocks
TURNOVER_BARS = 20                # chosen: liquidity = average daily value traded over 20 candles

# ---- Downloading ------------------------------------------------------------
SCAN_WORKERS = 8
ENRICH_WORKERS = 6
REQUEST_TIMEOUT = 20
MAX_RETRIES = 3
RETRY_BASE = float(os.environ.get("NSE_RETRY_BASE", 2.0))  # seconds; exponential backoff base
PRICE_BATCH_SIZE = 100
CHECKPOINT_EVERY = 400  # save partial scan results every N symbols

# ---- Cap classification ------------------------------------------------------
CAP_METHOD = "rank"  # "rank" (SEBI/AMFI: top100 large, next150 mid, rest small) or "threshold"
LARGE_CAP_CR = 20_000  # only used when CAP_METHOD == "threshold"
MID_CAP_CR = 5_000
RANK_LARGE = 100
RANK_MID = 250
ENRICH_REFRESH_DAYS = 7
ENRICH_RETRY_DAYS = 2

NON_EQUITY_GROUPS = {"INDEX", "ETF", "FUND", "DEBT", "REIT", "INVIT"}

# ---- Support / resistance levels (1H candles only; shown on the stock page) ----
LEVELS_ON = True                    # False = skip the level finder (levels.py)
LEVELS_TF = "1h"                    # the timeframe levels are found on
BOARD_FILE = str(DATA_DIR / "board_{tf}.json")  # dashboard extras per timeframe (signals, candles, ATR) built by build_board.py
