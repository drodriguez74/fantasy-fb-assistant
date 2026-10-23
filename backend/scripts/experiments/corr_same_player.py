"""Measure same-player prop correlations (two stats of one player in one entry).

PrizePicks lets one entry hold two stats of the same player (seen 2026-10-22:
Roschon Johnson targets + receiving yards). Those legs move together far
more than teammates do, so pricing them as independent is badly wrong. Same
data and method as corr_props.py: Sleeper weekly projections + stats (2024
wk 1-18, 2025 wk 1-18, 2026 wk 1-4, cached in .cache/backtest/), a synthetic
line at projection x k per market-season (k = median actual/projection, so
each market goes Over ~50%), then for each pair of one player's stats
  - phi of the two Over indicators -> copula rho = sin(pi * phi / 2);
  - the normal-score correlation of the continuous outcomes;
with 95% CIs from a player-week cluster bootstrap. Prints a table and writes
.cache/backtest/corr_same_player_results.json.

    python scripts/experiments/corr_same_player.py
"""
import json
import os
import sys
from collections import defaultdict
from itertools import combinations

import numpy as np
from scipy.stats import norm, rankdata

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from corr_props import CACHE, SEASONS, boot, load_json, to_rho  # noqa: E402

# Sleeper stat -> market key; per position group the stats it's offered on
# and the projection floor below which PrizePicks wouldn't post the stat.
MARKET = {"pass_yd": "player_pass_yds", "pass_att": "player_pass_attempts", "pass_cmp": "player_pass_completions",
          "pass_td": "player_pass_tds", "pass_int": "player_pass_interceptions", "rush_yd": "player_rush_yds",
          "rush_att": "player_rush_attempts", "rec": "player_receptions", "rec_yd": "player_reception_yds",
          "rec_tgt": "player_rec_targets"}
GROUPS = {
    "QB": (("QB",), {"pass_yd": 150, "pass_att": 20, "pass_cmp": 12, "pass_td": 0.8, "pass_int": 0.3,
                     "rush_yd": 10, "rush_att": 2}),
    "RB": (("RB",), {"rush_yd": 20, "rush_att": 5, "rec": 1.5, "rec_yd": 10, "rec_tgt": 2}),
    "WR/TE": (("WR", "TE"), {"rec": 1.5, "rec_yd": 15, "rec_tgt": 2}),
}


def build():
    """One row per player-week: {group, cluster, stat: (over, z)} for every stat above its floor."""
    rows = []
    for season, weeks in SEASONS.items():
        for week in weeks:
            actual = {r["player_id"]: r["stats"] for r in load_json("stats", season, week) if (r.get("stats") or {}).get("gp")}
            for r in load_json("projections", season, week):
                st, pos = actual.get(r["player_id"]), (r.get("player") or {}).get("position")
                group = next((g for g, (poss, _) in GROUPS.items() if pos in poss), None)
                if st is None or group is None:
                    continue
                proj = r.get("stats") or {}
                legs = {s: (float(proj[s]), float(st.get(s) or 0.0)) for s, floor in GROUPS[group][1].items()
                        if proj.get(s) is not None and proj[s] >= floor}
                if len(legs) >= 2:
                    rows.append({"group": group, "season": season, "cluster": f"{season}|{week}|{r['player_id']}", "legs": legs})
    # centre each (group, stat, season) at 50% Over; normal scores of actual/projection
    by = defaultdict(list)
    for i, row in enumerate(rows):
        for s in row["legs"]:
            by[(row["group"], s, row["season"])].append(i)
    out = [dict(row, scored={}) for row in rows]
    for (group, s, season), idx in by.items():
        ratio = np.array([rows[i]["legs"][s][1] / rows[i]["legs"][s][0] for i in idx])
        k = np.median(ratio)
        z = norm.ppf((rankdata(ratio) - 0.5) / len(ratio))
        for j, i in enumerate(idx):
            out[i]["scored"][s] = (ratio[j] > k, z[j])
    return out


def main():
    rows = build()
    clusters = sorted({r["cluster"] for r in rows})
    ci_of = {c: i for i, c in enumerate(clusters)}
    print(f"{len(rows)} player-weeks with 2+ prop-sized stats, seasons {list(SEASONS)}")
    print(f"{'group':6} {'pair':48} {'n':>6} {'copula rho [95% CI]':>26} {'normal-score [95% CI]':>26}")
    results = {}
    for group, (_, floors) in GROUPS.items():
        for a, b in combinations(floors, 2):
            g, xo, yo, xz, yz = [], [], [], [], []
            for r in rows:
                if r["group"] == group and a in r["scored"] and b in r["scored"]:
                    g.append(ci_of[r["cluster"]])
                    xo.append(r["scored"][a][0]); yo.append(r["scored"][b][0])
                    xz.append(r["scored"][a][1]); yz.append(r["scored"][b][1])
            if len(g) < 100:
                continue
            (phi, ns), ci = boot(np.array(g), len(clusters), [np.array(xo, float), np.array(xz)],
                                 [np.array(yo, float), np.array(yz)])
            rho, rci = to_rho(phi), to_rho(ci[:, 0])
            label = f"{MARKET[a]} ~ {MARKET[b]}"
            results[f"{group}|{MARKET[a]}|{MARKET[b]}"] = {"n": len(g), "rho": round(float(rho), 3),
                                                            "rho_ci": [round(float(x), 3) for x in rci],
                                                            "normal_score": round(float(ns), 3)}
            print(f"{group:6} {label:48} {len(g):6} {rho:+.3f} [{rci[0]:+.3f},{rci[1]:+.3f}]"
                  f"      {ns:+.3f} [{ci[0, 1]:+.3f},{ci[1, 1]:+.3f}]")
    with open(os.path.join(CACHE, "corr_same_player_results.json"), "w") as f:
        json.dump(results, f, indent=1)


if __name__ == "__main__":
    main()
