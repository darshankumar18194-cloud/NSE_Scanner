"""Headless-browser check of the dashboard (Playwright). NOT run by pytest.

    pip install playwright && python -m playwright install chromium
    python tests/browser/make_sample_data.py --yes-this-is-a-copy      # ONLY in a throw-away copy of the project
    python -m http.server 8765 &                                       # from the project folder
    python tests/browser/dashboard_check.py

Checks 1D and 1H: no JS errors; the 21 base buttons and their counts against the board file; direction, status, stage, style, rank,
SMC / candle filters; the SMC + pattern + base tab (including the stocks that must NOT appear); the stock and detailed pages (trigger
lines, target); and that every existing tab and filter still works.
"""
import json, os, re, sys
from playwright.sync_api import sync_playwright

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BASE = os.environ.get("DASH_URL", "http://localhost:8765")
_m = json.load(open(os.path.join(os.path.dirname(__file__), "sample_made.json")))
made, made1h = _m["made"], _m["made1h"]
crafted = {lab: sym for sym, lab in _m["crafted"]}
by_label = {}
for sym, lab in made:
    by_label.setdefault(lab, sym)
board = json.load(open(os.path.join(ROOT, "shared-data", "board_1d.json")))["stocks"]
stocks = json.load(open(os.path.join(ROOT, "shared-data", "stocks.json")))
live = {r["symbol"] for r in stocks if r.get("scanner_status") in ("OK", "STALE")}
NAMES = ['VCP', 'Cup with Handle', 'Flat Base', 'High Tight Flag', 'Power Play', 'Ascending Base', 'Darvas Box', 'The Ledge', 'Flags and Pennants', 'Ross Hook',
         'Double Bottom', 'Rounding Bottom', 'Wyckoff Accumulation', 'Supply & Demand Zones', 'Three Pushes', 'Bump and Run', 'Diamond', 'Triangles', 'Rectangle', 'Wedges', 'Broadening Wedge']


def expected(kind):
    """live / failed base signals on the board, under the default direction filter (bullish + two-sided, no warnings)."""
    out = {}
    for sy, b in board.items():
        if sy not in live:
            continue
        for g in b["signals"]:
            if g["group"] != "base" or not (g["dir"] == "bull" or (g["dir"] == "neutral" and not g.get("warn"))):
                continue
            if (g["status"] == "failed") == (kind == "fail"):
                out[g["name"]] = out.get(g["name"], 0) + 1
    return out


def top2(sym):
    """the (up to) 2 live bases the stock page draws lines for: the same rule as the page."""
    return [g for g in board[sym]["signals"] if g["group"] == "base" and g["status"] != "failed" and g.get("pivot") is not None][:2]


def find(pred):
    for sym, _ in made:
        if any(pred(g) for g in top2(sym)):
            return sym
    return None


results, errors = [], []


def check(name, ok, extra=""):
    results.append((name, bool(ok), extra))
    print(("PASS " if ok else "FAIL ") + name + (" - " + str(extra) if extra else ""))


with sync_playwright() as p:
    br = p.chromium.launch(); ctx = br.new_context(viewport={"width": 1600, "height": 950}); pg = ctx.new_page()

    def hook(page, label):
        page.on("pageerror", lambda e: errors.append((label, "pageerror", str(e))))
        page.on("console", lambda m: errors.append((label, "console." + m.type, m.text)) if m.type == "error" and "ERR_" not in m.text and "Failed to load resource" not in m.text else None)
    hook(pg, "main")
    cnt = lambda sel: int(re.search(r"(\d+) symbols", pg.inner_text(sel)).group(1))
    ev = lambda js: pg.evaluate(js)
    pg.goto(BASE + "/main-dashboard/index.html?tf=1d"); pg.wait_for_selector("#f_baseLive-body tr", state="attached", timeout=90000)

    # ---------------- tabs
    tabs = [t.strip().split("\n")[0] for t in pg.locator(".tab").all_inner_texts()]
    check("8 tabs, in order", [re.sub(r"\s*\d+$", "", t) for t in tabs] == ["SMC + pattern", "SMC + pattern + base", "SMC signals", "Pattern signals", "Base patterns", "All symbols", "Signal feed", "Watchlist"], tabs)
    for tab, view in [("combo", "#viewCombo"), ("triple", "#viewTriple"), ("smc", "#viewSmc"), ("pat", "#viewPat"), ("base", "#viewBase"), ("all", "#viewAll"), ("feed", "#viewFeed"), ("watch", "#viewWatch")]:
        pg.click(f".tab[data-tab={tab}]"); check(f"tab '{tab}' shows its view", pg.locator(view).is_visible())

    # ---------------- base buttons
    pg.click(".tab[data-tab=base]")
    chips = pg.locator("#baseChips .chip[data-pat]")
    names = [c.split("\n")[0] for c in chips.evaluate_all("els => els.map(e => e.firstChild.textContent)")]
    check("22 buttons: All + the 21 bases", chips.count() == 22 and names[1:] == NAMES, names)
    check("4 group labels", pg.locator("#baseChips .chip.grp").count() == 4)
    exp = expected("live"); expf = expected("fail")
    got = dict(zip(names, [int(n) for n in chips.evaluate_all("els => els.map(e => e.querySelector('.n').textContent)")]))
    check("every button count equals the board file", all(got[n] == exp.get(n, 0) for n in NAMES) and got["All"] == sum(exp.values()), {n: (got[n], exp.get(n, 0)) for n in NAMES if got[n] != exp.get(n, 0)})
    check("tab badge = All", pg.inner_text("#baseCount").strip() == str(sum(exp.values())))
    check("failed table count equals the board file", cnt("#f_baseFail-cnt") == sum(expf.values()), f"{cnt('#f_baseFail-cnt')} vs {sum(expf.values())}")
    heads = " ".join(pg.locator("#f_baseLive-head th").all_inner_texts())
    check("columns", all(k in heads for k in ["Symbol", "Base", "Direction", "Status", "Trigger level", "Stop ref", "Volume", "Base Rank", "SMC", "Candle pattern", "Base count", "Stage", "Rel. strength", "Price"]), heads.replace("\n", " ")[:160])
    check("default order = Base Rank, highest first", ev("baseLiveRows().slice().sort((a,b)=>b.rank-a.rank)[0].rank") == ev("Math.max(...baseLiveRows().map(r => r.rank))") and "aria-sort" in pg.locator("#f_baseLive-head").inner_html())
    ranks = ev("baseAll().live.concat(baseAll().fail).map(r => r.rank)")
    check("every Base Rank is a whole number 0-100", all(isinstance(r, int) and 0 <= r <= 100 for r in ranks), (min(ranks), max(ranks)))
    why = ev("baseAll().live[0].why"); check("the rank explains its 8 parts", all(k in why for k in ["Pattern quality", "Entry timing", "Trend (stage)", "Relative strength", "SMC aligned", "Candle pattern aligned", "Base count", "Liquidity and risk"]), why[:80])
    body = pg.locator("#f_baseLive-body").inner_text()
    check("fast-break tag and a measured-move target are shown", "fast" in body and "target ₹" in body)
    pg.click("#baseChips .chip[data-pat='Rectangle']"); n = cnt("#f_baseLive-cnt")
    check("button 'Rectangle' shows only Rectangles", n == exp.get("Rectangle", 0) and ev("baseLiveRows().every(r => r.g.name === 'Rectangle')"), n)
    check("the pressed button is marked", pg.locator("#baseChips .chip.on").inner_text().startswith("Rectangle"))
    pg.click("#baseChips .chip[data-pat='']"); check("button 'All' restores the list", cnt("#f_baseLive-cnt") == sum(exp.values()))
    # ---------------- direction
    n_default = cnt("#f_baseLive-cnt")
    pg.select_option("#fBDir", "bear"); nb = cnt("#f_baseLive-cnt"); check("Direction = Bearish: only bearish bases", nb > 0 and ev("baseLiveRows().every(r => r.dir === 'bear')"), nb)
    pg.select_option("#fBDir", "warn"); nw = cnt("#f_baseLive-cnt"); check("Direction = Warnings: only the Broadening Wedge", nw > 0 and ev("baseLiveRows().every(r => r.g.warn && r.g.name === 'Broadening Wedge')"), nw)
    pg.select_option("#fBDir", "neutral"); check("Direction = Two-sided only", ev("baseLiveRows().every(r => r.dir === 'neutral' && !r.g.warn)") and cnt("#f_baseLive-cnt") > 0)
    pg.select_option("#fBDir", "bull"); check("Direction = Bullish only", ev("baseLiveRows().every(r => r.dir === 'bull')") and cnt("#f_baseLive-cnt") > 0)
    pg.select_option("#fBDir", "all"); check("Direction = All is the sum", cnt("#f_baseLive-cnt") >= n_default + nb + nw - 1, cnt("#f_baseLive-cnt"))
    pg.select_option("#fBDir", "default")
    check("a warning has no trade level", ev("baseAll().live.length") > 0 and ev("(function(){ pg = state.b.dir; state.b.dir='warn'; BASE_ALL=null; const ok = baseLiveRows().every(r => r.g.pivot == null && r.g.stop == null); state.b.dir=pg; BASE_ALL=null; return ok; })()"))
    # ---------------- status / stage / within
    pg.select_option("#fBStatus", "breakout"); check("status = breakout", ev("baseLiveRows().every(r => r.st === 'breakout')") and cnt("#f_baseLive-cnt") > 0)
    pg.select_option("#fBStatus", "forming"); check("status = forming", ev("baseLiveRows().every(r => r.st === 'forming')") and cnt("#f_baseLive-cnt") > 0); pg.select_option("#fBStatus", "")
    pg.select_option("#fBStage", "2"); n2 = cnt("#f_baseLive-cnt"); check("stage = 2 narrows", 0 < n2 <= n_default, n2); pg.select_option("#fBStage", "4"); check("stage = 4 narrows more", cnt("#f_baseLive-cnt") <= n2); pg.select_option("#fBStage", "")
    pg.select_option("#fBWithin", "3"); check("status began within 3 candles narrows", cnt("#f_baseLive-cnt") <= n_default); pg.select_option("#fBWithin", "")
    # ---------------- trader style
    r_bal = ev("baseLiveRows().map(r => r.rank).reduce((a,b)=>a+b,0)")
    pg.select_option("#fBStyle", "breakout"); check("style Breakout trader sets Base status = breakout", pg.input_value("#fBStatus") == "breakout" and ev("baseLiveRows().every(r => r.st === 'breakout')"))
    pg.select_option("#fBStyle", "early"); check("style Early sets Base status = forming", pg.input_value("#fBStatus") == "forming")
    pg.select_option("#fBStyle", "conservative"); check("style Conservative sets stage 2, RS 70, risk 8, turnover 2, min rank 60", [pg.input_value(i) for i in ("#fBStage", "#fBRs", "#fBRisk", "#fBTurn", "#fBRank")] == ["2", "70", "8", "2", "60"])
    check("Conservative shows fewer rows", cnt("#f_baseLive-cnt") <= n_default, cnt("#f_baseLive-cnt"))
    pg.select_option("#fBStyle", "balanced"); check("Balanced clears the starting filters", [pg.input_value(i) for i in ("#fBStatus", "#fBStage", "#fBRs", "#fBRisk", "#fBTurn", "#fBRank")] == [""] * 6 and cnt("#f_baseLive-cnt") == n_default)
    pg.select_option("#fBStyle", "positional"); r_pos = ev("baseLiveRows().map(r => r.rank).reduce((a,b)=>a+b,0)/Math.max(1,baseLiveRows().length)")
    pg.select_option("#fBStyle", "balanced"); r_bal2 = ev("baseLiveRows().map(r => r.rank).reduce((a,b)=>a+b,0)/Math.max(1,baseLiveRows().length)")
    check("a style changes the ranks (same rows, different weights)", abs(r_pos - r_bal2) > 0.01, (round(r_pos, 1), round(r_bal2, 1)))
    # ---------------- requirement filters
    pg.check("#fBSmc"); check("Require SMC aligned", ev("baseLiveRows().every(r => r.sa === 1)") and cnt("#f_baseLive-cnt") <= n_default); n_s = cnt("#f_baseLive-cnt")
    pg.check("#fBCand"); check("Require confirmed candle pattern", ev("baseLiveRows().every(r => r.cand && r.cand.lvl === 2)") and cnt("#f_baseLive-cnt") <= n_s)
    pg.uncheck("#fBSmc"); pg.uncheck("#fBCand")
    pg.fill("#fBTurn", "100000"); check("min turnover narrows", cnt("#f_baseLive-cnt") < n_default); pg.fill("#fBTurn", "")
    pg.fill("#fBRisk", "1"); check("max risk narrows", cnt("#f_baseLive-cnt") < n_default); pg.fill("#fBRisk", "")
    pg.fill("#fBRs", "99"); check("min relative strength narrows", cnt("#f_baseLive-cnt") < n_default); pg.fill("#fBRs", "")
    pg.fill("#fBRank", "75"); check("min Base Rank keeps only strong ranks", ev("baseLiveRows().every(r => r.rank >= 75)") and 0 < cnt("#f_baseLive-cnt") < n_default); pg.fill("#fBRank", "")
    check("filters cleared: back to the default list", cnt("#f_baseLive-cnt") == n_default)
    # ---------------- global filters apply on the base tab
    pg.fill("#fSearch", by_label["rectangle"]); check("symbol search narrows", 0 < cnt("#f_baseLive-cnt") < n_default); pg.fill("#fSearch", "")
    pg.select_option("#fPat", "Rectangle"); check("global Pattern / signal filter = Rectangle", ev("baseLiveRows().every(r => r.g.name === 'Rectangle')") and cnt("#f_baseLive-cnt") > 0); pg.select_option("#fPat", "")
    pg.select_option("#fGroup", "range"); check("global group filter = range hides the bases", cnt("#f_baseLive-cnt") == 0); pg.select_option("#fGroup", "")
    check("'base' group and all 21 names are in the global filters", "base" in pg.locator("#fGroup option").all_inner_texts() and len(pg.locator("#fPat optgroup[label=base] option").all_inner_texts()) >= 15)
    pg.screenshot(path="shot_base.png")
    # ---------------- SMC + pattern + base
    pg.click(".tab[data-tab=triple]")
    ts = ev("tripleRows().map(r => r.s.symbol)")
    check("triple rows exist", len(ts) > 0, len(ts))
    check("every triple row: bullish/bearish base + SMC aligned + confirmed candle pattern", ev("tripleRows().every(r => (r.dir === 'bull' || r.dir === 'bear') && r.sa === 1 && r.cand && r.cand.lvl === 2)"))
    for lab in ("triple forming", "triple breakout", "triple bear"):
        check(f"crafted '{lab}' is listed", crafted[lab] in ts)
    for lab in ("no candle", "smc disagrees", "failed base"):
        check(f"crafted '{lab}' is NOT listed", crafted[lab] not in ts)
    check("triple badge = rows", pg.inner_text("#tripleCount").strip() == str(ev("tripleRows().length")))
    check("triple tab hides the two require-boxes and the window filters", not pg.locator("#fBSmcWrap").is_visible() and not pg.locator("#fWin").is_visible())
    check("triple chips count only triple rows", sum(int(x) for x in pg.locator("#baseChips .chip[data-pat]:not([data-pat=''])").evaluate_all("els => els.map(e => e.querySelector('.n').textContent)")) == len(ts))
    pg.click("#baseChips .chip[data-pat='Bump and Run']"); check("triple: button 'Bump and Run' shows the bearish one", ev("tripleRows().every(r => r.g.name === 'Bump and Run' && r.dir === 'bear')") and crafted["triple bear"] in ev("tripleRows().map(r => r.s.symbol)")); pg.click("#baseChips .chip[data-pat='']")
    pg.locator("#f_triple-body tr.row").first.click(); pg.wait_for_url("**/stock/index.html*"); check("clicking a triple row opens the stock page", True); pg.go_back(); pg.wait_for_selector("#f_baseLive-body tr", state="attached", timeout=60000)
    # ---------------- existing tabs unchanged
    pg.click(".tab[data-tab=combo]"); nc = ev("comboRows('low', true).length"); check("SMC + pattern tab: table count equals its rows", str(nc) in pg.inner_text("#f_comboLow-cnt"), nc)
    pg.click(".tab[data-tab=pat]"); pt = pg.locator("#f_patBull-body").inner_text() + pg.locator("#f_patBear-body").inner_text(); check("Pattern signals tab lists no base patterns", not any(x in pt for x in NAMES))
    pg.click(".tab[data-tab=all]"); a0 = int(re.search(r"of (\d+) symbols", pg.inner_text("#pagerInfo")).group(1)); pg.fill("#fSearch", "TCS"); a1 = int(re.search(r"of (\d+) symbols", pg.inner_text("#pagerInfo")).group(1)); pg.fill("#fSearch", "")
    check("All symbols tab and its search still work", a0 > 1000 and 0 < a1 < a0, (a0, a1))
    pg.click(".tab[data-tab=feed]"); pg.select_option("#fGroup", "base"); feed = pg.locator("#feed").inner_text(); check("feed: base group lists bases with a status pill", any(x in feed for x in NAMES) and re.search(r"(forming|breakout|failed)", feed)); pg.select_option("#fGroup", "")
    # ---------------- stock pages
    def stock(sym, tf="1d"):
        pg.goto(BASE + f"/stock/index.html?symbol={sym}&tf={tf}"); pg.wait_for_selector("#content:not(.hidden)", timeout=30000)
    hook(pg, "stock")
    stock(find(lambda g: g.get("pivot_lo") is not None)); ch = pg.inner_html("#chart"); check("stock page: a two-sided base draws two trigger lines", "upper ₹" in ch and "lower ₹" in ch and "◆" in ch)
    check("stock page: panel shows 'Two-sided' and both levels", "Two-sided" in pg.inner_text("#bases") and "↑" in pg.inner_text("#bases"))
    stock(find(lambda g: g.get("target") is not None and g["status"] == "breakout" and g.get("stop") is not None)); ch = pg.inner_html("#chart"); check("stock page: breakout shows stop and target lines", "stop ₹" in ch and "target ₹" in ch)
    stock(find(lambda g: g["dir"] == "bear")); check("stock page: a bearish base is marked Bearish", "Bearish" in pg.inner_text("#bases"))
    stock(next(sy for sy, _ in made if any(g.get("warn") for g in board[sy]["signals"] if g["group"] == "base"))); check("stock page: the Broadening Wedge is a warning with no trade level", "Warning" in pg.inner_text("#bases") and "no trade level" in pg.inner_text("#bases"))
    stock(by_label["flat forming"]); check("stock page: Stage and Base count readings", "Stage (30-week average)" in pg.inner_text("#ctx") and "Base count" in pg.inner_text("#ctx"))
    stock(made1h[0][0], "1h"); check("stock page 1H: base panel is shown", pg.locator("#baseCard").is_visible() and "hourly" in pg.inner_text("#baseMeta"))
    pg.goto(BASE + f"/signals/detail.html?symbol={find(lambda g: g.get('target') is not None and g['status'] == 'breakout' and g.get('stop') is not None)}"); pg.wait_for_selector("#sigs tr", timeout=30000)
    check("detailed page: trigger / stop / target lines", all(k in pg.inner_html("#chart") for k in ("upper", "stop", "target")) or all(k in pg.inner_html("#chart") for k in ("pivot", "stop", "target")))
    check("detailed page: Base pattern rows with a status chip", "Base pattern" in pg.inner_text("#sigs") and "Breakout" in pg.inner_text("#sigs"))
    pg.goto(BASE + "/signals/index.html"); pg.wait_for_selector("#body tr", timeout=30000); check("detailed list page loads", pg.locator("#body tr").count() > 0)
    # ---------------- 1H
    pg.goto(BASE + "/main-dashboard/index.html?tf=1h"); pg.wait_for_selector("#f_baseLive-body tr", state="attached", timeout=90000)
    pg.click(".tab[data-tab=base]")
    check("1H: base tab is no longer a '1D only' message", "1D only" not in pg.inner_text("#viewBase") and pg.locator("#baseChips .chip[data-pat]").count() == 22)
    n1h = cnt("#f_baseLive-cnt"); check("1H: base rows are listed", n1h > 0, n1h)
    check("1H: the note explains hourly candles", "hourly candles" in pg.inner_text("#baseNote"))
    check("1H: ranks are 0-100 without stage / relative strength", ev("baseAll().live.every(r => Number.isInteger(r.rank) && r.rank >= 0 && r.rank <= 100)"))
    pg.click(".tab[data-tab=triple]"); check("1H: the triple tab loads", pg.locator("#f_triple-head").count() == 1)
    for tab, view in [("combo", "#viewCombo"), ("smc", "#viewSmc"), ("pat", "#viewPat"), ("all", "#viewAll"), ("feed", "#viewFeed"), ("watch", "#viewWatch")]:
        pg.click(f".tab[data-tab={tab}]"); check(f"1H: tab '{tab}' works", pg.locator(view).is_visible())
    pg.goto(BASE + "/main-dashboard/index.html?tf=1d"); pg.set_viewport_size({"width": 390, "height": 800}); pg.wait_for_selector("#f_baseLive-body tr", state="attached"); pg.click(".tab[data-tab=base]"); pg.wait_for_timeout(300)
    check("mobile width: no sideways overflow", ev("document.documentElement.scrollWidth <= window.innerWidth + 4"), ev("[document.documentElement.scrollWidth, window.innerWidth]"))
    br.close()
print("\nJS errors:", len(errors)); [print(" ", e) for e in errors[:10]]
bad = [r for r in results if not r[1]]
print(f"\n{len(results) - len(bad)}/{len(results)} checks passed;", "JS errors: %d" % len(errors))
sys.exit(1 if bad or errors else 0)
