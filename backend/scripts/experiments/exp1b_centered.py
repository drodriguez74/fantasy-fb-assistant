"""Experiment 1b: key-number margin shape (model C of exp1) CENTERED ON THE
MARKET, the way production would use it: the shape is fitted on
2015-2024, the location is solved per game so the favorite's no-push
cover probability equals the de-vigged closing price. Compared with the
shipped rounded N(line, 13.5) (which ignores the price) and with a
price-centered normal. Scored on 2025 + 2026 wk1-4.

    python scripts/experiments/exp1b_centered.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from exp1_distribution import KEY_M, KM, binned_normal, fit, logloss, m_dist_B, m_dist_C, rps  # noqa: E402
from gl_common import boot_ci, load  # noqa: E402


def shape_pmf(kind, theta, mu, t):
    if kind == "normal":
        return binned_normal(KM, [mu], [13.5])[0]
    th = theta.copy()
    th[0], th[1] = mu, 0.0                       # location given directly
    return m_dist_C(th, np.array([0.0]), np.array([t]))[0]


def cover_prob(p, s):
    win, loss = p[KM > s].sum(), p[KM < s].sum()
    return win / (win + loss)


def centered(kind, theta, s, t, q):
    lo, hi = s - 8, s + 8
    for _ in range(40):
        mid = (lo + hi) / 2
        if cover_prob(shape_pmf(kind, theta, mid, t), s) < q:
            lo = mid
        else:
            hi = mid
    return shape_pmf(kind, theta, (lo + hi) / 2, t)


def main():
    d = load()
    f, o = d[d.fit], d[d.oos]
    sg = lambda df: np.where(df.spread_line >= 0, 1, -1)  # noqa: E731
    sF, tF, xF = np.abs(f.spread_line.values), f.total_line.values, (f.margin * sg(f)).values
    thB = fit(m_dist_B, np.array([0, 1, np.log(13.5), 0]), sF, tF, xF, KM)
    thC = fit(m_dist_C, np.r_[thB, np.zeros(KEY_M)], sF, tF, xF, KM, l2=0.5)
    s, t, x = np.abs(o.spread_line.values), o.total_line.values, (o.margin * sg(o)).values
    q = np.where(o.spread_line.values >= 0, o.mkt_home.values, 1 - o.mkt_home.values)  # fav de-vigged cover prob
    dists = {
        "A shipped N(line,13.5)": binned_normal(KM, s, np.full(len(s), 13.5)),
        "A' N centered on price": np.array([centered("normal", None, s[i], t[i], q[i]) for i in range(len(s))]),
        "C' key-number, centered on price": np.array([centered("C", thC, s[i], t[i], q[i]) for i in range(len(s))]),
    }
    base = list(dists.values())[0]
    bl, br = logloss(base, KM, x), rps(base, KM, x, s)
    print(f"OOS n={len(x)}; diff vs shipped, 95% paired bootstrap CI")
    for k, p in dists.items():
        ll, r = logloss(p, KM, x), rps(p, KM, x, s)
        print(f"  {k:34} logloss {ll.mean():.4f} diff {np.mean(ll - bl):+.4f} {tuple(round(v, 4) for v in boot_ci(ll - bl))}"
              f" | RPS(line+-14) {r.mean():.5f} diff {np.mean(r - br):+.5f} {tuple(round(v, 5) for v in boot_ci(r - br))}")
    # Cover-probability Brier at alternate lines one half point and one point either side of the close.
    print("\nBrier of P(fav covers L) for L = close +-0.5, +-1 (pushes excluded), OOS")
    for off in (-1, -0.5, 0.5, 1):
        L = s + off
        res = {}
        for k, p in dists.items():
            pw = np.array([p[i][KM > L[i]].sum() for i in range(len(L))])
            pl = np.array([p[i][KM < L[i]].sum() for i in range(len(L))])
            keep = x != L
            y = (x > L)[keep]
            res[k] = (pw / (pw + pl))[keep]
        ys = y
        b0 = (res["A shipped N(line,13.5)"] - ys) ** 2
        txt = []
        for k, pr in res.items():
            b = (pr - ys) ** 2
            txt.append(f"{k.split()[0]} {b.mean():.4f} ({np.mean(b - b0):+.4f} {tuple(round(v, 4) for v in boot_ci(b - b0))})")
        print(f"  close{off:+}: n={keep.sum()}  " + "  ".join(txt))

    print("\nHalf-point value when the market is a pick'em-priced favorite -3 (no-push cover 50%), total 44")
    for kind in ("normal", "C"):
        p = centered(kind, thC, 3.0, 44.0, 0.5)
        print(f"  {kind:6}: P(margin==3) {p[KM == 3].sum():.1%}; fav -2.5 wins {p[KM > 2.5].sum():.1%};"
              f" dog +3.5 wins {p[KM < 3.5].sum():.1%}; fav -3.5 wins {p[KM > 3.5].sum():.1%}")
        p = centered(kind, thC, 7.0, 44.0, 0.5)
        print(f"  {kind:6}: P(margin==7) {p[KM == 7].sum():.1%}; fav -6.5 wins {p[KM > 6.5].sum():.1%};"
              f" dog +7.5 wins {p[KM < 7.5].sum():.1%}")
        p = centered(kind, thC, 3.5, 44.0, 0.5)
        print(f"  {kind:6}: consensus -3.5 at 50%: fav -3 win/push {p[KM > 3].sum():.1%}/{p[KM == 3].sum():.1%};"
              f" dog +3 win/push {p[KM < 3].sum():.1%}/{p[KM == 3].sum():.1%}")
        p = centered(kind, thC, 2.5, 44.0, 0.5)
        print(f"  {kind:6}: consensus -2.5 at 50%: dog +3 win/push {p[KM < 3].sum():.1%}/{p[KM == 3].sum():.1%};"
              f" fav -3 win/push {p[KM > 3].sum():.1%}/{p[KM == 3].sum():.1%}")


if __name__ == "__main__":
    main()
