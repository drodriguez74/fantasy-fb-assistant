"""Experiment 1: is the rounded-normal margin/total distribution mispricing
key numbers? Fits alternatives on 2015-2024 and scores them on 2025 +
2026 wk1-4 (out-of-sample), against the realized margin/total.

    python scripts/experiments/exp1_distribution.py

Models (favorite's margin x given favorite spread s and total t; total
points y given total line t):
  A  rounded N(line, 13.5 / 13.0)                     -- shipped
  B  rounded N(a + b*line, sigma(t)) fitted           -- same shape, fitted scale
  C  B x exp(beta_k) key-number weights, fitted MLE   -- proposed
  D  kernel-weighted empirical histogram (+5% B)      -- nonparametric
  E  score composition 7*Pois(TD) + 3*Pois(FG) per team (Skellam-like)
Scores: mean log-loss of the exact result, RPS over the betting-relevant
CDF thresholds (line +-14 points), paired bootstrap CI of the difference
vs A, push calibration, and the value of a half point at key numbers.
"""
import sys

import numpy as np
from scipy.optimize import minimize
from scipy.stats import norm, poisson

sys.path.insert(0, __import__("os").path.dirname(__file__))
from gl_common import boot_ci, load, wilson  # noqa: E402

KM = np.arange(-70, 71)          # margin support
KT = np.arange(0, 121)           # total support
KEY_M = 26                       # beta for |k| = 0..25
KEY_T = (20, 76)                 # beta for totals 20..75


def binned_normal(K, mu, sd):
    mu, sd = np.asarray(mu, float)[:, None], np.asarray(sd, float)[:, None]
    p = norm.cdf((K[None] + 0.5 - mu) / sd) - norm.cdf((K[None] - 0.5 - mu) / sd)
    return p / p.sum(1, keepdims=True)


# ---------------- margin models ----------------

def m_params(theta, s, t):
    a, b, c0, c1 = theta[:4]
    return a + b * s, np.exp(c0 + c1 * (t - 44) / 10)


def m_dist_B(theta, s, t):
    mu, sd = m_params(theta, s, t)
    return binned_normal(KM, mu, sd)


def m_dist_C(theta, s, t):
    p = m_dist_B(theta, s, t)
    beta = np.zeros(len(KM))
    ab = np.abs(KM)
    sel = ab < KEY_M
    beta[sel] = theta[4:][ab[sel]]
    p = p * np.exp(beta)[None]
    return p / p.sum(1, keepdims=True)


def fit(dist_fn, theta0, s, t, x, K, l2=0.0, l2_from=4):
    idx = np.searchsorted(K, x)

    def nll(th):
        p = dist_fn(th, s, t)
        return -np.log(p[np.arange(len(x)), idx] + 1e-12).sum() + l2 * np.sum(th[l2_from:] ** 2)

    r = minimize(nll, theta0, method="L-BFGS-B")
    return r.x


def kernel_dist(K, train_v, train_s, train_t, s, t, hs, ht, base):
    out = np.zeros((len(s), len(K)))
    idx = np.searchsorted(K, train_v)
    for i in range(len(s)):
        w = np.exp(-0.5 * ((train_s - s[i]) / hs) ** 2 - 0.5 * ((train_t - t[i]) / ht) ** 2)
        h = np.bincount(idx, weights=w, minlength=len(K))
        out[i] = 0.95 * h / h.sum() + 0.05 * base[i]
    return out


def team_score_pmf(mean, fg_rate=0.078):
    """7*Pois(TD) + 3*Pois(FG): FGs per point from 2015-24 (~1.7 per 22 pts)."""
    lf = fg_rate * mean
    lt = np.maximum(mean - 3 * lf, 0.1) / 7
    pmf = np.zeros(121)
    for td in range(15):
        for fg in range(15):
            v = 7 * td + 3 * fg
            if v <= 120:
                pmf[v] += poisson.pmf(td, lt) * poisson.pmf(fg, lf)
    return pmf / pmf.sum()


def comp_dists(s, t):
    pm, pt = np.zeros((len(s), len(KM))), np.zeros((len(s), len(KT)))
    for i in range(len(s)):
        fav, dog = team_score_pmf((t[i] + s[i]) / 2), team_score_pmf((t[i] - s[i]) / 2)
        diff = np.convolve(fav, dog[::-1])          # index j -> fav - dog = j - 120
        vals = np.arange(-120, 121)
        sel = (vals >= KM[0]) & (vals <= KM[-1])
        pm[i] = diff[sel] / diff[sel].sum()
        tot = np.convolve(fav, dog)[:len(KT)]
        pt[i] = tot / tot.sum()
    return pm, pt


# ---------------- total models ----------------

def t_dist_B(theta, line, _):
    a, b, c0, c1 = theta[:4]
    return binned_normal(KT, a + b * line, np.exp(c0 + c1 * (line - 44) / 10))


def t_dist_C(theta, line, _):
    p = t_dist_B(theta, line, None)
    beta = np.zeros(len(KT))
    beta[KEY_T[0]:KEY_T[1]] = theta[4:]
    p = p * np.exp(beta)[None]
    return p / p.sum(1, keepdims=True)


# ---------------- scoring ----------------

def logloss(p, K, v):
    return -np.log(p[np.arange(len(v)), np.searchsorted(K, v)] + 1e-12)


def rps(p, K, v, center, width=14):
    cdf = np.cumsum(p, 1)
    out = np.zeros(len(v))
    for i in range(len(v)):
        j = (K >= center[i] - width) & (K <= center[i] + width)
        out[i] = np.mean((cdf[i, j] - (v[i] <= K[j])) ** 2)
    return out


def compare(name, dists, K, v, center):
    base_ll, base_rps = logloss(dists["A"], K, v), rps(dists["A"], K, v, center)
    print(f"\n{name}: OOS n={len(v)} (lower is better; diff = model - A, 95% paired bootstrap CI)")
    for k, p in dists.items():
        ll, r = logloss(p, K, v), rps(p, K, v, center)
        dll, dr = ll - base_ll, r - base_rps
        lo1, hi1 = boot_ci(dll)
        lo2, hi2 = boot_ci(dr)
        print(f"  {k}: logloss {ll.mean():.4f} (diff {dll.mean():+.4f} [{lo1:+.4f},{hi1:+.4f}])"
              f"   RPS {r.mean():.5f} (diff {dr.mean():+.5f} [{lo2:+.5f},{hi2:+.5f}])")


def ev110(p_win, p_push):
    return p_win * (100 / 110) - (1 - p_win - p_push)


def main():
    d = load()
    fit_d, oos = d[d.fit], d[d.oos]
    sign = lambda df: np.where(df.spread_line >= 0, 1, -1)  # noqa: E731
    sF, tF, xF = np.abs(fit_d.spread_line.values), fit_d.total_line.values, (fit_d.margin * sign(fit_d)).values
    sO, tO, xO = np.abs(oos.spread_line.values), oos.total_line.values, (oos.margin * sign(oos)).values
    yF, yO = fit_d.points.values, oos.points.values
    print(f"fit games {len(fit_d)} (2015-2024), OOS games {len(oos)} (2025 REG + 2026 wk1-4)")

    # ---- margins
    thB = fit(m_dist_B, np.array([0, 1, np.log(13.5), 0]), sF, tF, xF, KM)
    thC = fit(m_dist_C, np.r_[thB, np.zeros(KEY_M)], sF, tF, xF, KM, l2=0.5)
    print(f"Margin B: mean = {thB[0]:+.2f} + {thB[1]:.3f}*s, sd = {np.exp(thB[2]):.2f} * exp({thB[3]:+.3f} per 10 pts of total)")
    print(f"Margin C: sd at t=44 {np.exp(thC[2]):.2f}; key weights exp(beta): " +
          ", ".join(f"{k}:{np.exp(thC[4 + k]):.2f}" for k in (0, 1, 2, 3, 4, 6, 7, 8, 10, 14, 17, 21)))
    dm = {"A": binned_normal(KM, sO, np.full(len(sO), 13.5)), "B": m_dist_B(thB, sO, tO), "C": m_dist_C(thC, sO, tO)}
    dm["D"] = kernel_dist(KM, xF, sF, tF, sO, tO, 1.0, 4.0, dm["B"])
    pmE, ptE = comp_dists(sO, tO)
    dm["E"] = pmE
    compare("MARGIN (favorite perspective)", dm, KM, xO, sO)

    # Push calibration on whole-number spreads + landing frequencies.
    print("\nLanding on key margins (|fav margin| == k): predicted vs actual")
    for label, S, T, X in (("fit 2015-24 (in-sample for C)", sF, tF, xF), ("OOS 2025-26", sO, tO, xO)):
        pa = binned_normal(KM, S, np.full(len(S), 13.5))
        pc = m_dist_C(thC, S, T)
        for k in (3, 7, 10, 6, 14, 4, 1):
            m = np.isin(KM, [k, -k])
            act = np.isin(X, [k, -k])
            ci = wilson(act.sum(), len(X))
            print(f"  {label:30} |x|={k:2}: A {pa[:, m].sum(1).mean():.1%}  C {pc[:, m].sum(1).mean():.1%}"
                  f"  actual {act.mean():.1%} [{ci[0]:.1%},{ci[1]:.1%}] (n={len(X)})")
    print("\nPush rate at the closing spread (whole-number spreads only)")
    for label, S, T, X in (("fit 2015-24", sF, tF, xF), ("OOS 2025-26", sO, tO, xO)):
        w = (S == np.round(S)) & (S > 0)
        pa = binned_normal(KM, S[w], np.full(w.sum(), 13.5))
        pc = m_dist_C(thC, S[w], T[w])
        idx = np.searchsorted(KM, S[w])
        act = X[w] == S[w]
        ci = wilson(act.sum(), w.sum())
        print(f"  {label:12} n={w.sum():4}: A {pa[np.arange(w.sum()), idx].mean():.1%}  C {pc[np.arange(w.sum()), idx].mean():.1%}"
              f"  actual {act.mean():.1%} [{ci[0]:.1%},{ci[1]:.1%}]")
        for k in (3, 7):
            wk = w & (S == k)
            if wk.sum():
                a2 = (X[wk] == k)
                ci = wilson(a2.sum(), wk.sum())
                pck = m_dist_C(thC, S[wk], T[wk])[:, np.searchsorted(KM, k)].mean()
                pak = binned_normal(KM, S[wk], np.full(wk.sum(), 13.5))[:, np.searchsorted(KM, k)].mean()
                print(f"     spread {k}: n={wk.sum():3} A {pak:.1%} C {pck:.1%} actual {a2.mean():.1%} [{ci[0]:.1%},{ci[1]:.1%}]")

    print("\nValue of a half point at -110 (consensus favorite spread s, total 44): P(fav covers L), P(push)")
    print("   s    L   | A: win  push  EV@-110 | C: win  push  EV@-110")
    for s0, Ls in ((3, (2.5, 3, 3.5)), (7, (6.5, 7, 7.5)), (2.5, (2.5, 3)), (3.5, (3, 3.5)), (6.5, (6.5, 7)), (7.5, (7, 7.5)),
                   (10, (9.5, 10, 10.5))):
        pa = binned_normal(KM, [s0], [13.5])[0]
        pc = m_dist_C(thC, np.array([s0]), np.array([44.0]))[0]
        for L in Ls:
            for side in ("fav", "dog"):
                if side == "dog" and L != Ls[-1]:
                    continue
                if side == "fav":
                    wa, wc = pa[KM > L].sum(), pc[KM > L].sum()
                else:
                    wa, wc = pa[KM < L].sum(), pc[KM < L].sum()
                qa, qc = (pa[KM == L].sum(), pc[KM == L].sum())
                lab = f"-{L:g}" if side == "fav" else f"+{L:g}"
                print(f"  {s0:4g} {lab:6}| {wa:6.1%} {qa:5.1%} {ev110(wa, qa):+6.1%} | {wc:6.1%} {qc:5.1%} {ev110(wc, qc):+6.1%}")
    # empirical half-point value OOS and fit
    for label, S, X in (("fit 2015-24", sF, xF), ("OOS 2025-26", sO, xO)):
        near3 = (S >= 2.5) & (S <= 3.5)
        near7 = (S >= 6.5) & (S <= 7.5)
        for k, m in ((3, near3), (7, near7)):
            a = (X[m] == k)
            ci = wilson(a.sum(), m.sum())
            print(f"  {label}: fav spread {k - 0.5}-{k + 0.5}, fav wins by exactly {k}: {a.mean():.1%} [{ci[0]:.1%},{ci[1]:.1%}] n={m.sum()}"
                  f"  (A says {binned_normal(KM, S[m], np.full(m.sum(), 13.5))[:, np.searchsorted(KM, k)].mean():.1%})")

    # ---- totals
    tbB = fit(t_dist_B, np.array([0, 1, np.log(13), 0]), tF, None, yF, KT)
    tbC = fit(t_dist_C, np.r_[tbB, np.zeros(KEY_T[1] - KEY_T[0])], tF, None, yF, KT, l2=3.0)
    print(f"\nTotal B: mean = {tbB[0]:+.2f} + {tbB[1]:.3f}*t, sd at 44 = {np.exp(tbB[2]):.2f} * exp({tbB[3]:+.3f}/10pts)")
    print("Total C key weights exp(beta): " + ", ".join(f"{k}:{np.exp(tbC[4 + k - KEY_T[0]]):.2f}"
                                                       for k in (30, 33, 34, 37, 40, 41, 43, 44, 45, 47, 48, 51, 54, 55)))
    dt = {"A": binned_normal(KT, tO, np.full(len(tO), 13.0)), "B": t_dist_B(tbB, tO, None), "C": t_dist_C(tbC, tO, None)}
    dt["D"] = kernel_dist(KT, yF, tF, tF, tO, tO, 1.5, 1e9, dt["B"])
    dt["E"] = ptE
    compare("TOTAL POINTS", dt, KT, yO, tO)
    print("\nPush rate at the closing total (whole-number totals) and landing on key totals")
    for label, T, Y in (("fit 2015-24", tF, yF), ("OOS 2025-26", tO, yO)):
        w = T == np.round(T)
        idx = np.searchsorted(KT, T[w])
        pa = binned_normal(KT, T[w], np.full(w.sum(), 13.0))[np.arange(w.sum()), idx].mean()
        pc = t_dist_C(tbC, T[w], None)[np.arange(w.sum()), idx].mean()
        act = Y[w] == T[w]
        ci = wilson(act.sum(), w.sum())
        print(f"  {label:12} n={w.sum():4}: A {pa:.1%}  C {pc:.1%}  actual {act.mean():.1%} [{ci[0]:.1%},{ci[1]:.1%}]")
    # totals near key numbers: actual frequency of exactly k when line within 3 of k
    for k in (37, 41, 44, 47, 51):
        m = np.abs(tF - k) <= 3
        a = (yF[m] == k).mean()
        pa = binned_normal(KT, tF[m], np.full(m.sum(), 13.0))[:, np.searchsorted(KT, k)].mean()
        print(f"  fit: lines within 3 of {k}: exactly {k} {a:.1%} vs A {pa:.1%} (n={m.sum()})")


if __name__ == "__main__":
    main()
