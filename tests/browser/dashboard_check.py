"""Headless-browser check of the dashboard (Playwright). NOT run by pytest.

    pip install playwright && python -m playwright install chromium
    python tests/browser/make_sample_data.py --yes-this-is-a-copy      # ONLY in a throw-away copy of the project
    python -m http.server 8765 &                                       # from the project folder
    python tests/browser/dashboard_check.py

Checks 1D and 1H: no JS errors, the Base patterns tab and its filters, base signals in the feed and in the Pattern group /
Pattern-signal filters, the stock page chart (pivot, stop, marker), the detailed signals page, and that every existing tab and
filter still works.
"""
import json, os, re, sys
from playwright.sync_api import sync_playwright
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BASE = os.environ.get("DASH_URL", "http://localhost:8765")
_m=json.load(open(os.path.join(os.path.dirname(__file__), "sample_made.json")))
made=_m["made"]; crafted=dict((lab,sym) for sym,lab in _m["crafted"])
sym_brk=[s for s,l in made if l=="cup BREAKOUT" and not s.startswith("^")][0]
sym_flat=[s for s,l in made if l=="flat forming" and not s.startswith("^")][0]
board=json.load(open(os.path.join(ROOT, "shared-data", "board_1d.json")))["stocks"]
stocks=json.load(open(os.path.join(ROOT, "shared-data", "stocks.json")))
live={r["symbol"] for r in stocks if r.get("scanner_status") in("OK","STALE")}
exp_live=sum(1 for sy,b in board.items() if sy in live for g in b["signals"] if g["group"]=="base" and g.get("status")!="failed")
exp_fail=sum(1 for sy,b in board.items() if sy in live for g in b["signals"] if g["group"]=="base" and g.get("status")=="failed")
BASE_NAMES=['VCP','Cup with Handle','Flat Base','Double Bottom','High Tight Flag','Power Play','Ascending Base','Darvas Box','The Ledge']
results=[]; errors=[]
def check(name, ok, extra=""):
    results.append((name, bool(ok), extra)); print(("PASS " if ok else "FAIL ")+name+(" - "+str(extra) if extra else ""))
with sync_playwright() as p:
    br=p.chromium.launch(); ctx=br.new_context(viewport={"width":1500,"height":950}); pg=ctx.new_page()
    def hook(page,label):
        page.on("pageerror", lambda e: errors.append((label,"pageerror",str(e))))
        page.on("console", lambda m: errors.append((label,"console."+m.type,m.text)) if m.type=="error" and "ERR_" not in m.text and "Failed to load resource" not in m.text else None)
    hook(pg,"main1d")
    def text(sel): return pg.inner_text(sel).strip()
    def rows(sel): return pg.locator(sel).count()
    # ---------------- 1D main dashboard
    pg.goto(BASE+"/main-dashboard/index.html?tf=1d"); pg.wait_for_selector("#f_patBull-body tr.row", state="attached", timeout=60000)
    check("1D dashboard loads, Base patterns tab exists", rows(".tab[data-tab=base]")==1)
    # existing tabs still render
    for tab,view in [("combo","#viewCombo"),("triple","#viewTriple"),("smc","#viewSmc"),("pat","#viewPat"),("all","#viewAll"),("feed","#viewFeed"),("watch","#viewWatch"),("base","#viewBase")]:
        pg.click(f".tab[data-tab={tab}]"); vis=pg.locator(view).is_visible()
        check(f"tab '{tab}' shows its view", vis)
    pg.click(".tab[data-tab=all]"); base_all=int(re.search(r"of (\d+) symbols",text("#pagerInfo")).group(1))
    # base filters only on the base tab
    pg.click(".tab[data-tab=base]"); check("base-only filters visible on Base tab", pg.locator("#baseFilters").is_visible())
    pg.click(".tab[data-tab=pat]"); check("base-only filters hidden on other tabs", not pg.locator("#baseFilters").is_visible())
    # base tab content
    pg.click(".tab[data-tab=base]")
    live_cnt=int(re.search(r"(\d+) symbols",text("#f_baseLive-cnt")).group(1)); fail_cnt=int(re.search(r"(\d+) symbols",text("#f_baseFail-cnt")).group(1))
    check("live base table row count equals board file", live_cnt==exp_live, f"{live_cnt} vs {exp_live}")
    check("failed base table row count equals board file", fail_cnt==exp_fail, f"{fail_cnt} vs {exp_fail}")
    check("tab badge shows the live count", text("#baseCount")==str(exp_live))
    heads=[h.strip() for h in pg.locator("#f_baseLive-head th").all_inner_texts()]
    check("columns present", all(any(k in h for h in heads) for k in ["Symbol","Base pattern","Status","Pivot","Stop","Volume","Confluence","Base count","Stage","Price"]), heads)
    first=pg.locator("#f_baseLive-body tr.row").first.inner_text()
    check("default order: breakouts first", "Breakout" in pg.locator("#f_baseLive-body tr.row").first.inner_text(), first.replace("\n"," | ")[:110])
    names_shown={n for n in BASE_NAMES if pg.locator("#f_baseLive-body").inner_text().count(n)}
    check("base names shown in table (page 1)", len(names_shown)>=3, sorted(names_shown))
    # base filters
    pg.select_option("#fBStatus","breakout"); n_b=rows("#f_baseLive-body tr.row"); pills=pg.locator("#f_baseLive-body .pill").all_inner_texts()
    check("status=breakout filter: only Breakout rows", n_b>0 and all(("Breakout" in t) or t.startswith("Stage") or "just" in t or "S" in t for t in pills) and "Forming" not in " ".join(pills), f"{n_b} rows")
    pg.select_option("#fBStatus",""); 
    pg.click("#msBase .ms-btn"); pg.click("#msBase input[value='VCP']"); pg.keyboard.press("Escape"); pg.click("h1")
    body=pg.locator("#f_baseLive-body").inner_text()
    check("base pattern multi-select VCP: only VCP rows", rows("#f_baseLive-body tr.row")>0 and not any(n in body for n in BASE_NAMES if n!="VCP"), f"{rows('#f_baseLive-body tr.row')} rows")
    pg.click("#fReset"); check("Reset restores live count", int(re.search(r"(\d+) symbols",text("#f_baseLive-cnt")).group(1))==exp_live)
    pg.select_option("#fBStage","2"); n2=int(re.search(r"(\d+) symbols",text("#f_baseLive-cnt")).group(1)); check("stage filter narrows (or equals) the list", n2<=exp_live, n2)
    pg.select_option("#fBStage",""); pg.select_option("#fBWithin","3"); n3=int(re.search(r"(\d+) symbols",text("#f_baseLive-cnt")).group(1)); check("'status began within 3 candles' narrows the list", n3<=exp_live, n3)
    pg.click("#fReset")
    # sorting
    pg.click("#f_baseLive-head button[data-tsort=score]"); s1=pg.locator("#f_baseLive-body tr.row").first.inner_text()
    check("sorting by Confluence works", "aria-sort" in pg.locator("#f_baseLive-head").inner_html())
    # global filters apply to the base tab
    pg.fill("#fSearch", sym_flat); n_s=int(re.search(r"(\d+) symbols",text("#f_baseLive-cnt")).group(1)); check("symbol search narrows the base table", 0<n_s<exp_live, n_s); pg.fill("#fSearch","")
    pg.select_option("#fPat","VCP"); body=pg.locator("#f_baseLive-body").inner_text(); check("global 'Pattern / signal' = VCP applies to base tab", all(n not in body for n in BASE_NAMES if n!="VCP")); pg.click("#fReset")
    # group + pattern filter contents
    groups=pg.locator("#fGroup option").all_inner_texts(); check("'base' is in Pattern group filter", "base" in groups, groups)
    opts=pg.locator("#fPat optgroup[label=base] option").all_inner_texts(); check("base signals listed in Pattern/signal filter", len(opts)>=7, opts)
    # row click opens stock page
    # ---------------- SMC + pattern + base tab
    pg.click(".tab[data-tab=triple]"); check("triple tab shows its view and the base filters", pg.locator("#viewTriple").is_visible() and pg.locator("#baseFilters").is_visible())
    check("triple tab keeps the pattern window / confirmation filters visible", pg.locator("#fWin").is_visible() and pg.locator("#fConfirm").is_visible())
    tsyms=lambda: pg.evaluate("tripleRows().map(r => r.s.symbol)")
    ts=tsyms(); csyms=set(pg.evaluate("comboRows('low', true).map(r => r.s.symbol)"))
    check("triple rows are a subset of the SMC + pattern rows", set(ts) <= csyms and len(ts) > 0, len(ts))
    check("every triple row has a live (forming or breakout) base", pg.evaluate("tripleRows().every(r => ['forming','breakout'].includes(r.bst))"))
    check("crafted: SMC + pattern + forming base is listed", crafted["forming"] in ts)
    check("crafted: SMC + pattern + breakout base is listed", crafted["breakout"] in ts)
    check("crafted: SMC + pattern with NO base is not listed", crafted["no base"] not in ts and crafted["no base"] in csyms)
    check("crafted: SMC + pattern with a FAILED base is not listed", crafted["failed base"] not in ts and crafted["failed base"] in csyms)
    check("triple badge and table count match", pg.inner_text("#tripleCount").strip()==str(len(ts)) and (str(len(ts)) in pg.inner_text("#f_triple-cnt")), pg.inner_text("#f_triple-cnt"))
    heads=" ".join(pg.locator("#f_triple-head th").all_inner_texts())
    check("triple columns: SMC + pattern half and base half", all(k in heads for k in ["Low signal","Low level","Pattern","SMC rank","Pattern score","Base pattern","Base status","Pivot","Base stop","Base score","Base count","Stage"]), heads.replace("\n"," ")[:150])
    pg.select_option("#fBStatus","breakout"); t1=tsyms(); check("base status = breakout keeps only breakout rows", crafted["breakout"] in t1 and crafted["forming"] not in t1, len(t1)); pg.select_option("#fBStatus","")
    pg.click("#msBase .ms-btn"); pg.click("#msBase input[value=\'VCP\']"); pg.click("h1"); t2=tsyms()
    check("base pattern = VCP only: the Flat Base rows drop out", crafted["forming"] not in t2 and crafted["breakout"] not in t2, len(t2)); pg.click("#fReset")
    pg.select_option("#fPat","Hammer"); t3=tsyms(); check("pattern filter = a candle pattern narrows the candle half only (base untouched)", crafted["forming"] in t3 and crafted["breakout"] in t3, len(t3)); pg.select_option("#fPat","")
    pg.select_option("#fPat","Flat Base"); t4=tsyms(); check("pattern filter = a base pattern narrows the base half only (candle half untouched)", crafted["forming"] in t4 and set(t4) <= set(ts), len(t4)); pg.select_option("#fPat","")
    pg.select_option("#fStrength","WEAK"); t5=tsyms(); check("SMC strength = Weak removes the Strong Low rows", crafted["forming"] not in t5 and crafted["breakout"] not in t5, len(t5)); pg.click("#fReset")
    pg.select_option("#fBStage","4"); t6=tsyms(); check("stage filter = Stage 4 removes the Stage 2 crafted rows", crafted["forming"] not in t6, len(t6)); pg.click("#fReset")
    pg.fill("#fSearch", crafted["breakout"]); t7=tsyms(); check("symbol search narrows the triple table", t7==[crafted["breakout"]], t7); pg.fill("#fSearch","")
    check("reset restores the triple rows", tsyms()==ts)
    pg.locator("#f_triple-body tr.row").first.click(); pg.wait_for_url("**/stock/index.html*"); check("clicking a triple row opens the stock page", True); pg.go_back(); pg.wait_for_selector("#f_patBull-body tr.row", state="attached", timeout=60000)
    # the existing SMC + pattern tab must behave exactly as before
    pg.click(".tab[data-tab=combo]"); n_combo=pg.evaluate("comboRows('low', true).length"); check("existing SMC + pattern tab: table count equals its rows", str(n_combo) in pg.inner_text("#f_comboLow-cnt"), pg.inner_text("#f_comboLow-cnt"))
    pg.select_option("#fPat","VCP"); check("existing SMC + pattern tab: a base-pattern filter still empties it (unchanged behaviour)", pg.evaluate("comboRows('low', true).length")==0); pg.select_option("#fPat","")
    # pattern tab excludes base
    pg.click(".tab[data-tab=pat]"); pat_text=pg.locator("#f_patBull-body").inner_text()+pg.locator("#f_patBear-body").inner_text()
    check("Pattern signals tab does not list base patterns", not any(n in pat_text for n in BASE_NAMES))
    # existing filters still work (counts change, reset restores)
    pg.click(".tab[data-tab=all]")
    def allcount(): return int(re.search(r"of (\d+) symbols",text("#pagerInfo")).group(1))
    c0=allcount(); check("All symbols count", c0==base_all and c0>1000, c0)
    pg.fill("#fSearch","TCS"); c1=allcount(); check("existing: symbol search", 0<c1<c0, c1); pg.fill("#fSearch","")
    pg.select_option("#fSqueeze","on"); c2=allcount(); check("existing: squeeze filter", c2<c0, c2); pg.select_option("#fSqueeze","")
    pg.select_option("#fSmc","BULLISH"); c3=allcount(); check("existing: SMC trend filter", 0<c3<c0, c3); pg.select_option("#fSmc","")
    pg.select_option("#fGroup","range"); c4=allcount(); check("existing: pattern group filter (range)", 0<c4<c0, c4)
    pg.select_option("#fGroup","base"); c4b=allcount(); check("new: pattern group filter (base) lists the stocks with base signals", 0<c4b<c0, c4b); pg.select_option("#fGroup","")
    pg.select_option("#fPat","VCP"); c5=allcount(); check("pattern filter on a base signal in All symbols", 0<c5<c0, c5); pg.select_option("#fPat","")
    pg.click("#fOnly"); c6=allcount(); check("existing: only symbols with a pattern", c6<c0, c6); pg.click("#fOnly")
    pg.click("#msSector .ms-btn"); pg.locator("#msSector .ms-opt input").nth(1).check(); pg.click("h1"); c7=allcount(); check("existing: sector multi-select", 0<c7<c0, c7); pg.click("#fReset")
    pg.click("#fRegular"); c8=allcount(); check("existing: regular equity only", c8<c0, c8); pg.click("#fReset")
    pg.fill("#fFrom","2026-11-10"); c9=allcount(); pg.fill("#fFrom",""); check("existing: date filter runs", True, c9)
    pg.click("#barRow .bar-btn[data-bar='0']"); c10=allcount(); check("existing: candle-ago button runs", c10<=c0, c10); pg.click("#fReset")
    check("reset restores All symbols count", allcount()==c0)
    # feed
    pg.click(".tab[data-tab=feed]"); feed=pg.locator("#feed").inner_text(); fc=int(text("#feedCount")); check("feed has items", fc>0, fc)
    pg.select_option("#fGroup","base"); feed=pg.locator("#feed").inner_text(); check("feed: base group shows base signals with a status pill", any(n in feed for n in BASE_NAMES) and re.search(r"(forming|breakout|failed)",feed), pg.locator("#feed li").first.inner_text().replace("\n"," | ")[:100]); pg.select_option("#fGroup","")
    pg.screenshot(path="shot_feed.png")
    # screenshots + row click
    pg.click(".tab[data-tab=base]"); pg.wait_for_timeout(200); pg.screenshot(path="shot_base_tab.png", full_page=False)
    pg.fill("#fSearch", sym_brk); pg.locator("#f_baseLive-body tr.row").first.click(); pg.wait_for_url("**/stock/index.html*"); 
    check("clicking a base row opens the stock page", "symbol="+sym_brk.replace('&','%26') in pg.url or sym_brk in pg.url, pg.url[-60:])
    pg.wait_for_selector("#content:not(.hidden)", timeout=30000)
    # ---------------- stock page 1D
    hook(pg,"stock1d")
    chart=pg.inner_html("#chart"); check("stock page chart: pivot line + label", "pivot ₹" in chart and "stop ₹" in chart)
    check("stock page chart: base marker (diamond)", "◆" in chart)
    check("stock page: Base patterns panel has rows", rows("#bases tr")>=1 and "No base pattern" not in pg.inner_text("#bases"), pg.inner_text("#bases").replace("\n"," | ")[:120])
    check("stock page: Stage + Base count readings", "Stage (30-week average)" in pg.inner_text("#ctx") and "Base count" in pg.inner_text("#ctx"))
    check("stock page: chart title follows timeframe", "daily" in pg.inner_text("#chartTitle"), pg.inner_text("#chartTitle"))
    check("stock page: signals table lists the base signal", "base" in pg.inner_text("#sigs"))
    pg.screenshot(path="shot_stock.png", full_page=True)
    # ---------------- stock page 1H (no base)
    pg.goto(BASE+f"/stock/index.html?symbol={sym_brk}&tf=1h"); pg.wait_for_timeout(1500)
    check("stock page 1H: base panel hidden, page loads", not pg.locator("#baseCard").is_visible() and pg.locator("#content").is_visible())
    # ---------------- detailed signals pages
    pg.goto(BASE+f"/signals/detail.html?symbol={sym_brk}"); pg.wait_for_selector("#sigs tr", timeout=30000)
    check("detailed page: base chart lines", "pivot" in pg.inner_html("#chart"))
    check("detailed page: 'Base pattern' group + Breakout chip", "Base pattern" in pg.inner_text("#sigs") and "Breakout" in pg.inner_text("#sigs"))
    check("detailed page: Stage + Base count readings", "Stage (30-week average)" in pg.inner_text("#ctx") if pg.locator("#ctx").count() else False)
    pg.goto(BASE+"/signals/index.html"); pg.wait_for_selector("#body tr", timeout=30000); check("detailed list page loads", rows("#body tr")>0)
    # ---------------- 1H main dashboard
    pg.goto(BASE+"/main-dashboard/index.html?tf=1h"); pg.wait_for_selector("#f_patBull-body tr.row", state="attached", timeout=60000)
    pg.click(".tab[data-tab=base]"); msg=pg.inner_text("#fullBase")
    check("1H: Base patterns tab shows the 1D-only message", "1D only" in msg)
    check("1H: base-only filters hidden", not pg.locator("#baseFilters").is_visible())
    pg.click(".tab[data-tab=triple]"); check("1H: SMC + pattern + base shows the 1D-only message", "1D only" in pg.inner_text("#fullTriple") and not pg.locator("#baseFilters").is_visible())
    for tab,view in [("combo","#viewCombo"),("smc","#viewSmc"),("pat","#viewPat"),("all","#viewAll"),("feed","#viewFeed"),("watch","#viewWatch")]:
        pg.click(f".tab[data-tab={tab}]"); check(f"1H: tab '{tab}' works", pg.locator(view).is_visible())
    pg.click(".tab[data-tab=all]"); c1h=int(re.search(r"of (\d+) symbols",text("#pagerInfo")).group(1)); check("1H: All symbols table filled", c1h>1000, c1h)
    check("1H: no base group in the group filter", "base" not in pg.locator("#fGroup option").all_inner_texts())
    pg.goto(BASE+"/main-dashboard/index.html?tf=1d")
    pg.set_viewport_size({"width":390,"height":800}); pg.wait_for_selector("#f_patBull-body tr.row", state="attached"); pg.click(".tab[data-tab=base]"); pg.wait_for_timeout(200)
    check("mobile width: page does not overflow sideways", pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 4"), pg.evaluate("[document.documentElement.scrollWidth, window.innerWidth]"))
    pg.screenshot(path="shot_mobile.png")
    br.close()
print("\nJS errors:", len(errors)); [print(" ",e) for e in errors[:10]]
bad=[r for r in results if not r[1]]
print(f"\n{len(results)-len(bad)}/{len(results)} checks passed;", "JS errors: %d"%len(errors))
sys.exit(1 if bad or errors else 0)
