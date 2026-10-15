"""QB + receiver PrizePicks stacks on real 2025 PrizePicks lines (cached by scripts/backtest_props.py fetch): how often both legs hit vs the books' independent chance. Free; results in BETTING_GUIDE section 9.

    cd backend && python scripts/experiments/props_hist_stacks.py
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
rows_by_w = {w: b._get("stats", 2025, w) for w in range(1, 19)}
pos = {}
for w, rows in rows_by_w.items():
    for r in rows:
        p = r.get("player") or {}
        pos[normalize_name(f"{p.get('first_name','')} {p.get('last_name','')}")] = p.get("position")
actual = {w: b._index(rows) for w, rows in rows_by_w.items()}
pairs = []  # (gid, week, kind, p1, p2, both_hit, side)
for n in sorted(os.listdir(b.HIST)):
    if not n.startswith("props_"): continue
    d = json.load(open(os.path.join(b.HIST, n))); ev = d["data"]; gid = d["game_id"]; w = week_of[gid]
    teams = (bs._team(ev["home_team"]), bs._team(ev["away_team"]))
    legs = []
    for (pl, m), o in bs._group_offers(ev).items():
        if m not in ("player_pass_yds", "player_reception_yds") or o.get("prizepicks") is None: continue
        nm = normalize_name(pl)
        t = next((t for t in teams if actual[w].get((nm, t))), None)
        if not t or not actual[w][(nm, t)].get("gp"): continue
        fair = bs._fair_over(o["books"])
        if not fair: continue
        ppl = o["prizepicks"]; near = min(fair, key=lambda pt: abs(pt - ppl))
        p_over = fair[near] if near == ppl else bs._books_chance(m, pl, near, fair[near], ppl)
        val = bs._projected_mean(actual[w][(nm, t)], m) or 0.0
        if val == ppl: continue
        legs.append((pl, m, t, p_over, val > ppl, pos.get(nm)))
    qbs = [l for l in legs if l[1] == "player_pass_yds" and l[5] == "QB"]
    rec = [l for l in legs if l[1] == "player_reception_yds" and l[5] in ("WR", "TE")]
    for q in qbs:
        for r in rec:
            kind = "QB + own WR/TE" if q[2] == r[2] else "QB + opp WR/TE"
            for side in ("More", "Less"):
                p1 = q[3] if side == "More" else 1 - q[3]; p2 = r[3] if side == "More" else 1 - r[3]
                h1 = q[4] if side == "More" else not q[4]; h2 = r[4] if side == "More" else not r[4]
                pairs.append((gid, w, kind, p1, p2, h1 and h2, side, h1, h2))
for kind in ("QB + own WR/TE", "QB + opp WR/TE"):
    for side in ("More", "Less"):
        s = [p for p in pairs if p[2] == kind and p[6] == side]
        if not s: continue
        indep = np.mean([p[3] * p[4] for p in s]); both = np.mean([p[5] for p in s])
        h1 = np.array([p[7] for p in s], float); h2 = np.array([p[8] for p in s], float)
        byg = defaultdict(list)
        for p in s: byg[p[0]].append(float(p[5]) - p[3] * p[4])
        lo, hi = b._boot_ci(byg, np.mean, n=1000)
        a = [p[5] - p[3]*p[4] for p in s if p[1] <= 9]; c = [p[5] - p[3]*p[4] for p in s if p[1] > 9]
        print(f"{kind:15} both {side:4}: n={len(s):4d} books-independent {indep:.1%}, actual both {both:.1%} "
              f"(lift {both - indep:+.1%} [{lo:+.1%}, {hi:+.1%}]; wk1-9 {np.mean(a):+.1%}, wk10-18 {np.mean(c):+.1%}); "
              f"leg corr {np.corrcoef(h1, h2)[0,1]:+.2f}")
# What a 2-pick Power would return (3x): both More on QB + own WR at PP lines
s = [p for p in pairs if p[2] == "QB + own WR/TE"]
for side in ("More", "Less"):
    t = [p for p in s if p[6] == side]
    print(f"2-pick Power (3x) {side}/{side} QB + own WR/TE, every pair: ROI {np.mean([3.0 * p[5] - 1 for p in t]):+.1%} (n={len(t)})")
