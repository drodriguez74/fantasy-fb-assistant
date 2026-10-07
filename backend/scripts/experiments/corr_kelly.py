"""Kelly sizing when the estimated edge is only partly real.

Input: the per-line CSV from scripts/backtest_game_lines.py (2025, closing
lines, every priced line with the blended p_win, de-vigged market_prob,
price and result). Two parts:

1. Empirical shrinkage: regress result (W=1/L=0) - market_prob on the
   estimated edge p_win - market_prob. The slope lambda is how much of the
   estimated edge was real (1 = all of it, 0 = none). Game-bootstrap CI.
2. Simulation: resample seasons of lines from the CSV's real edge
   distribution, set the true probability to market + lambda x estimated
   edge, and bet with Kelly fraction f and EV threshold t (units capped at
   MAX_UNITS, 0.5u steps, 1u = 1% of bankroll, rebalanced weekly-ish per
   bet). Report mean ROI, median bankroll growth and P(drawdown > 20%).

    python scripts/backtest_game_lines.py --csv .cache/backtest/corr_game_lines_2025.csv
    python scripts/experiments/corr_kelly.py
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.services import betting_model as bm  # noqa: E402

CACHE = os.path.join(os.path.dirname(__file__), "..", "..", ".cache", "backtest")
RNG = np.random.default_rng(3)
SEASONS = 4000


def load():
    d = pd.read_csv(os.path.join(CACHE, "corr_game_lines_2025.csv"))
    d = d[(d.variant == "shipped") & (d.result != "P")].copy()
    d["win"] = (d.result == "W").astype(float)
    d["edge"] = d.p_win - d.market_prob
    d["dec"] = d.price.apply(bm.american_to_decimal)
    return d


def shrinkage(d, mask, label):
    x, y, g = d.edge[mask].values, (d.win - d.market_prob)[mask].values, d.game[mask].values
    lam = np.sum(x * y) / np.sum(x * x)  # through the origin: zero estimated edge = market
    games = np.unique(g)
    idx = {k: np.where(g == k)[0] for k in games}
    bs = []
    for _ in range(3000):
        i = np.concatenate([idx[k] for k in RNG.choice(games, len(games))])
        bs.append(np.sum(x[i] * y[i]) / np.sum(x[i] * x[i]))
    lo, hi = np.percentile(bs, [2.5, 97.5])
    print(f"  {label:34} n={mask.sum():4}  lambda = {lam:+.2f}  95% CI [{lo:+.2f}, {hi:+.2f}]  mean est. edge {x.mean():+.3f}")
    return lam


def stake_units(p, dec, frac):
    b = dec - 1
    f = (b * p - (1 - p)) / b
    if f <= 0:
        return 0.0
    return min(bm.MAX_UNITS, np.floor(f * frac * 100 / bm.UNIT_STEP) * bm.UNIT_STEP)


def simulate(d, lam, frac, thresh, n_lines=None):
    p_est, mkt, dec = d.p_win.values, d.market_prob.values, d.dec.values
    ev_est = p_est * dec - 1
    elig = np.where(ev_est >= thresh)[0]
    if len(elig) == 0:
        return 0, 0, 0, 0, 0
    units = np.array([stake_units(p_est[i], dec[i], frac) for i in elig])
    keep = units > 0
    elig, units = elig[keep], units[keep]
    if len(elig) == 0:
        return 0, 0, 0, 0, 0
    p_true = np.clip(mkt[elig] + lam * (p_est[elig] - mkt[elig]), 0.01, 0.99)
    n = n_lines or len(d)
    per_season = int(round(len(elig) * n / len(d)))
    rois, growth, dd = [], [], []
    for _ in range(SEASONS):
        k = RNG.integers(0, len(elig), per_season)
        win = RNG.random(per_season) < p_true[k]
        pnl_pct = np.where(win, units[k] * (dec[elig][k] - 1), -units[k]) / 100  # fraction of bankroll
        bank = np.cumprod(1 + pnl_pct)
        rois.append((pnl_pct.sum()) / (units[k].sum() / 100))
        growth.append(bank[-1])
        dd.append((1 - bank / np.maximum.accumulate(np.concatenate([[1], bank]))[1:]).max())
    return per_season, np.mean(rois), np.median(growth), np.mean(np.array(growth) < 1), np.mean(np.array(dd) > 0.2)


def main():
    d = load()
    d["game"] = d.week.astype(str) + d["game"]
    print("1. How much of the estimated edge was real (2025 closing lines, blended p_win):")
    lam_all = shrinkage(d, np.ones(len(d), bool), "all priced lines")
    shrinkage(d, (d.p_win * d.dec - 1 >= bm.MIN_EV).values, f"lines with est. EV >= {bm.MIN_EV:.0%}")
    shrinkage(d, (d.kind == "spread").values, "spreads")
    shrinkage(d, (d.kind == "total").values, "totals")

    print("\n2. Simulated season (2025-sized slate, resampled) -- mean ROI / median bankroll / P(season loss) / P(drawdown>20%)")
    for lam in (0.0, 0.25, 0.5, 1.0):
        print(f"  true edge = {lam:.2f} x estimated")
        for thresh in (0.03, 0.05, 0.08):
            for frac in (0.10, 0.25, 0.50):
                n, roi, g, loss, dd = simulate(d, lam, frac, thresh)
                print(f"    EV>={thresh:.0%} Kelly {frac:.2f}: {n:3} bets  ROI {roi:+6.1%}  median bank x{g:.3f}"
                      f"  P(loss) {loss:.0%}  P(DD>20%) {dd:.0%}")


if __name__ == "__main__":
    main()
