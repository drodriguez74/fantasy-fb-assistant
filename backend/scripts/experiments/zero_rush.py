"""Zero-rushing games (2026-10-07 fix for overconfident low rushing lines).

Finding: QBs end a start with zero or negative rushing yards 19% of the
time (kneel-downs, no scrambles), which the gamma yardage model can't
produce. QBs projected for 5-10 rushing yards cleared Over 0.5 61% of the
time while the model said 94% (a 3u "bet" on Jared Goff Over 0.5 came from
this). Candidate fix, the same shape as zero_catch.py: P(rushing yards <= 0)
as a logistic of ln(projected rushing yards), fitted separately for QBs and
for everyone else on 2025 wk 4-10; rushing yards are 0 that often, otherwise
gamma with the mean preserved. Scored out of sample on 2025 wk 11-17, 2026
wk 1-4 and 2024 wk 4-17 (Brier of P(over) at 0.5 / 4.5 / 9.5 and at 20-120%
of the projection), by position.

    cd backend && source venv/bin/activate
    python scripts/experiments/zero_rush.py
"""
import json
import os
import sys

import numpy as np
from scipy.optimize import minimize

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
from app.services import betting_model as bm  # noqa: E402

CACHE = os.path.join(HERE, "..", "..", ".cache", "backtest")
FRACS = (0.2, 0.4, 0.6, 0.8, 1.0, 1.2)
FIXED = (0.5, 4.5, 9.5)


def load(season, weeks):
    rows = []  # (is_qb, projected rush yds, actual rush yds)
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
            pos = (r.get("player") or {}).get("position")
            st = r.get("stats") or {}
            if pos not in ("QB", "RB", "WR"):
                continue
            pr = float(st.get("rush_yd") or 0)
            s = sm.get(r.get("player_id"))
            if pr < 1 or not s or not (s.get("stats") or {}).get("gp"):
                continue
            if pos == "QB" and float(st.get("pass_yd") or 0) < 150:
                continue  # starters only
            rows.append((pos == "QB", pr, float(s["stats"].get("rush_yd") or 0)))
    return np.array(rows, dtype=float)


def p0_fn(theta, proj):
    a, b = theta
    return 1 / (1 + np.exp(-(a + b * np.log(proj))))


def fit(rows):
    y = (rows[:, 2] <= 0).astype(float)

    def nll(th):
        p = np.clip(p0_fn(th, rows[:, 1]), 1e-6, 1 - 1e-6)
        return -np.sum(y * np.log(p) + (1 - y) * np.log(1 - p))
    return minimize(nll, np.array([0.0, -1.0]), method="Nelder-Mead").x


def score(rows, thetas, label):
    print(f"\n{label}: n={len(rows)}")
    for is_qb, name in ((1.0, "QB"), (0.0, "RB/WR")):
        sel = rows[rows[:, 0] == is_qb]
        if not len(sel):
            continue
        p0 = p0_fn(thetas[name], sel[:, 1])
        print(f"  {name}: P(<=0 rush yds) real {np.mean(sel[:, 2] <= 0):.1%} fitted {p0.mean():.1%} (n={len(sel)})")
        old_b, new_b, ys, po, pn, low = [], [], [], [], [], []
        for i, (q, proj, act) in enumerate(sel):
            old = bm.simulate_stat("player_rush_yds", proj, f"r|{i}", n=3000)
            new = bm.simulate_stat("player_rush_yds", proj, f"r|{i}", n=3000, p_zero=float(p0[i]))
            lines = sorted({np.floor(proj * f) + 0.5 for f in FRACS} | set(FIXED))
            for line in lines:
                y = float(act > line)
                a, b = float((old > line).mean()), float((new > line).mean())
                old_b.append((a - y) ** 2); new_b.append((b - y) ** 2); ys.append(y); po.append(a); pn.append(b)
                low.append(line <= max(4.5, proj * 0.4))
        diff = np.array(new_b) - np.array(old_b)
        rng = np.random.default_rng(1)
        boots = [diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(2000)]
        lo, hi = np.percentile(boots, [2.5, 97.5])
        low = np.array(low)
        print(f"    all lines ({len(diff)}): real {np.mean(ys):.1%} shipped {np.mean(po):.1%} new {np.mean(pn):.1%}"
              f"  Brier diff {diff.mean():+.4f} [{lo:+.4f}, {hi:+.4f}]")
        print(f"    low lines (<= max(4.5, 40% of proj)): real {np.mean(np.array(ys)[low]):.1%}"
              f" shipped {np.mean(np.array(po)[low]):.1%} new {np.mean(np.array(pn)[low]):.1%}")
        hi_ = ~low
        print(f"    other lines: real {np.mean(np.array(ys)[hi_]):.1%} shipped {np.mean(np.array(po)[hi_]):.1%}"
              f" new {np.mean(np.array(pn)[hi_]):.1%}")


def main():
    f = load(2025, range(4, 11))
    # Fitted separately the two groups came out nearly identical (QB 2.635 /
    # -1.489, RB/WR 2.590 / -1.489), so one pooled fit is shipped for both.
    pooled = fit(f)
    thetas = {"QB": pooled, "RB/WR": pooled}
    for k, th in thetas.items():
        print(f"{k}: P(<=0 rush yds) = logistic({th[0]:.4f} + {th[1]:.4f} * ln(projected rush yds));"
              + " ".join(f" proj {p}: {p0_fn(th, np.array([p]))[0]:.0%}" for p in (3, 5, 10, 20, 40, 70)))
    score(load(2025, range(11, 18)), thetas, "2025 wk 11-17 (held out)")
    score(load(2026, range(1, 5)), thetas, "2026 wk 1-4 (held out)")
    score(load(2024, range(4, 18)), thetas, "2024 wk 4-17 (held out)")


if __name__ == "__main__":
    main()
