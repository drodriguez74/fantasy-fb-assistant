"""Compare outcome-distribution families for NFL player props, out of sample.

    cd backend && source venv/bin/activate
    python scripts/experiments/props_dist_data.py      # build/cache cases (once)
    python scripts/experiments/props_dist_eval.py      # all methods, all splits
    python scripts/experiments/props_dist_eval.py --centered   # shape-only (median re-centered per test set)

Every method is fitted on 2025 weeks 4-10 only and scored, untouched, on
2025 weeks 11-17, 2026 weeks 1-4 and 2024 weeks 4-17. Each predictive
distribution is a (cases, S) sorted matrix of outcome quantiles/samples.

Scores per market:
- pinball loss, average over the 10th..90th percentiles (same as backtest_projections.py)
- calibration: share of randomized PIT values below .10/.25/.50/.75/.90
- P(over line) Brier score and bias (mean predicted - mean realized) for lines at
  r x projection: goblin r in {.5,.6,.7}, standard {.9,1.0,1.1}, demon {1.2,1.3,1.4}
  (half-point lines, so no pushes)
- paired cluster bootstrap 95% CIs (clusters = season-week-team) for every
  difference vs the current model.

--centered re-centers each method on each test set so its median PIT is 0.5
(an oracle stand-in for live slate centering, which sets the level from the
market each week); it isolates the shape question from projection level.
"""
import argparse
import os
import sys
import time
from collections import defaultdict

import numpy as np
from scipy import optimize, stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
import props_dist_data as D  # noqa: E402
import backtest_projections as bp  # noqa: E402
from app.services import betting_model as bm  # noqa: E402

S = 4000
UGRID = (np.arange(S) + 0.5) / S
DECILES = np.arange(1, 10) / 10
REGIONS = {"goblin": (0.5, 0.6, 0.7), "standard": (0.9, 1.0, 1.1), "demon": (1.2, 1.3, 1.4)}
REF = {"player_pass_yds": 240.0, "player_rush_yds": 60.0, "player_reception_yds": 60.0, "player_receptions": 4.0}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def arr(cases, k):
    return np.array([c[k] for c in cases], dtype=float)


def pos_dummies(market, cases):
    """Position indicators relative to the market's main position."""
    if market == "player_pass_yds":
        return np.zeros((len(cases), 0))
    base = "RB" if market == "player_rush_yds" else "WR"
    others = [p for p in ("RB", "WR", "TE", "QB") if p != base]
    if market != "player_rush_yds":
        others = [p for p in others if p != "QB"]
    return np.array([[1.0 if c["pos"] == p else 0.0 for p in others] for c in cases])


def role_feats(cases, means=None):
    X = np.column_stack([arr(cases, "snap_share"), arr(cases, "tgt_share")])
    if means is None:
        means = np.nanmean(X, axis=0)
    X = np.where(np.isnan(X), means, X)
    return X - means, means


def sim_current(market, proj, params, seed, scale=1.0):
    """betting_model.simulate_stat's structure (vectorized), S draws, sorted."""
    rng = np.random.default_rng(seed)
    m = (proj * params["level"] * scale)[:, None]
    tm = np.clip(m + params["proj_err"] * m * rng.standard_normal((len(proj), S)), 0.01, None)
    if market not in bm.YARDS_CV:
        return np.sort(rng.poisson(tm).astype(float), axis=1)
    mm = proj * params["level"] * scale
    cv = params["cv"] * (bm.YARDS_REF_MEAN[market] / np.maximum(mm, 1.0)) ** bm.VOLUME_EXPONENT
    cv = np.clip(cv, params["cv"] * 0.8, bm.MAX_YARDS_CV)[:, None]
    shape = 1 / cv ** 2
    out = rng.gamma(np.broadcast_to(shape, tm.shape), tm / shape)
    out = bm.apply_duds(out, tm, params.get("dud", 0.0), rng)
    return np.sort(out, axis=1)


def pit(M, a, rng):
    """Randomized PIT of actuals a under sorted sample rows M."""
    below = (M < a[:, None]).mean(1)
    eq = (M == a[:, None]).mean(1)
    return below + rng.random(len(a)) * eq


# ---------------------------------------------------------------------------
# Methods. Each: fit(market, train_cases) -> model; predict(model, cases, scale) -> sorted (n, S)
# ---------------------------------------------------------------------------

class Current:
    """Production settings; only the level is fitted (live, centering sets it)."""
    name = "current"

    def fit(self, market, tr):
        p = bp.current_params(market)
        proj, a = arr(tr, "proj"), arr(tr, "actual")
        best = None
        for lv in np.arange(0.80, 1.21, 0.01):
            q = sim_current(market, proj, {**p, "level": lv}, 5)[:, (DECILES * S).astype(int)]
            d = a[:, None] - q
            s = np.mean(np.maximum(DECILES * d, (DECILES - 1) * d))
            if best is None or s < best[0]:
                best = (s, lv)
        return {**p, "level": float(best[1])}

    def predict(self, market, model, cs, scale=1.0):
        return sim_current(market, arr(cs, "proj"), model, 11, scale)


class CurrentRefit(Current):
    """Same family, every knob refitted (what backtest_projections.py does)."""
    name = "current_refit"

    def fit(self, market, tr):
        bp.SIMS = 1500
        return bp.fit(market, tr)


class LogNormal:
    """log(X+1) ~ N(log(L*proj+1) + pos offset, s), s = exp(t0 + t1 log(proj/ref) [+ pos + role]),
    X <= 0 treated as censored. Fitted by maximum likelihood."""
    name = "lognormal"
    features = False

    def design(self, market, cs, fmeans=None):
        proj = arr(cs, "proj")
        lp = np.log(proj / REF[market])
        P = pos_dummies(market, cs)
        cols = [np.ones(len(cs)), lp]
        loc = [P] if P.shape[1] else []
        if self.features:
            R, fmeans = role_feats(cs, fmeans)
            cols = cols + [P[:, i] for i in range(P.shape[1])] + [R[:, 0], R[:, 1]]
        Z = np.column_stack(cols)
        Lc = np.column_stack(loc) if loc else np.zeros((len(cs), 0))
        return proj, Z, Lc, fmeans

    def unpack(self, th, Z, Lc):
        k = Z.shape[1]
        return th[0], th[1:1 + Lc.shape[1]], th[1 + Lc.shape[1]:1 + Lc.shape[1] + k]

    def mu_s(self, th, proj, Z, Lc, scale=1.0):
        loglev, b, g = self.unpack(th, Z, Lc)
        mu = np.log1p(proj * np.exp(loglev) * scale) + (Lc @ b if Lc.shape[1] else 0.0)
        s = np.exp(Z @ g)
        return mu, s

    def nll(self, th, proj, Z, Lc, a):
        mu, s = self.mu_s(th, proj, Z, Lc)
        y = np.log1p(np.maximum(a, 0))
        cens = a <= 0
        ll = np.where(cens, stats.norm.logcdf((0 - mu) / s), stats.norm.logpdf((y - mu) / s) - np.log(s))
        return -ll.sum()

    def fit(self, market, tr):
        proj, Z, Lc, fm = self.design(market, tr)
        th0 = np.zeros(1 + Lc.shape[1] + Z.shape[1])
        th0[1 + Lc.shape[1]] = np.log(0.5)
        r = optimize.minimize(self.nll, th0, args=(proj, Z, Lc, arr(tr, "actual")), method="BFGS")
        return {"th": r.x, "fmeans": fm}

    def predict(self, market, model, cs, scale=1.0):
        proj, Z, Lc, _ = self.design(market, cs, model["fmeans"])
        mu, s = self.mu_s(model["th"], proj, Z, Lc, scale)
        return np.maximum(np.expm1(mu[:, None] + s[:, None] * stats.norm.ppf(UGRID)[None, :]), 0.0)


class LogNormalFeat(LogNormal):
    """Lognormal with spread conditioned on projection size, position, lagged snap and target share."""
    name = "lognormal_feat"
    features = True


class LogNormalMix(LogNormal):
    """Two-component censored lognormal: normal game vs dud game (lower location,
    own spread), dud weight logistic in log(proj). Fitted by maximum likelihood."""
    name = "lognormal_mix"

    def nll(self, th, proj, Z, Lc, a):
        base = th[:-4]
        d, ls2, w0, w1 = th[-4:]
        mu, s = self.mu_s(base, proj, Z, Lc)
        mu2, s2 = mu + d, np.exp(ls2)
        pi = 1 / (1 + np.exp(-(w0 + w1 * np.log(proj / 60.0))))
        y = np.log1p(np.maximum(a, 0))
        cens = a <= 0

        def comp(m, sd):
            return np.where(cens, stats.norm.logcdf(-m / sd), stats.norm.logpdf((y - m) / sd) - np.log(sd))
        ll = np.logaddexp(np.log1p(-pi) + comp(mu, s), np.log(pi) + comp(mu2, s2))
        return -ll.sum()

    def fit(self, market, tr):
        proj, Z, Lc, fm = self.design(market, tr)
        th0 = np.zeros(1 + Lc.shape[1] + Z.shape[1])
        th0[1 + Lc.shape[1]] = np.log(0.4)
        best = None
        for d0 in (-1.5, -2.5):
            x0 = np.concatenate([th0, [d0, np.log(1.0), -2.5, 0.0]])
            r = optimize.minimize(self.nll, x0, args=(proj, Z, Lc, arr(tr, "actual")), method="Nelder-Mead",
                                  options={"maxiter": 20000, "maxfev": 20000, "xatol": 1e-5, "fatol": 1e-4})
            r = optimize.minimize(self.nll, r.x, args=(proj, Z, Lc, arr(tr, "actual")), method="BFGS")
            if best is None or r.fun < best.fun:
                best = r
        return {"th": best.x, "fmeans": fm}

    def predict(self, market, model, cs, scale=1.0):
        th = model["th"]
        proj, Z, Lc, _ = self.design(market, cs, model["fmeans"])
        mu, s = self.mu_s(th[:-4], proj, Z, Lc, scale)
        d, ls2, w0, w1 = th[-4:]
        pi = 1 / (1 + np.exp(-(w0 + w1 * np.log(proj * scale / 60.0))))
        rng = np.random.default_rng(13)
        dud = rng.random((len(cs), S)) < pi[:, None]
        z = rng.standard_normal((len(cs), S))
        out = np.where(dud, mu[:, None] + d + np.exp(ls2) * z, mu[:, None] + s[:, None] * z)
        return np.sort(np.maximum(np.expm1(out), 0.0), axis=1)


class LogNormalEB(LogNormal):
    """Lognormal; each player's spread multiplied by an empirical-Bayes factor
    lambda_i^2 = (sum z_j^2 + k) / (n_i + k) from his own earlier standardized
    residuals (previous season + this season's prior weeks); k fitted on train."""
    name = "lognormal_eb"

    def player_lambda(self, market, model, cs, k):
        lam = np.ones(len(cs))
        for i, c in enumerate(cs):
            h = c["hist"]
            if not h:
                continue
            hp = np.array([x[0] for x in h])
            ha = np.array([x[1] for x in h])
            hc = [{"proj": x, "pos": c["pos"], "snap_share": np.nan, "tgt_share": np.nan} for x in hp]
            proj, Z, Lc, _ = LogNormal.design(self, market, hc, model["fmeans"])
            mu, s = self.mu_s(model["th"], proj, Z, Lc)
            z = (np.log1p(np.maximum(ha, 0)) - mu) / s
            lam[i] = np.sqrt((np.sum(z ** 2) + k) / (len(z) + k))
        return lam

    def fit(self, market, tr):
        base = LogNormal.fit(self, market, tr)
        proj, Z, Lc, _ = self.design(market, tr, base["fmeans"])
        a = arr(tr, "actual")
        mu, s = self.mu_s(base["th"], proj, Z, Lc)
        y = np.log1p(np.maximum(a, 0))
        best = None
        for k in (1, 2, 4, 8, 16, 32, 64, 1e9):
            lam = self.player_lambda(market, base, tr, k)
            ss = s * lam
            ll = np.where(a <= 0, stats.norm.logcdf(-mu / ss), stats.norm.logpdf((y - mu) / ss) - np.log(ss)).sum()
            if best is None or ll > best[0]:
                best = (ll, k)
        return {**base, "k": best[1]}

    def predict(self, market, model, cs, scale=1.0):
        proj, Z, Lc, _ = self.design(market, cs, model["fmeans"])
        mu, s = self.mu_s(model["th"], proj, Z, Lc, scale)
        s = s * self.player_lambda(market, model, cs, model["k"])
        return np.maximum(np.expm1(mu[:, None] + s[:, None] * stats.norm.ppf(UGRID)[None, :]), 0.0)


class NegBin:
    """Receptions ~ NegBin(mean L*proj, dispersion alpha*mean^beta) (Var = m + alpha m^(1+beta)). MLE."""
    name = "negbin"

    def nb(self, th, proj, scale=1.0):
        m = proj * np.exp(th[0]) * scale
        var_extra = np.exp(th[1]) * m ** (1 + th[2])
        n = m ** 2 / np.maximum(var_extra, 1e-9)
        return m, n

    def fit(self, market, tr):
        proj, a = arr(tr, "proj"), arr(tr, "actual")

        def nll(th):
            m, n = self.nb(th, proj)
            return -stats.nbinom.logpmf(a, n, n / (n + m)).sum()
        r = optimize.minimize(nll, np.array([0.0, np.log(0.05), 1.0]), method="Nelder-Mead", options={"maxiter": 4000})
        return {"th": r.x}

    def predict(self, market, model, cs, scale=1.0):
        m, n = self.nb(model["th"], arr(cs, "proj"), scale)
        return stats.nbinom.ppf(UGRID[None, :], n[:, None], (n / (n + m))[:, None]).astype(float)


class PoissonPlain:
    """Receptions ~ Poisson(L*proj): no projection error, the least dispersed baseline."""
    name = "poisson_plain"

    def fit(self, market, tr):
        return {"L": float(arr(tr, "actual").sum() / arr(tr, "proj").sum())}

    def predict(self, market, model, cs, scale=1.0):
        return stats.poisson.ppf(UGRID[None, :], (arr(cs, "proj") * model["L"] * scale)[:, None]).astype(float)


class Bootstrap:
    """Empirical residual bootstrap: actual/projection ratios from train, by
    market x position group x projection quintile."""
    name = "bootstrap"

    def key(self, market, c):
        if market == "player_pass_yds":
            return "all"
        if market == "player_rush_yds":
            return "QB" if c["pos"] == "QB" else "RB+"
        return "RB" if c["pos"] == "RB" else "WR/TE"

    def fit(self, market, tr):
        proj = arr(tr, "proj")
        edges = np.quantile(proj, [0.2, 0.4, 0.6, 0.8])
        groups = defaultdict(list)
        for c in tr:
            groups[(self.key(market, c), int(np.searchsorted(edges, c["proj"])))].append(c["actual"] / c["proj"])
        allr = defaultdict(list)
        for c in tr:
            allr[self.key(market, c)].append(c["actual"] / c["proj"])
        return {"edges": edges, "q": {k: np.quantile(v, UGRID) for k, v in groups.items() if len(v) >= 25},
                "qk": {k: np.quantile(v, UGRID) for k, v in allr.items()}}

    def predict(self, market, model, cs, scale=1.0):
        out = np.empty((len(cs), S))
        for i, c in enumerate(cs):
            k = (self.key(market, c), int(np.searchsorted(model["edges"], c["proj"])))
            q = model["q"].get(k)
            if q is None:
                q = model["qk"].get(k[0], next(iter(model["qk"].values())))
            out[i] = q * c["proj"] * scale
        if market == "player_receptions":
            out = np.floor(out + 0.5)
        return out


class QuantReg:
    """Linear quantile regression of actual/projection on log(proj), position,
    lagged snap share and target share, at 99 levels (rearranged to be monotone)."""
    name = "quantreg"
    TAUS = np.arange(1, 100) / 100

    def X(self, market, cs, fm=None):
        R, fm = role_feats(cs, fm)
        P = pos_dummies(market, cs)
        return np.column_stack([np.ones(len(cs)), np.log(arr(cs, "proj") / REF[market]), P, R]), fm

    def fit(self, market, tr):
        import statsmodels.api as sm
        X, fm = self.X(market, tr)
        y = arr(tr, "actual") / arr(tr, "proj")
        B = np.array([sm.QuantReg(y, X).fit(q=t, max_iter=5000).params for t in self.TAUS])
        return {"B": B, "fm": fm}

    def predict(self, market, model, cs, scale=1.0):
        X, _ = self.X(market, cs, model["fm"])
        Q = np.sort(X @ model["B"].T, axis=1)  # (n, 99) rearranged
        out = np.array([np.interp(UGRID, self.TAUS, q) for q in Q]) * arr(cs, "proj")[:, None] * scale
        if market != "player_rush_yds":
            out = np.maximum(out, 0)
        return out


class Recalibrated(Current):
    """Current model + PIT recalibration (split-conformal style): the model's
    nominal quantile levels are remapped to the empirical PIT distribution
    observed on train. Shape-preserving; fixes systematic tail miscoverage."""
    name = "current_recal"

    def fit(self, market, tr):
        base = Current.fit(self, market, tr)
        M = Current.predict(self, market, base, tr)
        u = pit(M, arr(tr, "actual"), np.random.default_rng(3))
        return {**base, "hinv": np.quantile(u, UGRID)}

    def predict(self, market, model, cs, scale=1.0):
        M = Current.predict(self, market, model, cs, scale)
        idx = np.clip((model["hinv"] * S).astype(int), 0, S - 1)
        return M[:, idx]


class Normal:
    """Symmetric alternative: X ~ Normal(L*proj, cv*L*proj), floored at 0. MLE."""
    name = "normal"

    def fit(self, market, tr):
        proj, a = arr(tr, "proj"), arr(tr, "actual")

        def nll(th):
            m = proj * np.exp(th[0])
            return -stats.norm.logpdf(a, m, np.exp(th[1]) * m).sum()
        r = optimize.minimize(nll, np.array([0.0, np.log(0.3)]), method="Nelder-Mead")
        return {"th": r.x, "cv": float(np.exp(r.x[1])), "level": float(np.exp(r.x[0]))}

    def predict(self, market, model, cs, scale=1.0):
        m = arr(cs, "proj") * model["level"] * scale
        return np.maximum(m[:, None] * (1 + model["cv"] * stats.norm.ppf(UGRID)[None, :]), 0.0)


YARD_METHODS = [Current(), CurrentRefit(), LogNormal(), LogNormalMix(), LogNormalFeat(), LogNormalEB(),
                Bootstrap(), QuantReg(), Recalibrated(), Normal()]
REC_METHODS = [Current(), CurrentRefit(), PoissonPlain(), NegBin(), Bootstrap(), QuantReg(), Recalibrated()]


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------

def per_case_scores(M, cs, rng):
    a, proj = arr(cs, "actual"), arr(cs, "proj")
    q = M[:, (DECILES * S).astype(int)]
    d = a[:, None] - q
    pin = np.mean(np.maximum(DECILES * d, (DECILES - 1) * d), axis=1)
    u = pit(M, a, rng)
    reg = {}
    for name, rs in REGIONS.items():
        P, Y = [], []
        for r in rs:
            line = np.floor(r * proj) + 0.5
            P.append((M > line[:, None]).mean(1))
            Y.append((a > line).astype(float))
        P, Y = np.array(P).T, np.array(Y).T
        reg[name] = (P, Y)
    return pin, u, reg


def clusters(cs):
    keys = {}
    return np.array([keys.setdefault((c["season"], c["week"], c["team"]), len(keys)) for c in cs])


def boot_ci(vals, cl, B=1000, seed=0):
    """Mean and 95% cluster-bootstrap CI of per-case values."""
    rng = np.random.default_rng(seed)
    ncl = cl.max() + 1
    sums = np.bincount(cl, weights=vals, minlength=ncl)
    cnts = np.bincount(cl, minlength=ncl)
    bs = []
    for _ in range(B):
        w = np.bincount(rng.integers(0, ncl, ncl), minlength=ncl)
        bs.append((w * sums).sum() / (w * cnts).sum())
    return vals.mean(), np.percentile(bs, 2.5), np.percentile(bs, 97.5)


def center_scale(method, market, model, cs):
    """Oracle re-centering: scale s.t. the median PIT on this set is 0.5."""
    a = arr(cs, "actual")
    lo, hi = 0.6, 1.6
    for _ in range(11):
        mid = (lo + hi) / 2
        u = pit(method.predict(market, model, cs, mid), a, np.random.default_rng(9))
        if np.median(u) > 0.5:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--centered", action="store_true")
    ap.add_argument("--markets", default=",".join(D.MARKETS))
    ap.add_argument("--methods", default="")
    args = ap.parse_args()
    sp = D.load_splits()
    train = sp["train_2025_w4-10"]
    tests = [k for k in sp if k.startswith("test")]
    for market in args.markets.split(","):
        methods = REC_METHODS if market == "player_receptions" else YARD_METHODS
        if args.methods:
            methods = [m for m in methods if m.name in args.methods.split(",") or m.name == "current"]
        tr = [c for c in train if c["market"] == market]
        models = {}
        for m in methods:
            t0 = time.time()
            models[m.name] = m.fit(market, tr)
            extra = {k: v for k, v in models[m.name].items() if k in ("level", "proj_err", "cv", "dud", "k")}
            print(f"[fit] {market} {m.name} {time.time() - t0:.1f}s {extra}", file=sys.stderr)
        for split in tests:
            cs = [c for c in sp[split] if c["market"] == market]
            cl = clusters(cs)
            print(f"\n=== {market} | {split} | n={len(cs)} | {'CENTERED (shape only)' if args.centered else 'train level'} ===")
            print(f"{'method':15} {'pinball':>8} {'d% vs cur [95% CI]':>24} | PIT<.10 .25 .50 .75 .90 |"
                  f" {'Brier goblin':>13} {'std':>6} {'demon':>6} | bias(pred-real) gob/std/dem | dBrier vs cur x1e3 gob / std / dem [95% CI]")
            base = None
            for m in methods:
                sc = center_scale(m, market, models[m.name], cs) if args.centered else 1.0
                M = m.predict(market, models[m.name], cs, sc)
                pin, u, reg = per_case_scores(M, cs, np.random.default_rng(21))
                brier = {k: ((P - Y) ** 2).mean(1) for k, (P, Y) in reg.items()}
                bias = {k: (P - Y).mean(1) for k, (P, Y) in reg.items()}
                if base is None:
                    base = (pin, brier)
                dp = boot_ci((pin - base[0]) / base[0].mean() * 100, cl)
                cov = [np.mean(u < t) for t in (0.1, 0.25, 0.5, 0.75, 0.9)]
                bb = []
                for k in REGIONS:
                    mean, lo, hi = boot_ci((brier[k] - base[1][k]) * 1e3, cl)
                    bb.append(f"{mean:+5.1f}[{lo:+5.1f},{hi:+5.1f}]")
                bi = []
                for k in REGIONS:
                    mean, lo, hi = boot_ci(bias[k], cl)
                    bi.append(f"{mean:+.3f}")
                tag = f" (scale {sc:.2f})" if args.centered else ""
                print(f"{m.name:15} {pin.mean():8.3f} {dp[0]:+6.2f}% [{dp[1]:+5.2f},{dp[2]:+5.2f}] |"
                      f" {' '.join(f'{x:.2f}' for x in cov)} | {brier['goblin'].mean():13.4f} {brier['standard'].mean():6.4f}"
                      f" {brier['demon'].mean():6.4f} | {'/'.join(bi)} | {' / '.join(bb)}{tag}")


if __name__ == "__main__":
    main()
