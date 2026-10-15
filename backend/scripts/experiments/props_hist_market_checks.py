"""Line shopping (one book vs the other six), PrizePicks standard lines vs the books, and the anytime-TD de-vig, on the cached 2025 historical props (scripts/backtest_props.py fetch). Free; results in BETTING_GUIDE section 9.

    cd backend && python scripts/experiments/props_hist_market_checks.py
"""
import sys, os, json
from collections import defaultdict
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..')); sys.path.insert(0, os.path.join(HERE, '..', '..'))
import backtest_props as b
from app.services import betting_service as bs, betting_model as bm
from app.services.weekly_projections import normalize_name

games = b.load_games(2025); week_of = {r["game_id"]: int(r["week"]) for r in games}
total_of = {r["game_id"]: float(r["total_line"]) for r in games}
actual = {w: b._index(b._get("stats", 2025, w)) for w in range(1, 19)}
shop = defaultdict(list)   # (scope, bucket) -> [(gid, week, pnl)]
pp = []                    # (gid, week, market, books_p_side, won)
td = []                    # (gid, week, raw implied, game_scale, hit)
EVB = ((-9, 0), (0, .02), (.02, .04), (.04, .06), (.06, .10), (.10, 9))
def bucket(ev): return next(f"{lo:+.0%}..{hi:+.0%}" if hi < 9 else f"{lo:+.0%}+" for lo, hi in EVB if lo <= ev < hi)

for n in sorted(os.listdir(b.HIST)):
    if not n.startswith("props_"): continue
    d = json.load(open(os.path.join(b.HIST, n))); ev = d["data"]; gid = d["game_id"]; w = week_of[gid]
    teams = (bs._team(ev["home_team"]), bs._team(ev["away_team"]))
    groups = bs._group_offers(ev)
    implied = [p for (_, m), o in groups.items() if m == "player_anytime_td" for p in [bs._td_implied(bs._td_yes_prices(o["books"]))] if p]
    scale = bm.td_rate_scale(implied, total_of.get(gid))
    for (pl, m), o in groups.items():
        st = next((actual[w].get((normalize_name(pl), t)) for t in teams if actual[w].get((normalize_name(pl), t))), None)
        if not st or not st.get("gp"): continue
        val = bs._projected_mean(st, m) or 0.0
        books = o["books"]
        if m == "player_anytime_td":
            p = bs._td_implied(bs._td_yes_prices(books))
            if p: td.append((gid, w, p, scale, val >= 1))
            continue
        # 1. Line shopping: each book's price vs the other books' de-vigged median at the same point.
        for bk, pts in books.items():
            for point, sides in pts.items():
                if point is None or not {"Over", "Under"} <= set(sides): continue
                others = [q[point] for k, q in books.items() if k != bk and point in q and {"Over", "Under"} <= set(q[point])]
                if len(others) < 3: continue
                fair_o = bm.median(bm.devig_pair(s["Over"], s["Under"])[0] for s in others)
                for side in ("Over", "Under"):
                    pw = fair_o if side == "Over" else 1 - fair_o
                    dec = bm.american_to_decimal(sides[side]); e = pw * dec - 1
                    if val == point: pnl = 0.0
                    else: pnl = dec - 1 if (val > point) == (side == "Over") else -1.0
                    for scope in ("any", "hardrockbet"):
                        if scope == "any" or bk == scope:
                            shop[(scope, bucket(e))].append((gid, w, pnl, f"{gid}|{pl}|{m}|{side}"))
        # 2. PrizePicks line vs the books.
        ppl = o.get("prizepicks")
        fair = bs._fair_over(books)
        if ppl is None or not fair or val == ppl: continue
        near = min(fair, key=lambda pt: abs(pt - ppl))
        p_over = fair[near] if near == ppl else bs._books_chance(m, pl, near, fair[near], ppl)
        side_over = p_over >= 0.5
        pp.append((gid, w, m, max(p_over, 1 - p_over), (val > ppl) == side_over, ppl - bs.market_center(m, o)))

def ci(rows, f):
    byg = defaultdict(list)
    for r in rows: byg[r[0]].append(f(r))
    return b._boot_ci(byg, np.mean, n=1000)

print("1. Line shopping: one book's price vs the other books' fair chance (no model). Flat 1u.")
print("   'any' counts every book's offer; best-of-7 only = one bet per prop side at the best EV.")
for scope in ("any", "hardrockbet"):
    for lo, hi in EVB:
        k = (scope, f"{lo:+.0%}..{hi:+.0%}" if hi < 9 else f"{lo:+.0%}+")
        rows = shop.get(k, [])
        if scope == "any":  # keep one offer per prop side: the best-EV book in this bucket
            seen = {}; [seen.setdefault(r[3], r) for r in rows]; rows = list(seen.values())
        if len(rows) < 30: continue
        a = [r[2] for r in rows if r[1] <= 9]; c = [r[2] for r in rows if r[1] > 9]
        lo_, hi_ = ci(rows, lambda r: r[2])
        print(f"   {scope:11} EV {k[1]:10} n={len(rows):6d} ROI wk1-9 {np.mean(a):+.1%} | wk10-18 {np.mean(c):+.1%} | all {np.mean([r[2] for r in rows]):+.1%} [{lo_:+.1%}, {hi_:+.1%}]")

print("\n2. PrizePicks standard line, the side the books favor at PP's number. Break-even per pick: 2-pick Power 57.7%, 6-pick Flex ~54.2%.")
for lo, hi in ((.5, .54), (.54, .577), (.577, .62), (.62, .7), (.7, 1.01)):
    rows = [r for r in pp if lo <= r[3] < hi]
    if len(rows) < 20: continue
    a = [r[4] for r in rows if r[1] <= 9]; c = [r[4] for r in rows if r[1] > 9]
    l, h = ci(rows, lambda r: r[4])
    print(f"   books {lo:.1%}-{min(hi,1):.1%}: n={len(rows):5d} said {np.mean([r[3] for r in rows]):.1%} hit wk1-9 {np.mean(a):.1%} | wk10-18 {np.mean(c):.1%} | all {np.mean([r[4] for r in rows]):.1%} [{l:.1%}, {h:.1%}]")
off = [r for r in pp if abs(r[5] or 0) >= 1]
print(f"   PP line 1+ unit off the books' center: n={len(off)}; same-line: n={len(pp) - len(off)}")
for m in ("player_pass_yds", "player_rush_yds", "player_reception_yds", "player_receptions"):
    rows = [r for r in pp if r[2] == m and r[3] >= .577]
    if rows: print(f"   {m.replace('player_',''):14} books >= 57.7%: n={len(rows):4d} said {np.mean([r[3] for r in rows]):.1%} hit {np.mean([r[4] for r in rows]):.1%}")

print("\n3. Anytime TD calibration. Current: td_fair_prob(raw, game scale). Fit on wk1-9: p = c * raw^a.")
tr = [r for r in td if r[1] <= 9]; te = [r for r in td if r[1] > 9]
def cur(r): return bm.td_fair_prob(r[2], r[3] if r[3] is not None else 0.7)
best = None
for a in np.arange(0.8, 1.8, 0.02):
    for c in np.arange(0.5, 1.3, 0.01):
        br = np.mean([(min(.99, c * r[2] ** a) - r[4]) ** 2 for r in tr])
        if best is None or br < best[0]: best = (br, a, c)
_, a, c = best
def fit(r): return min(.99, c * r[2] ** a)
for name, f in (("raw implied", lambda r: r[2]), ("current scale", cur), (f"fit {c:.2f}*p^{a:.2f}", fit)):
    print(f"   {name:22} Brier wk10-18 {np.mean([(f(r) - r[4]) ** 2 for r in te]):.5f}")
byg = defaultdict(list)
for r in te: byg[r[0]].append((fit(r) - r[4]) ** 2 - (cur(r) - r[4]) ** 2)
print(f"   fit - current: {np.mean([v for vs in byg.values() for v in vs]):+.5f} {b._boot_ci(byg, np.mean, n=1000)}")
for lo, hi in ((0, .15), (.15, .25), (.25, .35), (.35, .5), (.5, 1)):
    s = [r for r in te if lo <= r[2] < hi]
    if s: print(f"   raw {lo:.0%}-{hi:.0%} n={len(s):4d}: hit {np.mean([r[4] for r in s]):.1%}  current {np.mean([cur(r) for r in s]):.1%}  fit {np.mean([fit(r) for r in s]):.1%}")
