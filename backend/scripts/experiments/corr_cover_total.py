"""Measure COVER_TOTAL_RHO from closing lines (nflverse games.csv).

betting_model.simulate_game_joint draws (favorite margin, total) as a
bivariate normal with correlation COVER_TOTAL_RHO (0.15). The matching
empirical quantity is the correlation between the favorite's margin error
(margin - closing spread) and the total error (total - closing total). Also
reported: phi / tetrachoric correlation of the binary outcomes (favorite
covers, game goes over), by spread bucket, with game-bootstrap 95% CIs, and
the effect on the four combo probabilities vs the shipped 0.15.

    python scripts/experiments/corr_cover_total.py [--from 2015 --to 2025]
"""
import argparse
import csv
import os
import sys

import numpy as np
from scipy.stats import multivariate_normal, norm

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.services import betting_model as bm  # noqa: E402

CACHE = os.path.join(os.path.dirname(__file__), "..", "..", ".cache", "backtest")
RNG = np.random.default_rng(11)
B = 2000


def load(lo, hi, include_post=True):
    out = []
    with open(os.path.join(CACHE, "nflverse_games.csv")) as f:
        for r in csv.DictReader(f):
            if not (lo <= int(r["season"]) <= hi) or not r["result"] or not r["spread_line"] or not r["total_line"]:
                continue
            if r["game_type"] != "REG" and not include_post:
                continue
            spread = float(r["spread_line"])  # home favored by spread_line
            if spread == 0:
                continue
            home_margin = float(r["result"])
            fav_margin = home_margin if spread > 0 else -home_margin
            out.append({"season": int(r["season"]), "spread": abs(spread), "total_line": float(r["total_line"]),
                        "fav_err": fav_margin - abs(spread), "tot_err": float(r["total"]) - float(r["total_line"])})
    return out


def tetrachoric(x, y):
    """Latent normal correlation reproducing the observed 2x2 table (x, y in {0,1})."""
    px, py, pxy = x.mean(), y.mean(), (x & y).mean()
    a, b = norm.ppf(px), norm.ppf(py)
    lo, hi = -0.99, 0.99
    for _ in range(40):
        mid = (lo + hi) / 2
        if multivariate_normal.cdf([a, b], cov=[[1, mid], [mid, 1]]) < pxy:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def stats(rows, boot=True):
    fe = np.array([r["fav_err"] for r in rows])
    te = np.array([r["tot_err"] for r in rows])
    keep = (fe != 0) & (te != 0)  # pushes out of the binary measures
    cov, ov = fe[keep] > 0, te[keep] > 0

    def point(fe, te, cov, ov):
        return np.corrcoef(fe, te)[0, 1], np.corrcoef(cov, ov)[0, 1]

    pear, phi = point(fe, te, cov, ov)
    res = {"n": len(rows), "pearson": pear, "phi": phi, "tetra": tetrachoric(cov, ov),
           "p_cov_over": (cov & ov).mean(), "p_cov": cov.mean(), "p_over": ov.mean()}
    if boot:
        bs = []
        n = len(fe)
        for _ in range(B):
            i = RNG.integers(0, n, n)
            k = keep[i]
            bs.append(point(fe[i], te[i], (fe[i] > 0)[k], (te[i] > 0)[k]))
        bs = np.array(bs)
        res["pearson_ci"] = np.percentile(bs[:, 0], [2.5, 97.5])
        res["phi_ci"] = np.percentile(bs[:, 1], [2.5, 97.5])
    return res


def combo_probs(rho):
    """P(fav covers & over) etc. for a pick'em-centred game at the shipped SDs."""
    return bm.joint_prob(0.5, 0.5, rho)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="lo", type=int, default=2015)
    ap.add_argument("--to", dest="hi", type=int, default=2025)
    a = ap.parse_args()
    rows = load(a.lo, a.hi)
    s = stats(rows)
    print(f"Seasons {a.lo}-{a.hi}, REG+POST, non-pick'em games: n={s['n']}")
    print(f"  Pearson(fav margin err, total err) = {s['pearson']:+.3f}  95% CI [{s['pearson_ci'][0]:+.3f}, {s['pearson_ci'][1]:+.3f}]"
          "   <- the quantity simulate_game_joint's rho represents")
    print(f"  phi(fav covers, over)              = {s['phi']:+.3f}  95% CI [{s['phi_ci'][0]:+.3f}, {s['phi_ci'][1]:+.3f}]")
    print(f"  tetrachoric (latent) rho           = {s['tetra']:+.3f}")
    print(f"  P(cover)={s['p_cov']:.3f} P(over)={s['p_over']:.3f} P(cover&over)={s['p_cov_over']:.3f}")
    print("\nBy spread size (favorite's points):")
    for lo, hi in ((0.5, 3), (3.5, 6.5), (7, 9.5), (10, 30)):
        sub = [r for r in rows if lo <= r["spread"] <= hi]
        t = stats(sub)
        print(f"  {lo:>4}-{hi:<4} n={t['n']:4}  pearson {t['pearson']:+.3f} [{t['pearson_ci'][0]:+.3f},{t['pearson_ci'][1]:+.3f}]"
              f"  phi {t['phi']:+.3f} [{t['phi_ci'][0]:+.3f},{t['phi_ci'][1]:+.3f}]  tetra {t['tetra']:+.3f}")
    print("\nBy era:")
    for lo, hi in ((2015, 2019), (2020, 2025)):
        t = stats([r for r in rows if lo <= r["season"] <= hi])
        print(f"  {lo}-{hi} n={t['n']:4}  pearson {t['pearson']:+.3f} [{t['pearson_ci'][0]:+.3f},{t['pearson_ci'][1]:+.3f}]"
              f"  phi {t['phi']:+.3f} [{t['phi_ci'][0]:+.3f},{t['phi_ci'][1]:+.3f}]")

    print("\nImpact on a 50/50 game's combos (P(fav cover & Over) = P(dog cover & Under); other two = 0.5 - that):")
    for label, rho in (("independent", 0.0), ("shipped 0.15", bm.COVER_TOTAL_RHO), ("measured", s["pearson"]),
                       ("CI low", s["pearson_ci"][0]), ("CI high", s["pearson_ci"][1])):
        p = combo_probs(rho)
        # fair odds and EV at a typical SGP price of +260 for a 2-leg -110 parlay
        ev = p * 3.6 - 1
        print(f"  {label:13} rho={rho:+.3f}  fav&Over {p:.4f} (fair {bm.fair_american(p):+d})  fav&Under {0.5 - p:.4f}"
              f" (fair {bm.fair_american(0.5 - p):+d})  EV@+260 fav&Over {ev:+.3%}")


if __name__ == "__main__":
    main()
