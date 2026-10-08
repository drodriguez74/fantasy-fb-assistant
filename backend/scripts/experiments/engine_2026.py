"""How did the engine's predictions hold up in 2026 weeks 1-4?

No prop lines exist for those weeks (lines were first saved in week 5), so
this can't say whether the engine beat the books. It answers the other half:
when the engine said a pick wins X%, did it? For every player-week with a
Sleeper projection (pass/rush/rec yards, receptions), lines are set where
PrizePicks puts them relative to a projection -- goblin (~50-70%), standard
(~95-100%), demon (~125-140%) -- and the engine's More/Less chance at each is
compared with the real result. Two engines: this morning's (no zero-game
mass) and the current one (zero-catch + zero-rush). Also: the "most likely"
style picks (engine >= 70%), and whether ESPN agreeing made picks better.

    cd backend && source venv/bin/activate
    python scripts/experiments/engine_2026.py
"""
import json
import os
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
from app.services import betting_model as bm  # noqa: E402

CACHE = os.path.join(HERE, "..", "..", ".cache", "backtest")
MARKETS = {"player_pass_yds": "pass_yd", "player_rush_yds": "rush_yd",
           "player_reception_yds": "rec_yd", "player_receptions": "rec"}
FLOOR = {"player_pass_yds": 150, "player_rush_yds": 15, "player_reception_yds": 15, "player_receptions": 1.5}
TIERS = {"goblin": (0.5, 0.6, 0.7), "standard": (0.95, 1.0), "demon": (1.25, 1.4)}


def espn_index(season, week):
    try:
        rows = json.load(open(os.path.join(CACHE, f"espn_projections_{season}_{week}.json")))
    except FileNotFoundError:
        return {}
    rows = rows if isinstance(rows, list) else list(rows.values()) if isinstance(rows, dict) else []
    out = {}
    for r in rows:
        name = (r.get("name") or r.get("player") or "").lower() if isinstance(r, dict) else ""
        if name:
            out[name] = r
    return out


def cases(season, weeks):
    out = []
    for w in weeks:
        try:
            P = json.load(open(os.path.join(CACHE, f"projections_{season}_{w}.json")))
            S = json.load(open(os.path.join(CACHE, f"stats_{season}_{w}.json")))
        except FileNotFoundError:
            continue
        P = P if isinstance(P, list) else list(P.values())
        S = S if isinstance(S, list) else list(S.values())
        sm = {r.get("player_id"): r for r in S}
        for r in P:
            st = r.get("stats") or {}
            pl = r.get("player") or {}
            s = sm.get(r.get("player_id"))
            if not s or not (s.get("stats") or {}).get("gp"):
                continue
            a = s["stats"]
            name = f"{pl.get('first_name', '')} {pl.get('last_name', '')}".strip()
            for market, key in MARKETS.items():
                proj = float(st.get(key) or 0)
                if proj < FLOOR[market]:
                    continue
                if market == "player_pass_yds" and pl.get("position") != "QB":
                    continue
                p0 = None
                if market in bm.ZERO_CATCH_MARKETS:
                    p0 = bm.zero_catch_prob(float(st.get("rec") or 0))
                elif market == "player_rush_yds":
                    p0 = bm.zero_rush_prob(proj)
                out.append({"week": w, "name": name, "pos": pl.get("position"), "market": market,
                            "proj": proj, "actual": float(a.get(key) or 0), "p0": p0})
    return out


def run(rows):
    """Every (case, tier line, side) priced by both engines."""
    out = []
    for i, c in enumerate(rows):
        old = bm.simulate_stat(c["market"], c["proj"], f"e|{i}", n=4000)
        new = bm.simulate_stat(c["market"], c["proj"], f"e|{i}", n=4000, p_zero=c["p0"])
        for tier, fracs in TIERS.items():
            for f in fracs:
                line = np.floor(c["proj"] * f) + 0.5
                po, pn = float((old > line).mean()), float((new > line).mean())
                hit = c["actual"] > line
                out.append({**c, "tier": tier, "line": line, "side": "More", "p_old": po, "p_new": pn, "hit": hit})
                if tier != "goblin":  # PrizePicks goblins are More-only
                    out.append({**c, "tier": tier, "line": line, "side": "Less", "p_old": 1 - po, "p_new": 1 - pn,
                                "hit": not hit})
    return out


def report(picks, label):
    print(f"\n=== {label}: {len(picks)} priced picks ===")
    y = np.array([p["hit"] for p in picks], float)
    for eng in ("p_old", "p_new"):
        p = np.array([q[eng] for q in picks])
        print(f"  {'this morning' if eng == 'p_old' else 'current':12} Brier {np.mean((p - y) ** 2):.4f}")
    print("  Calibration (when the engine said X%, how often it hit):")
    print(f"    {'said':>9} {'n':>6} {'morning: said':>14} {'hit':>6} | {'current: said':>14} {'hit':>6}")
    for lo, hi in ((0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)):
        row = []
        for eng in ("p_old", "p_new"):
            sel = [q for q in picks if lo <= q[eng] < hi]
            row.append((len(sel), np.mean([q[eng] for q in sel]) if sel else float("nan"),
                        np.mean([q["hit"] for q in sel]) if sel else float("nan")))
        (n1, s1, h1), (n2, s2, h2) = row
        print(f"    {int(lo*100):>3}-{int(min(hi,1)*100):<3}%  {n1:>5}/{n2:<5} {s1:>9.1%} {h1:>8.1%} | {s2:>10.1%} {h2:>8.1%}")


def main():
    rows = cases(2026, range(1, 5))
    print(f"2026 weeks 1-4: {len(rows)} player-week-markets with a projection and a game played")
    picks = run(rows)
    report(picks, "All tiers, both sides")
    for tier in TIERS:
        report([p for p in picks if p["tier"] == tier], f"{tier.capitalize()}-style lines")
    # "Most likely to win" style: More picks the engine put at 70%+ on goblin-style lines.
    print("\n=== Most likely to win style (goblin lines, engine >= 70%) ===")
    for eng, label in (("p_old", "this morning"), ("p_new", "current")):
        sel = [p for p in picks if p["tier"] == "goblin" and p[eng] >= bm.MOST_LIKELY_MIN]
        if sel:
            print(f"  {label:12} n={len(sel):5d}  said {np.mean([p[eng] for p in sel]):.1%}  hit {np.mean([p['hit'] for p in sel]):.1%}")
    print("\n  By market (current engine, goblin lines >= 70%):")
    by = defaultdict(list)
    for p in picks:
        if p["tier"] == "goblin" and p["p_new"] >= bm.MOST_LIKELY_MIN:
            by[p["market"]].append(p)
    for m, ps in sorted(by.items()):
        print(f"    {m:22} n={len(ps):5d} said {np.mean([p['p_new'] for p in ps]):.1%}  hit {np.mean([p['hit'] for p in ps]):.1%}")
    print("\n  By week (current engine, all picks):")
    for w in range(1, 5):
        ps = [p for p in picks if p["week"] == w]
        if ps:
            print(f"    week {w}: n={len(ps):5d} said {np.mean([p['p_new'] for p in ps]):.1%} hit {np.mean([p['hit'] for p in ps]):.1%}")


if __name__ == "__main__":
    main()
