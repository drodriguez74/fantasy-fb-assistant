"""Outcome spread for the prop markets added 2026-10-15 (pass TDs, attempts,
completions, interceptions, rush attempts, rush+rec yards, pass+rush yards).

Same method as scripts/backtest_projections.py: every 2025 player-week where
the player played and was projected for a prop-sized amount; each candidate
distribution around Sleeper's projection is fitted on weeks 4-10 and scored
on weeks 11-17 by pinball loss over the 10th-90th percentiles (lower is
better). Level isn't scored separately: slate centering sets it live.

    cd backend && python scripts/experiments/new_markets_dist.py
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
from backtest_projections import _get  # noqa: E402

DECILES = np.arange(1, 10) / 10
SIMS = 2000
# market: (Sleeper stat keys, position filter, prop-sized projection floor)
MARKETS = {
    "player_pass_tds": (("pass_td",), "QB", 0.8),
    "player_pass_interceptions": (("pass_int",), "QB", 0.3),
    "player_pass_attempts": (("pass_att",), "QB", 20.0),
    "player_pass_completions": (("pass_cmp",), "QB", 12.0),
    "player_rush_attempts": (("rush_att",), None, 5.0),
    "player_rush_rec_yds": (("rush_yd", "rec_yd"), None, 20.0),
    "player_pass_rush_yds": (("pass_yd", "rush_yd"), "QB", 150.0),
}


def cases(market, weeks):
    keys, pos, floor = MARKETS[market]
    out = []
    for w in weeks:
        stats = {r["player_id"]: r.get("stats") or {} for r in _get("stats", 2025, w)}
        for r in _get("projections", 2025, w):
            st, pl = r.get("stats") or {}, r.get("player") or {}
            if pos and pl.get("position") != pos:
                continue
            proj = sum(float(st.get(k) or 0) for k in keys)
            a = stats.get(r["player_id"])
            if proj < floor or not a or not a.get("gp"):
                continue
            out.append((proj, sum(float(a.get(k) or 0) for k in keys)))
    return out


def sample(kind, mean, param, rng):
    if kind == "poisson":  # param: projection error (sd as a share of the mean)
        true = np.clip(rng.normal(mean, param * mean, SIMS), 0.01, None)
        return rng.poisson(true).astype(float)
    if kind == "normal":  # param: CV
        return np.maximum(rng.normal(mean, param * mean, SIMS), 0.0)
    if kind == "gamma":  # param: CV
        shape = 1 / param ** 2
        return rng.gamma(shape, mean / shape, SIMS)
    raise ValueError(kind)


def pinball(rows, kind, param):
    rng = np.random.default_rng(11)
    loss = []
    cover = np.zeros(3)
    for proj, actual in rows:
        q = np.quantile(sample(kind, proj, param, rng), DECILES)
        loss.append(np.mean([max(t * (actual - x), (t - 1) * (actual - x)) for t, x in zip(DECILES, q)]))
        cover += (actual < q[0], actual < q[4], actual > q[8])
    return float(np.mean(loss)), cover / len(rows)


GRIDS = {"poisson": [0.0, 0.1, 0.2, 0.3], "normal": np.round(np.arange(0.10, 0.62, 0.02), 2),
         "gamma": np.round(np.arange(0.20, 1.02, 0.04), 2)}


def main():
    for market in MARKETS:
        train, test = cases(market, range(4, 11)), cases(market, range(11, 18))
        print(f"\n{market}: {len(train)} fit / {len(test)} scored")
        for kind, grid in GRIDS.items():
            best = min(grid, key=lambda p: pinball(train, kind, p)[0])
            loss, cov = pinball(test, kind, best)
            print(f"  {kind:8} param {best:<5} held-out pinball {loss:.4f}   below q10 {cov[0]:.0%} / median {cov[1]:.0%} / above q90 {cov[2]:.0%}")


if __name__ == "__main__":
    main()
