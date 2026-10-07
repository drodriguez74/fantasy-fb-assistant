"""Hit probability / EV of typical PrizePicks Power entries at ~55% legs under
the shipped LEG_CORRELATION vs the correlations measured by corr_props.py.

Exact Gaussian-copula orthant probabilities (scipy), no simulation noise.

    python scripts/experiments/corr_impact.py   (run corr_props.py first)
"""
import json
import os
import sys

import numpy as np
from scipy.stats import multivariate_normal, norm

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.services import betting_model as bm  # noqa: E402

CACHE = os.path.join(os.path.dirname(__file__), "..", "..", ".cache", "backtest")
M = json.load(open(os.path.join(CACHE, "corr_props_results.json")))


def rho(label):
    return M[label]["rho"]


def p_all(ps, corr):
    t = norm.ppf(ps)
    if len(ps) == 1:
        return ps[0]
    return float(multivariate_normal(mean=np.zeros(len(ps)), cov=corr, allow_singular=True).cdf(t))


def corr_mat(n, pairs):
    c = np.eye(n)
    for (i, j), r in pairs.items():
        c[i, j] = c[j, i] = r
    return c


QBQB, QBWRo, WRWRo, RBRBo = ("QB pass yds  ~ opp QB pass yds", "QB pass yds  ~ opp WR/TE rec yds",
                             "WR/TE rec yds ~ opp WR/TE rec yds", "RB rush yds  ~ opp RB rush yds")
QBWRt = "QB pass yds  ~ own WR/TE rec yds"
S = bm.LEG_CORRELATION
P, R, Y = bm._PASS, bm._RUSH, bm._REC_YDS

# (description, n legs, {pair: (shipped-as-coded rho, measured rho)}) -- signs already for the sides chosen
CASES = [
    ("2-pick, different games (baseline)", 2, {}),
    ("2-pick QB More / opp QB More", 2, {(0, 1): (S[(P, P, False)], rho(QBQB))}),
    ("2-pick QB More / opp QB Less", 2, {(0, 1): (-S[(P, P, False)], -rho(QBQB))}),
    ("2-pick QB More / opp WR More", 2, {(0, 1): (S[(P, Y, False)], rho(QBWRo))}),
    ("2-pick WR More / opp WR More", 2, {(0, 1): (S[(Y, Y, False)], rho(WRWRo))}),
    ("2-pick RB More / opp RB More", 2, {(0, 1): (0.0, rho(RBRBo))}),
    ("2-pick RB More / opp RB Less", 2, {(0, 1): (0.0, -rho(RBRBo))}),
    ("3-pick QB More + own WR More + other game (code treats teammates as 0)", 3, {(0, 1): (0.0, rho(QBWRt))}),
    ("3-pick QB Less + own WR Less + other game", 3, {(0, 1): (0.0, rho(QBWRt))}),
    ("3-pick QB More + own WR Less + other game", 3, {(0, 1): (0.0, -rho(QBWRt))}),
    ("3-pick QB_A More, QB_B More, WR_B More (shootout stack)", 3,
     {(0, 1): (S[(P, P, False)], rho(QBQB)), (0, 2): (S[(P, Y, False)], rho(QBWRo)), (1, 2): (0.0, rho(QBWRt))}),
    ("3-pick three opposing-game legs WR/WR/QB More", 3,
     {(0, 1): (S[(Y, Y, False)], rho(WRWRo)), (0, 2): (S[(P, Y, False)], rho(QBWRo)), (1, 2): (S[(P, Y, False)], rho(QBWRo))}),
]


def main():
    for p_leg in (0.55, 0.58):
        print(f"\nLegs at {p_leg:.0%} each; Power payouts 2-pick {bm.POWER_PAYOUTS[2]}x, 3-pick {bm.POWER_PAYOUTS[3]}x")
        print(f"{'entry':72} {'indep':>7} {'shipped':>8} {'measured':>9}   EV shipped -> measured")
        for label, n, pairs in CASES:
            ps = [p_leg] * n
            pay = bm.POWER_PAYOUTS[n]
            ind = p_all(ps, np.eye(n))
            sh = p_all(ps, corr_mat(n, {k: v[0] for k, v in pairs.items()}))
            me = p_all(ps, corr_mat(n, {k: v[1] for k, v in pairs.items()}))
            print(f"{label:72} {ind:7.4f} {sh:8.4f} {me:9.4f}   {sh * pay - 1:+.1%} -> {me * pay - 1:+.1%}")


if __name__ == "__main__":
    main()
