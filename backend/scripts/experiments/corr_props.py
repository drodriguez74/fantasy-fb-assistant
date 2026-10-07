"""Measure same-game prop correlations (LEG_CORRELATION) from real outcomes.

Data: Sleeper weekly projections + stats (2024 wk 1-18, 2025 wk 1-18,
2026 wk 1-4; cached in .cache/backtest/ by scripts/backtest_projections.py's
fetcher) and nflverse closing totals.

For every prop-sized projection (the floors scripts/backtest_projections.py
uses) a synthetic line is set at projection x k, with k the market/season
median of actual/projection, so each market goes Over ~50% of the time
(the books' lines are centred the same way; Sleeper's raw projections are
biased by market). For each pair type in the same game we report
  - phi of the two Over indicators, converted to the latent Gaussian
    (copula) correlation at 50/50 legs: rho = sin(pi * phi / 2) -- the
    number joint_prob / hit_count_distribution consume;
  - the normal-score correlation of the continuous outcomes (rank of
    actual/projection within market-season -> Phi^-1), a second estimate of
    the copula rho that uses the whole distribution;
with 95% CIs from a game-cluster bootstrap. Also each market's Over vs the
game going Over its closing total.

    python scripts/experiments/corr_props.py
"""
import csv
import json
import os
import sys
from collections import defaultdict

import numpy as np
from scipy.stats import norm, rankdata

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.services import betting_model as bm  # noqa: E402

CACHE = os.path.join(os.path.dirname(__file__), "..", "..", ".cache", "backtest")
SEASONS = {2024: range(1, 19), 2025: range(1, 19), 2026: range(1, 5)}
B = 2000
RNG = np.random.default_rng(5)

PASS, RUSH, RECY, RECS = "player_pass_yds", "player_rush_yds", "player_reception_yds", "player_receptions"
STATS = {"pass_yd": (PASS, ("QB",), 150.0), "rush_yd": (RUSH, ("QB", "RB", "WR"), 20.0),
         "rec_yd": (RECY, ("RB", "WR", "TE"), 20.0), "rec": (RECS, ("RB", "WR", "TE"), 2.0)}
NFLVERSE_TEAM = {"LAR": "LA"}

# (label, market a, positions a, market b, positions b, same team)
PAIRS = [
    ("QB pass yds  ~ own WR/TE rec yds", PASS, ("QB",), RECY, ("WR", "TE"), True),
    ("QB pass yds  ~ own WR/TE receptions", PASS, ("QB",), RECS, ("WR", "TE"), True),
    ("QB pass yds  ~ own RB rec yds", PASS, ("QB",), RECY, ("RB",), True),
    ("QB pass yds  ~ own RB rush yds", PASS, ("QB",), RUSH, ("RB",), True),
    ("QB pass yds  ~ own QB rush (n/a)", PASS, ("QB",), RUSH, ("QB",), True),
    ("RB rush yds  ~ own WR/TE rec yds", RUSH, ("RB",), RECY, ("WR", "TE"), True),
    ("RB rush yds  ~ own RB rush yds", RUSH, ("RB",), RUSH, ("RB",), True),
    ("WR/TE rec yds ~ own WR/TE rec yds", RECY, ("WR", "TE"), RECY, ("WR", "TE"), True),
    ("WR/TE recs   ~ own WR/TE recs", RECS, ("WR", "TE"), RECS, ("WR", "TE"), True),
    ("QB pass yds  ~ opp QB pass yds", PASS, ("QB",), PASS, ("QB",), False),
    ("QB pass yds  ~ opp WR/TE rec yds", PASS, ("QB",), RECY, ("WR", "TE"), False),
    ("QB pass yds  ~ opp WR/TE receptions", PASS, ("QB",), RECS, ("WR", "TE"), False),
    ("QB pass yds  ~ opp RB rush yds", PASS, ("QB",), RUSH, ("RB",), False),
    ("WR/TE rec yds ~ opp WR/TE rec yds", RECY, ("WR", "TE"), RECY, ("WR", "TE"), False),
    ("WR/TE rec yds ~ opp RB rush yds", RECY, ("WR", "TE"), RUSH, ("RB",), False),
    ("WR/TE recs   ~ opp WR/TE recs", RECS, ("WR", "TE"), RECS, ("WR", "TE"), False),
    ("RB rush yds  ~ opp RB rush yds", RUSH, ("RB",), RUSH, ("RB",), False),
]


def load_json(kind, season, week):
    with open(os.path.join(CACHE, f"{kind}_{season}_{week}.json")) as f:
        return json.load(f)


def closing_totals():
    out = {}
    with open(os.path.join(CACHE, "nflverse_games.csv")) as f:
        for r in csv.DictReader(f):
            if int(r["season"]) in SEASONS and r["total"] and r["total_line"]:
                err = float(r["total"]) - float(r["total_line"])
                for t in (r["home_team"], r["away_team"]):
                    out[(int(r["season"]), int(r["week"]), t)] = err
    return out


def build_legs():
    legs = []
    for season, weeks in SEASONS.items():
        for week in weeks:
            actual = {r["player_id"]: r["stats"] for r in load_json("stats", season, week) if (r.get("stats") or {}).get("gp")}
            for r in load_json("projections", season, week):
                st = actual.get(r["player_id"])
                pos = (r.get("player") or {}).get("position")
                if st is None or not r.get("game_id") or not r.get("team"):
                    continue
                proj = r.get("stats") or {}
                for stat, (market, poss, floor) in STATS.items():
                    p = proj.get(stat)
                    if pos not in poss or p is None or p < floor:
                        continue
                    legs.append({"season": season, "week": week, "game": f"{season}|{r['game_id']}", "team": r["team"],
                                 "pid": r["player_id"], "pos": pos, "market": market, "proj": float(p),
                                 "actual": float(st.get(stat) or 0.0)})
    # centre each market-season at 50% Over; normal scores of actual/projection
    by = defaultdict(list)
    for i, l in enumerate(legs):
        by[(l["season"], l["market"])].append(i)
    for idx in by.values():
        ratio = np.array([legs[i]["actual"] / legs[i]["proj"] for i in idx])
        k = np.median(ratio)
        z = norm.ppf((rankdata(ratio) - 0.5) / len(ratio))
        for j, i in enumerate(idx):
            legs[i]["over"] = ratio[j] > k
            legs[i]["z"] = z[j]
    return legs


def wcorr(x, y, w):
    mx, my = np.average(x, weights=w), np.average(y, weights=w)
    cov = np.average((x - mx) * (y - my), weights=w)
    return cov / np.sqrt(np.average((x - mx) ** 2, weights=w) * np.average((y - my) ** 2, weights=w))


def boot(gidx, ngames, xs, ys):
    """Point estimates and game-cluster bootstrap CIs for phi(xs[0], ys[0]) and corr(xs[1], ys[1])."""
    point = [np.corrcoef(x, y)[0, 1] for x, y in zip(xs, ys)]
    draws = []
    for _ in range(B):
        w = np.bincount(RNG.integers(0, ngames, ngames), minlength=ngames)[gidx].astype(float)
        if w.sum() == 0:
            continue
        draws.append([wcorr(x, y, w) for x, y in zip(xs, ys)])
    draws = np.array(draws)
    return point, np.percentile(draws, [2.5, 97.5], axis=0)


def to_rho(phi):
    return np.sin(np.pi * np.asarray(phi) / 2)


def main():
    legs = build_legs()
    games = sorted({l["game"] for l in legs})
    gi = {g: i for i, g in enumerate(games)}
    by_game = defaultdict(list)
    for l in legs:
        by_game[l["game"]].append(l)
    print(f"{len(legs)} prop-sized legs, {len(games)} games, seasons {list(SEASONS)}")
    print(f"{'pair':38} {'n':>5} {'phi':>6}  {'copula rho = sin(pi*phi/2) [95% CI]':>36}  {'normal-score rho [95% CI]':>27}  shipped")
    results = {}
    for label, ma, pa, mb, pb, same in PAIRS:
        g, xo, yo, xz, yz = [], [], [], [], []
        for game, ls in by_game.items():
            A = [l for l in ls if l["market"] == ma and l["pos"] in pa]
            Bs = [l for l in ls if l["market"] == mb and l["pos"] in pb]
            seen = set()
            for a in A:
                for b in Bs:
                    if a["pid"] == b["pid"] or (a["team"] == b["team"]) != same:
                        continue
                    key = frozenset((a["pid"], b["pid"]))
                    if ma == mb and key in seen:
                        continue
                    seen.add(key)
                    g.append(gi[game]); xo.append(a["over"]); yo.append(b["over"]); xz.append(a["z"]); yz.append(b["z"])
        if len(g) < 30:
            continue
        g = np.array(g)
        (phi, ns), ci = boot(g, len(games), [np.array(xo, float), np.array(xz)], [np.array(yo, float), np.array(yz)])
        r, rci = to_rho(phi), to_rho(ci[:, 0])
        shipped = bm.leg_correlation(ma, mb, True, same)
        results[label] = (len(g), r, rci, ns, ci[:, 1], shipped)
        sig = "*" if rci[0] > 0 or rci[1] < 0 else " "
        print(f"{label:38} {len(g):5} {phi:+.3f}  {r:+.3f} [{rci[0]:+.3f},{rci[1]:+.3f}]{sig}"
              f"            {ns:+.3f} [{ci[0, 1]:+.3f},{ci[1, 1]:+.3f}]      {shipped:+.2f}")

    print("\nEach market's Over vs the game going Over its closing total (copula rho from phi; normal-score vs total error):")
    tot = closing_totals()
    for market in (PASS, RUSH, RECY, RECS):
        g, xo, yo, xz, yz = [], [], [], [], []
        for l in legs:
            err = tot.get((l["season"], l["week"], NFLVERSE_TEAM.get(l["team"], l["team"])))
            if l["market"] != market or err is None or err == 0:
                continue
            g.append(gi[l["game"]]); xo.append(l["over"]); yo.append(err > 0); xz.append(l["z"]); yz.append(err)
        g = np.array(g)
        (phi, ns), ci = boot(g, len(games), [np.array(xo, float), np.array(xz)], [np.array(yo, float), np.array(yz)])
        rci = to_rho(ci[:, 0])
        print(f"  {market:22} n={len(g):5}  rho {to_rho(phi):+.3f} [{rci[0]:+.3f},{rci[1]:+.3f}]   normal-score vs total err {ns:+.3f} [{ci[0, 1]:+.3f},{ci[1, 1]:+.3f}]")

    with open(os.path.join(CACHE, "corr_props_results.json"), "w") as f:
        json.dump({k: {"n": v[0], "rho": float(v[1]), "rho_ci": [float(x) for x in v[2]], "normal_score": float(v[3]),
                       "shipped": v[5]} for k, v in results.items()}, f, indent=1)


if __name__ == "__main__":
    main()
