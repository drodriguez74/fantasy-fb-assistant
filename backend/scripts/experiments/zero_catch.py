"""Zero-catch games for receivers (2026-10-07 fix for overconfident low lines).

Finding that prompted it: on very low receiving-yard lines (goblins) the
shipped yardage model was overconfident for low-volume receivers. Receivers
projected for 1-2 catches cleared a line at 20% of their projection 66% of
the time; the model said 84%. Real zero-catch games (26% for 1.5-2.5
projected catches) are far more common than a Poisson count implies, and the
gamma yardage model has no zero mass at all.

Candidate fix: P(0 catches) as a logistic function of log(projected
receptions), fitted on 2025 wk 4-10. Receiving yards are 0 with that
probability (else gamma with the mean scaled up so the overall mean is
unchanged); receptions get the same zero mass (zero-inflated Poisson, mean
preserved). Scored out of sample on 2025 wk 11-17, 2026 wk 1-4 and 2024 wk
4-17: Brier of P(over) at lines from 20% to 120% of the projection, by
projected-catch bucket, vs the shipped model.

    cd backend && source venv/bin/activate
    python scripts/experiments/zero_catch.py
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
N = 3000


def load(season, weeks):
    rows = []
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
            if (r.get("player") or {}).get("position") not in ("WR", "TE", "RB"):
                continue
            prec, pyd = float(st.get("rec") or 0), float(st.get("rec_yd") or 0)
            s = sm.get(r.get("player_id"))
            if prec < 0.5 or pyd < 5 or not s or not (s.get("stats") or {}).get("gp"):
                continue
            a = s["stats"]
            rows.append((prec, pyd, float(a.get("rec") or 0), float(a.get("rec_yd") or 0)))
    return np.array(rows)


def p0_fn(theta, prec):
    a, b = theta
    return 1 / (1 + np.exp(-(a + b * np.log(prec))))


def fit_p0(rows):
    y = (rows[:, 2] == 0).astype(float)

    def nll(th):
        p = np.clip(p0_fn(th, rows[:, 0]), 1e-6, 1 - 1e-6)
        return -np.sum(y * np.log(p) + (1 - y) * np.log(1 - p))
    return minimize(nll, np.array([-1.0, -1.5]), method="Nelder-Mead").x


def sims(market, mean, p0, seed, n=N):
    """Shipped model when p0 is None, else the zero-catch version."""
    if p0 is None:
        return bm.simulate_stat(market, mean, seed, n=n)
    return bm.simulate_stat(market, mean, seed, n=n, p_zero=p0)


def score(rows, theta, label):
    print(f"\n{label}: n={len(rows)} player-weeks")
    p0 = p0_fn(theta, rows[:, 0])
    zero = rows[:, 2] == 0
    for lo, hi in ((0.5, 2), (2, 3), (3, 4), (4, 12)):
        sel = (rows[:, 0] >= lo) & (rows[:, 0] < hi)
        if sel.sum():
            print(f"  P(0 catches), proj {lo}-{hi}: real {zero[sel].mean():.1%}  fitted {p0[sel].mean():.1%}  n={sel.sum()}")
    for market, col_p, col_a in (("player_reception_yds", 1, 3), ("player_receptions", 0, 2)):
        res = {b: {"old": [], "new": [], "y": [], "pold": [], "pnew": []} for b in ("<3 catches", "3+ catches")}
        for i, r in enumerate(rows):
            b = "<3 catches" if r[0] < 3 else "3+ catches"
            old = sims(market, r[col_p], None, f"{market}|{i}")
            new = sims(market, r[col_p], float(p0[i]), f"{market}|{i}")
            for f in FRACS:
                line = np.floor(r[col_p] * f) + 0.5  # half-point lines, no pushes
                y = float(r[col_a] > line)
                po, pn = float((old > line).mean()), float((new > line).mean())
                d = res[b]
                d["old"].append((po - y) ** 2); d["new"].append((pn - y) ** 2)
                d["y"].append(y); d["pold"].append(po); d["pnew"].append(pn)
        for b, d in res.items():
            if not d["y"]:
                continue
            diff = np.array(d["new"]) - np.array(d["old"])
            rng = np.random.default_rng(1)
            # resample player-weeks (6 lines each) to respect clustering
            k = len(diff) // len(FRACS)
            blocks = diff[: k * len(FRACS)].reshape(k, len(FRACS)).mean(1)
            boots = [blocks[rng.integers(0, k, k)].mean() for _ in range(2000)]
            lo_, hi_ = np.percentile(boots, [2.5, 97.5])
            print(f"  {market:22} {b:11} lines={len(diff):5d}  real {np.mean(d['y']):.1%}  shipped {np.mean(d['pold']):.1%}"
                  f"  new {np.mean(d['pnew']):.1%}  Brier diff {diff.mean():+.4f} [{lo_:+.4f}, {hi_:+.4f}]")
        # the goblin region specifically: lines at 20-40% of projection, low volume
        d = res["<3 catches"]
        if d["y"]:
            idx = [j for j in range(len(d["y"])) if FRACS[j % len(FRACS)] <= 0.4]
            print(f"  {market:22} <3 catches, lines at 20-40% of proj: real {np.mean([d['y'][j] for j in idx]):.1%}"
                  f"  shipped {np.mean([d['pold'][j] for j in idx]):.1%}  new {np.mean([d['pnew'][j] for j in idx]):.1%}")


def main():
    fit = load(2025, range(4, 11))
    theta = fit_p0(fit)
    print(f"fit on 2025 wk 4-10 (n={len(fit)}): P(0 catches) = logistic({theta[0]:.4f} + {theta[1]:.4f} * ln(projected receptions))")
    for r in (1, 1.5, 2, 3, 4, 6):
        print(f"  projected {r}: {p0_fn(theta, np.array([r]))[0]:.1%}")
    score(load(2025, range(11, 18)), theta, "2025 wk 11-17 (held out)")
    score(load(2026, range(1, 5)), theta, "2026 wk 1-4 (held out)")
    score(load(2024, range(4, 18)), theta, "2024 wk 4-17 (held out)")


if __name__ == "__main__":
    main()
