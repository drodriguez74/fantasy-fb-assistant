"""Backtest and calibrate the betting model's outcome spread against real games.

Uses a past season's Sleeper weekly projections and actual stats (free, no
Odds API credits). For every player-week where the player played and was
projected for a prop-sized amount, it checks how well betting_model's
simulated distribution (projection error + gamma/Poisson outcome noise)
covers what actually happened, then fits the spread settings per market.

    python scripts/backtest_projections.py               # report + fit (2025 season)
    python scripts/backtest_projections.py --season 2026 # once a season is complete

Method:
- Fit on weeks 4-10, validate on weeks 11-17 (no peeking).
- Score = average pinball loss over the 10th..90th percentiles (a proper
  scoring rule for quantile forecasts; lower is better). Coverage (share of
  actuals below the 10th percentile / median / above the 90th) is reported too.
- A per-market level factor is fitted alongside the spread but not shipped:
  live, slate centering (fit_projection_scale) sets the level from the
  market each week, so only the shape settings matter.

First run (2026-10-07, 2025 season, 4,556 cases) is recorded in
docs/guides/BETTING_GUIDE.md. The same harness was used to test Google's
TimesFM 3 as a projection source (rejected; see the guide).
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.services import betting_model as bm  # noqa: E402

CACHE = os.path.join(os.path.dirname(__file__), "..", ".cache", "backtest")
POSITIONS = ("QB", "RB", "WR", "TE")
# Sleeper stat -> (betting market, position filter, prop-sized projection floor)
STATS = {
    "pass_yd": ("player_pass_yds", "QB", 150.0),
    "rush_yd": ("player_rush_yds", None, 20.0),
    "rec_yd": ("player_reception_yds", None, 20.0),
    "rec": ("player_receptions", None, 2.0),
}
DECILES = np.arange(1, 10) / 10
SIMS = 1500


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def _get(kind: str, season: int, week: int):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"{kind}_{season}_{week}.json")
    if not os.path.exists(path):
        pos = "&".join(f"position[]={p}" for p in POSITIONS)
        url = f"https://api.sleeper.app/{kind}/nfl/{season}/{week}?season_type=regular&{pos}"
        req = urllib.request.Request(url, headers={"User-Agent": "ff-assistant-backtest"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
        with open(path, "w") as f:
            json.dump(data, f)
        time.sleep(0.2)
    with open(path) as f:
        return json.load(f)


def build_cases(season: int):
    actual = {}
    for week in range(1, 19):
        for r in _get("stats", season, week):
            st = r.get("stats") or {}
            if st.get("gp"):
                actual[(r["player_id"], week)] = st
    cases = []
    for week in range(4, 18):
        for r in _get("projections", season, week):
            st = actual.get((r["player_id"], week))
            if st is None:
                continue  # didn't play: books void the prop
            proj = r.get("stats") or {}
            pos = (r.get("player") or {}).get("position")
            for stat, (market, only_pos, floor) in STATS.items():
                p = proj.get(stat)
                if (only_pos and pos != only_pos) or p is None or p < floor:
                    continue
                cases.append({"market": market, "week": week, "proj": float(p), "actual": float(st.get(stat) or 0.0)})
    return cases


# ---------------------------------------------------------------------------
# Model (mirrors betting_model.simulate_stat, with every setting exposed)
# ---------------------------------------------------------------------------

def current_params(market: str) -> dict:
    p = {"level": 1.0, "proj_err": bm.projection_error(market), "dud": bm.DUD_PROB.get(market, 0.0)}
    if market in bm.YARDS_CV:
        p["cv"] = bm.YARDS_CV[market]
    return p


def simulate(market: str, means: np.ndarray, params: dict, rng: np.random.Generator) -> np.ndarray:
    """(cases, SIMS) outcomes. Same structure as betting_model.simulate_stat."""
    m = means[:, None] * params["level"]
    true_mean = np.clip(m + params["proj_err"] * m * rng.standard_normal((len(means), SIMS)), 0.01, None)
    if market not in bm.YARDS_CV:
        return rng.poisson(true_mean).astype(float)
    cv = params["cv"] * (bm.YARDS_REF_MEAN[market] / np.maximum(means, 1.0)) ** bm.VOLUME_EXPONENT
    cv = np.clip(cv, params["cv"] * 0.8, bm.MAX_YARDS_CV)[:, None]
    shape = 1 / cv ** 2
    out = rng.gamma(np.broadcast_to(shape, true_mean.shape), true_mean / shape)
    return bm.apply_duds(out, true_mean, params["dud"], rng)


def score(market: str, cases: list, params: dict, seed: int = 7):
    means = np.array([c["proj"] for c in cases])
    actual = np.array([c["actual"] for c in cases])
    sims = simulate(market, means, params, np.random.default_rng(seed))
    q = np.quantile(sims, DECILES, axis=1).T  # (cases, 9)
    diff = actual[:, None] - q
    pinball = float(np.mean(np.maximum(DECILES * diff, (DECILES - 1) * diff)))
    coverage = (float(np.mean(actual < q[:, 0])), float(np.mean(actual < q[:, 4])), float(np.mean(actual > q[:, 8])))
    return pinball, coverage


GRIDS = {
    "level": np.round(np.arange(0.90, 1.21, 0.02), 3),
    "proj_err": np.round(np.arange(0.0, 0.41, 0.025), 3),
    "cv": np.round(np.arange(0.15, 0.86, 0.025), 3),
    "dud": np.round(np.arange(0.0, 0.16, 0.01), 3),
}


def fit(market: str, cases: list) -> dict:
    """Coordinate descent over the settings, 3 passes, common random numbers."""
    params = current_params(market)
    keys = ["level", "proj_err"] + (["cv", "dud"] if market in bm.YARDS_CV else [])
    best = score(market, cases, params)[0]
    for _ in range(3):
        for k in keys:
            for v in GRIDS[k]:
                trial = {**params, k: float(v)}
                s = score(market, cases, trial)[0]
                if s < best - 1e-9:
                    best, params = s, trial
    return params


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2025)
    args = ap.parse_args()
    cases = build_cases(args.season)
    by_market = defaultdict(list)
    for c in cases:
        by_market[c["market"]].append(c)
    print(f"{args.season}: {len(cases)} cases (fit weeks 4-10, validate weeks 11-17)\n")
    fitted = {}
    for market, cs in by_market.items():
        fit_set = [c for c in cs if c["week"] <= 10]
        val_set = [c for c in cs if c["week"] > 10]
        cur = current_params(market)
        new = fit(market, fit_set)
        # Compare shapes fairly: the current settings get the fitted level too.
        cur_leveled = {**cur, "level": new["level"]}
        fitted[market] = new
        for label, p in (("current", cur_leveled), ("fitted ", new)):
            pin, cov = score(market, val_set, p, seed=11)
            shape = {k: v for k, v in p.items() if k != "level"}
            print(f"{market:22} {label} validation pinball {pin:7.3f} | below q10 {cov[0]:4.0%}  below median {cov[1]:4.0%}"
                  f"  above q90 {cov[2]:4.0%} | {shape}")
        print(f"{'':22} (level factor {new['level']}: Sleeper's projections vs actuals; live, slate centering handles level)\n")
    print("Fitted shape settings:", json.dumps({m: {k: v for k, v in p.items() if k != 'level'} for m, p in fitted.items()}))


if __name__ == "__main__":
    main()
