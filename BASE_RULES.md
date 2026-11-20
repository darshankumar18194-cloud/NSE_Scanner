# Base rulebook: what makes each base, and each breakout, "true"

Every base has its **own** rules. A Darvas Box is not judged like a VCP, and neither is judged like a Flat Base. This page lists the rules
the scanner applies to each of the 21 bases (+ 1 warning), where each rule comes from, and where to change the number.

* **Numbers live in `config.py`** (shape numbers by name, e.g. `FLAT_MAX_DEPTH`; breakout numbers in `BASE_BREAKOUT_RULES`).
* **Shapes live in `bases.py`** (the first 9) and **`bases_ext.py`** (the other 12). `base_utils.py` only prepares the price / volume arrays.
* "Guide" = your three documents (*All Pre-Breakout Techniques*, *Advanced Rare Techniques*, *Named Base Types Vol. III*).
  "Chosen" = the guide gives no number, so the value is ours and can be changed.
* Closed candles only. Nothing here says how often a shape that passes works in a real market.

## 1. The three questions asked of every base

1. **Is the shape real?** The base's own rules (depth, length, contractions, touches ...). Section 3.
2. **Is the breakout real?** The closing candle must pass *that base's* breakout rules. Section 2.
3. **Did it hold?** A breakout that closes back below its trigger within 5 candles, or below the base's stop, is marked *failed*.

## 2. Breakout rules

A base is **armed** on a candle when its shape stands and the close is within 5% of the trigger (`BASE_NEAR_PIVOT_PCT`).
The **next closed candle** decides:

| Next candle | Result |
|---|---|
| Closes beyond the trigger, passes the base's volume rule **and** close rule | **Breakout** |
| Closes beyond the trigger but volume is short | stays **Forming**, flagged *low volume* |
| Closes beyond the trigger but near the low of its own range (poked out, closed back) | stays **Forming**, flagged *weak close* |
| Closes beyond the trigger by more than 5% without enough volume | base is over (ran away) |
| Closes beyond the stop | **Failed** (Cup with Handle, High Tight Flag, Power Play, Flags only fail when the shape is gone too) |

Volume is the breakout candle's volume as a multiple of the 50-candle average.

| Rule set | Volume needed | Close rule | Used by |
|---|---|---|---|
| Standard (`BASE_BREAKOUT_VOL`) | **1.4x** | none | VCP, Cup with Handle, Double Bottom, High Tight Flag, Ascending Base, The Ledge, Triangles, Flags and Pennants, Wedges, Diamond, Wyckoff Accumulation |
| Easy (`BASE_BREAKOUT_VOL_EASY`) | **1.2x** | none | Flat Base, Power Play, Three Pushes, Bump and Run, Supply & Demand Zones |
| Price only | none | none | Ross Hook |
| **Darvas Box** (own rules) | **1.5x** | close in the **top 30%** of the candle's range | Darvas Box |
| **Rectangle** (own rules) | 1.4x | close in the better **40%** of the candle's range ("decisive") | Rectangle |
| **Rounding Bottom** (own rules) | **1.2x** ("pickup", not a surge) | none | Rounding Bottom |

To give any base its own rules, add a line to `BASE_BREAKOUT_RULES` in `config.py`:
`"Flat Base": {"vol": 1.3, "close_pos": 0.6}`. Nothing else needs to change.

## 3. Shape rules, base by base

### Continuation bases (bullish, price near its highs)

All of these also need the stock to have **risen at least 30% into the base** (20% for Flat Base) and to be within 30% of its
130-candle high, so a base in a falling stock is never called.

| Base | The shape is real when | Trigger / stop | Guide rule it follows |
|---|---|---|---|
| **VCP** | 15-65 candles. At least 2 pullbacks, **each smaller than the one before** (first 10-35%, last at most 10%). Volume of the last contraction is not above the first. | Trigger = high of the last contraction. Stop = its low. | "Each pullback shallower than the last"; "if a later contraction is bigger the pattern is invalid"; "volume shrinks with each contraction"; breakout on **40-50%+ volume**. |
| **Cup with Handle** | Cup 35-130 candles and **12-33% deep**. Right rim within 10% of the left rim. **U-shaped, not V**. Handle 5-25 candles, pulls back at most 12%, **stays in the upper half of the cup**, volume **below** the cup's. | Trigger = handle high (right rim). Stop = handle low. | "Cup 12-33% deep"; "handle drifts down or sideways on declining volume"; "handle in the lower half is weaker". |
| **Flat Base** | 25-65 candles (at least 5 weeks), **under 15% deep**, sideways (end within 8% of the start). Prior rise at least 20%. | Trigger = base high. Stop = base low. | "Shallow sideways, under 15% deep, at least five weeks"; "even modest volume is enough" so 1.2x. |
| **Double Bottom** | W of 35-120 candles. Lows 15-60 candles apart. **Second low undercuts the first by a small amount (0.1-5%)**. Middle of the W at least 8% above the first low. | Trigger = the peak between the two lows. | "Second low undercuts the first slightly; a big undercut or none is lower quality." |
| **High Tight Flag** | **+100% in 20-40 candles** (4-8 weeks), then a flag of 10-25 candles pulling back **under 25%**. | Trigger = flag high. | "Rallies 100%+ in 4-8 weeks, pullback under 25%." |
| **Power Play** | **+50% in 10-40 candles**, then a pause of 5-20 candles pulling back at most 12%. Price within 10% of its 250-candle high. | Trigger = pause high. | "Explosive move, unusually shallow pullback (often under 10-15%)"; volume "still elevated" so 1.2x. |
| **Ascending Base** | At least **3 up-and-down steps**, 30-80 candles. Each pullback 5-20%, **each low at least 1% above the last**, highs not lower. | Trigger = latest minor high. Stop = last low. | "A staircase; each pullback holds above the prior low." |
| **Darvas Box** | Box top = highest high of the last 40 candles, **within 5% of the 250-candle high** (a new-high stock). The top is at least 5 candles old and **3 candles have failed to beat it**; the bottom is confirmed the same way. Box at most 15% tall. | Trigger = box top. Stop = box bottom. | "Price hits a new high, then trades sideways, unable to make a new high or break the low." Breakout: "close above the top on increased volume, a 2x+ spike" and a **clean close**. |
| **The Ledge** | 5-15 candles, **under 10% deep**, level (end within 5% of the start), within 5% of the high of a larger base that had a pullback of at least 10%. Volume **below average and shrinking**. | Trigger = ledge high. Stop = ledge low. | "Holds tight under 10% for one to three weeks on shrinking volume, then breaks on expanding volume." |
| **Flags and Pennants** | Pole of 15-50% in 5-20 candles, at least 1% per candle. Flag/pennant of 5-20 candles that gives back **at most 50% of the pole**. Flag = parallel edges, pennant = converging. | Break in the **direction of the pole** (bull or bear flags). | "Within one to three weeks"; "more than 50% retrace is a possible reversal." |
| **Ross Hook** | A 1-2-3: reaction at least 5% below point 1, point 3 within 3% of point 1 (or beyond), then a **1-3 candle hook**. Prior move at least 10%. All within 40 candles. | Trigger = hook high. | "A small pullback right after point 3 sets up the entry." |

### Reversal / basing bases

| Base | The shape is real when | Trigger / direction | Guide rule it follows |
|---|---|---|---|
| **Rounding Bottom** | 60-250 candles, 10-50% deep. A parabola explains at least 70% of the closes. Bottom in the **middle 40%**. U not V. Price back within 10% of where it started. | Bullish. Trigger = the level where the saucer began. | "Very slow U-shape taking months"; "pickup in volume after a long quiet period". |
| **Wyckoff Accumulation** | A fall of at least 25% first. Range of 30-120 candles, 10-40% tall. A **Spring**: undercuts support by 0.5-5% and **closes back above within 3 candles**. | Bullish. Trigger = range top. | "The Spring: a failed breakdown quickly reclaimed." |
| **Supply & Demand Zones** | A base of 1-5 small candles (each at most 0.6 ATR), then a move away of at least **3 ATR within 3 candles**. Price **returns** 5-60 candles later and compresses (last 3 candles average at most 1 ATR). | Demand zone = bullish, supply zone = bearish. | "Price returns to the zone, consolidates briefly, then moves again." |
| **Three Pushes** | Three pushes, each at least 0.5% beyond the last, 20-80 candles, the third within the last 10 candles. | Pushes up = bearish, down = bullish. | "Three attempts, each weaker; decisive break of the trendline." |
| **Bump and Run** | Lead-in trendline fitted on 40 candles. A bump of 10-30 candles peaking **at least 20% above** that line and **1.5x steeper**. | Bearish. Trigger = a close back through the lead-in line. | "Steep unsustainable bump, then a break of the lead-in trendline." |
| **Diamond** | 40-100 candles. Candle range **widens by 30%+, then narrows** to at most 60% of the widest part. Price is not trending (net move at most 35% of the widest swing). | Two-sided: either boundary. | "Widens then narrows; break of either boundary with a volume increase." |

### Two-sided bases (the direction is decided by the break)

| Base | The shape is real when | Direction | Guide rule it follows |
|---|---|---|---|
| **Triangles** | 20-80 candles. Two straight lines through the swing points (each within 1.5%). Flat line moves at most 2%, sloping line at least 3%. The gap **shrinks to at most 50%**. | Ascending breaks **up**, descending **down**, symmetrical either way. | "Break in the direction of the flat line, on expanding volume"; "symmetrical is the least reliable." |
| **Rectangle** | 25-150 candles, 5-25% tall, **at least 2 touches** of the ceiling and the floor, no close more than 1% outside. | Either way. **Decisive close** needed (see section 2). | "A decisive close outside either boundary, ideally on volume expansion." |
| **Wedges** | 20-60 candles. Both lines slope the **same way** (at least 3%) and the gap shrinks to at most 70%. | **Against the slope**: rising breaks down, falling breaks up. | "Counter-intuitively, wedges break against the direction they slope." |

### Warning (not a trade)

| Base | What it means |
|---|---|
| **Broadening Wedge** | Swings get **wider** (gap grows 30%+, each swing at least 1% beyond the last). Shown as a warning with no trigger and no stop: reduce size or stand aside. |

## 4. Not enforced yet (your call)

These are in the guide but are **not** a pass/fail rule today:

* **Volume dry-up inside the base** (guide: "the volume backbone behind VCP, Cup with Handle and Darvas"). It is enforced in the shape of
  **VCP, Cup with Handle and The Ledge**, but for **Darvas Box and Flat Base** it only raises the Base Rank score.
* **Pocket Pivot** (shown as a candle pattern) and **Base Count** (shown as information): neither changes which bases are called.
* **Stage 2 only.** Stage is shown, not required.

Say which of these you want as hard rules and they become one line each in `config.py`.
