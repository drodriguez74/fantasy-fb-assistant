"""Diagnostics behind the props_dist_eval results.

    cd backend && source venv/bin/activate
    python scripts/experiments/props_dist_diag.py

1. Does spread depend on role? Under the current model (level fitted on 2025
   wk 4-10), share of actuals inside the central 80% interval (q10..q90) and
   below q10 / above q90, by position, projection tercile, lagged snap-share
   and target-share tercile, on all held-out cases pooled. A feature worth
   conditioning on shows coverage far from 80% in some bucket, consistently.
2. Is a player's spread persistent? Correlation between his earlier squared
   normal scores (z = Phi^-1(PIT) under the current model) and this week's,
   for players with >= 6 earlier games.
3. Pooled held-out comparison (all three test sets) for passing yards:
   current vs Normal(cv) vs current_refit.
"""
import os
import sys
from collections import defaultdict

import numpy as np
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import props_dist_data as D  # noqa: E402
import props_dist_eval as E  # noqa: E402


def wilson(k, n):
    if n == 0:
        return (np.nan, np.nan)
    p, z = k / n, 1.96
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return c - h, c + h


def main():
    sp = D.load_splits()
    train = sp["train_2025_w4-10"]
    test = sp["test_2025_w11-17"] + sp["test_2026_w1-4"] + sp["test_2024_w4-17"]
    cur = E.Current()
    print("== 1. Coverage of the current model's central 80% interval by bucket (held-out, pooled) ==")
    for market in D.MARKETS:
        tr = [c for c in train if c["market"] == market]
        model = cur.fit(market, tr)
        cs = [c for c in test if c["market"] == market]
        M = cur.predict(market, model, cs)
        u = E.pit(M, E.arr(cs, "actual"), np.random.default_rng(1))
        feats = {"pos": [c["pos"] for c in cs]}
        for k in ("proj", "snap_share", "tgt_share"):
            v = E.arr(cs, k)
            if k == "tgt_share" and market in ("player_pass_yds",):
                continue
            ed = np.nanquantile(v, [1 / 3, 2 / 3])
            feats[k] = [("nan" if np.isnan(x) else ["low", "mid", "high"][int(np.searchsorted(ed, x))]) for x in v]
        print(f"\n{market} (n={len(cs)})  overall: below q10 {np.mean(u < .1):.3f}, above q90 {np.mean(u > .9):.3f}")
        for k, lab in feats.items():
            groups = defaultdict(list)
            for i, g in enumerate(lab):
                groups[g].append(i)
            for g in sorted(groups):
                idx = np.array(groups[g])
                if len(idx) < 60:
                    continue
                inside = np.sum((u[idx] >= .1) & (u[idx] <= .9))
                lo, hi = wilson(inside, len(idx))
                print(f"   {k:10} {g:5} n={len(idx):5d}  in 80% band {inside / len(idx):.3f} [{lo:.3f},{hi:.3f}]"
                      f"  below q10 {np.mean(u[idx] < .1):.3f}  above q90 {np.mean(u[idx] > .9):.3f}")

    print("\n== 2. Persistence of player-specific spread (current model normal scores) ==")
    for market in D.MARKETS:
        tr = [c for c in train if c["market"] == market]
        model = cur.fit(market, tr)
        cs = [c for c in test if c["market"] == market and len(c["hist"]) >= 6]
        a = E.arr(cs, "actual")
        z = stats.norm.ppf(np.clip(E.pit(cur.predict(market, model, cs), a, np.random.default_rng(2)), 1e-4, 1 - 1e-4))
        hz2 = []
        for c in cs:
            hc = [{"proj": p, "actual": x} for p, x in c["hist"]]
            hu = E.pit(cur.predict(market, model, hc), E.arr(hc, "actual"), np.random.default_rng(3))
            hz2.append(np.mean(stats.norm.ppf(np.clip(hu, 1e-4, 1 - 1e-4)) ** 2))
        hz2 = np.array(hz2)
        rho, p = stats.spearmanr(hz2, z ** 2)
        hi = hz2 > np.quantile(hz2, 2 / 3)
        lo = hz2 < np.quantile(hz2, 1 / 3)
        print(f"{market:22} n={len(cs):5d}  spearman(hist z^2, z^2) {rho:+.3f} (p={p:.2f})"
              f" | this-week z^2: high-history-spread third {np.mean(z[hi] ** 2):.2f}, low third {np.mean(z[lo] ** 2):.2f}")

    print("\n== 3. Passing yards pooled over all held-out sets (n, pinball, P(over) Brier/bias by region) ==")
    market = "player_pass_yds"
    tr = [c for c in train if c["market"] == market]
    cs = [c for c in test if c["market"] == market]
    cl = E.clusters(cs)
    base = None
    for m in (E.Current(), E.CurrentRefit(), E.Normal()):
        model = m.fit(market, tr)
        for centered in (False, True):
            sc = E.center_scale(m, market, model, cs) if centered else 1.0
            pin, u, reg = E.per_case_scores(m.predict(market, model, cs, sc), cs, np.random.default_rng(21))
            brier = {k: ((P - Y) ** 2).mean(1) for k, (P, Y) in reg.items()}
            bias = {k: (P - Y).mean(1) for k, (P, Y) in reg.items()}
            key = centered
            if m.name == "current":
                base = base or {}
                base[key] = (pin, brier)
            dp = E.boot_ci((pin - base[key][0]) / base[key][0].mean() * 100, cl)
            parts = []
            for k in E.REGIONS:
                b = E.boot_ci((brier[k] - base[key][1][k]) * 1e3, cl)
                bb = E.boot_ci(bias[k], cl)
                parts.append(f"{k} bias {bb[0]:+.3f}[{bb[1]:+.3f},{bb[2]:+.3f}] dBrier {b[0]:+.1f}[{b[1]:+.1f},{b[2]:+.1f}]")
            print(f"{m.name:14} {'centered' if centered else 'trainlvl'} n={len(cs)} pinball {pin.mean():.3f}"
                  f" d {dp[0]:+.2f}% [{dp[1]:+.2f},{dp[2]:+.2f}] | " + " | ".join(parts))


if __name__ == "__main__":
    main()
