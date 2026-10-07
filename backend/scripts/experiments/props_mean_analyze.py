"""Out-of-sample tests of ways to improve the props model's MEAN projection.

Reads the case table from props_mean_build.py. Every adjustment is fitted on
2025 wk 4-10 and scored on 2025 wk 11-17 + 2026 wk 1-4 (TEST); 2024 wk 4-17 is
a second, independent replication set (REP, same 2025-fitted coefficients).

Yardage/receptions: MAE and RMSE, delta vs Sleeper with a 95% bootstrap CI
(2,000 resamples clustered by game). "lvl" = the same after rescaling every
method's predictions to Sleeper's weekly mean per market (live slate centering
resets the level from the market, so only the shape of a change can help).
Anytime TD: Brier and log loss for p = 1 - exp(-lambda).

    python scripts/experiments/props_mean_fetch.py
    python scripts/experiments/props_mean_build.py
    python scripts/experiments/props_mean_analyze.py
"""
import os
import sys

import numpy as np
import pandas as pd
from scipy.optimize import minimize

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "..", "..", ".cache", "backtest")
YARD_MARKETS = ["pass_yds", "rush_yds", "rec_yds", "receptions"]
B = 2000
RNG = np.random.default_rng(42)


# ---------------------------------------------------------------------------
# Data + features
# ---------------------------------------------------------------------------

def load():
    d = pd.read_pickle(os.path.join(CACHE, "props_mean_cases.pkl"))
    d = d[d.E.notna() & (d.E > 0)].copy()
    d["split"] = np.where(d.season == 2024, "REP",
                 np.where((d.season == 2025) & (d.week <= 10), "FIT", "TEST"))
    eps = 1e-3
    d["lS"] = np.log(d.S)
    d["dSE"] = np.log(d.E / d.S)
    d["vegas"] = np.log(d.imp / d.sl_team_pts.clip(lower=7))
    d["imp_c"] = d.imp - 22.5
    # recent production relative to the projection (last 4 games)
    stat_r = {"pass_yd": "r_pass_yd", "rush_yd": "r_rush_yd", "rec_yd": "r_rec_yd", "rec": "r_rec"}
    d["r_ratio"] = np.nan
    for st, col in stat_r.items():
        m = d.stat == st
        d.loc[m, "r_ratio"] = np.log((d.loc[m, col].clip(lower=0) + 1) / (d.loc[m, "S"] + 1))
    td = d.stat == "td"
    d.loc[td, "r_ratio"] = np.log(((d.loc[td, "r_rec_yd"] + d.loc[td, "r_rush_yd"]).clip(lower=0) + 10) /
                                  (d.loc[td, "S"] * 150 + 10))
    d["tgt_gap"] = np.log((d.r_tgt + 1) / (d.proj_tgt.fillna(0) + 1))
    d["car_gap"] = np.log((d.r_car + 1) / (d.proj_car.fillna(0) + 1))
    d["early"] = (d.week <= 3).astype(float)
    d["rookie"] = (pd.to_numeric(d.years_exp, errors="coerce").fillna(3) == 0).astype(float)
    d["few_games"] = (d.r_n.fillna(0) < 3).astype(float)
    for p in ("RB", "WR", "TE"):
        d[f"is_{p}"] = (d.pos == p).astype(float)
    return d


FEATURES = {
    "vegas": ["vegas", "imp_c", "spread"],
    "usage": ["r_ratio", "r_tgt_sh", "r_car_sh", "r_snap_sh", "r_ay_sh", "tgt_gap", "car_gap"],
    "opp": ["opp_f"],
    "bias": ["lS", "early", "rookie", "few_games", "is_RB", "is_WR", "is_TE"],
}
FEATURES["all"] = sum((FEATURES[k] for k in ("vegas", "usage", "opp", "bias")), [])


# ---------------------------------------------------------------------------
# Models (fitted on FIT only)
# ---------------------------------------------------------------------------

def _design(g, cols, mu, sd):
    X = ((g[cols] - mu) / sd).fillna(0.0).to_numpy()
    return np.clip(X, -4, 4)


def fit_mult(fit, cols, alpha=None):
    """y ~ S * (a + b.x), ridge on b (alpha chosen by 5-fold CV on FIT by game)."""
    mu, sd = fit[cols].mean(), fit[cols].std().replace(0, 1)
    X = _design(fit, cols, mu, sd)
    S, y = fit.S.to_numpy(), fit.y.to_numpy()
    Z = np.column_stack([S, S[:, None] * X])

    def solve(Z, y, a):
        P = np.eye(Z.shape[1]) * a * (Z[:, 0] ** 2).mean()
        P[0, 0] = 0
        return np.linalg.solve(Z.T @ Z + P, Z.T @ y)

    if alpha is None:
        games = fit.game.unique()
        folds = {g: i % 5 for i, g in enumerate(RNG.permutation(games))}
        f = fit.game.map(folds).to_numpy()
        best = None
        for a in (0.01, 0.1, 1, 10, 100):
            err = 0.0
            for k in range(5):
                tr, te = f != k, f == k
                beta = solve(Z[tr], y[tr], a)
                err += np.sum((y[te] - Z[te] @ beta) ** 2)
            if best is None or err < best[0]:
                best = (err, a)
        alpha = best[1]
    beta = solve(Z, y, alpha)
    return lambda g: np.clip(np.column_stack([g.S, g.S.to_numpy()[:, None] * _design(g, cols, mu, sd)]) @ beta, 0, None), beta


def fit_blend(fit):
    S, E, y = fit.S.to_numpy(), fit.E.to_numpy(), fit.y.to_numpy()
    ws = np.linspace(0, 1, 101)
    w = ws[np.argmin([np.mean((y - (w * S + (1 - w) * E)) ** 2) for w in ws])]
    return lambda g: w * g.S + (1 - w) * g.E, w


def fit_gbm(fit, cols):
    from sklearn.ensemble import HistGradientBoostingRegressor
    cols = list(dict.fromkeys(cols + ["lS", "dSE"]))
    X = fit[cols]
    m = HistGradientBoostingRegressor(max_depth=3, learning_rate=0.03, max_iter=200, min_samples_leaf=40,
                                      l2_regularization=1.0, random_state=0)
    m.fit(X, (fit.y / fit.S).clip(upper=4), sample_weight=fit.S ** 2)  # == squared error on y
    return lambda g: g.S * m.predict(g[cols]).clip(0, None)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def level_match(g, pred):
    """Rescale pred to Sleeper's mean within each (season, week)."""
    p = pd.Series(np.asarray(pred, float), index=g.index)
    k = g.groupby(["season", "week"]).S.transform("sum") / p.groupby([g.season, g.week]).transform("sum")
    return (p * k).to_numpy()


def boot(g, base, pred):
    """Delta MAE% and RMSE% vs base, clustered bootstrap by game."""
    y = g.y.to_numpy()
    ae0, ae1 = np.abs(y - base), np.abs(y - pred)
    se0, se1 = (y - base) ** 2, (y - pred) ** 2
    codes, uniq = pd.factorize(g.game)
    sums = np.zeros((len(uniq), 5))
    for j, arr in enumerate((ae0, ae1, se0, se1, np.ones_like(y))):
        sums[:, j] = np.bincount(codes, weights=arr, minlength=len(uniq))
    idx = RNG.integers(0, len(uniq), (B, len(uniq)))
    S = sums[idx].sum(axis=1)
    dmae = (S[:, 1] - S[:, 0]) / S[:, 0] * 100
    drmse = (np.sqrt(S[:, 3] / S[:, 4]) - np.sqrt(S[:, 2] / S[:, 4])) / np.sqrt(S[:, 2] / S[:, 4]) * 100
    pt = lambda a, b: (a.mean() - b.mean()) / b.mean() * 100
    return (pt(ae1, ae0), *np.percentile(dmae, [2.5, 97.5]),
            (np.sqrt(se1.mean()) - np.sqrt(se0.mean())) / np.sqrt(se0.mean()) * 100, *np.percentile(drmse, [2.5, 97.5]))


def fmt(r):
    return f"{r[0]:+5.1f}% [{r[1]:+5.1f},{r[2]:+5.1f}]  RMSE {r[3]:+5.1f}% [{r[4]:+5.1f},{r[5]:+5.1f}]"


def yard_market(d, market):
    g = d[d.market == market]
    fit = g[g.split == "FIT"]
    models = {}
    pb, w = fit_blend(fit)
    models["ESPN"] = lambda x: x.E
    models[f"blend w_S={w:.2f}"] = pb
    for k, cols in FEATURES.items():
        models[f"ridge:{k}"], _ = fit_mult(fit, cols)
    models["ridge:all+ESPN"], _ = fit_mult(fit, FEATURES["all"] + ["dSE"])
    models["gbm:all+ESPN"] = fit_gbm(fit, FEATURES["all"])
    print(f"\n=== {market}: FIT n={len(fit)}  TEST n={sum(g.split == 'TEST')} "
          f"(2025 wk11-17 {sum((g.split == 'TEST') & (g.season == 2025))}, 2026 wk1-4 {sum(g.season == 2026)})  REP(2024) n={sum(g.split == 'REP')}")
    for split in ("TEST", "REP"):
        t = g[g.split == split]
        base = t.S.to_numpy()
        print(f"  [{split}] Sleeper MAE {np.mean(np.abs(t.y - base)):.3f}  RMSE {np.sqrt(np.mean((t.y - base) ** 2)):.3f}")
        for name, f in models.items():
            pred = np.asarray(f(t), float)
            raw = boot(t, base, pred)
            lvl = boot(t, base, level_match(t, pred))
            print(f"    {name:20} raw dMAE {fmt(raw)} | lvl dMAE {lvl[0]:+5.1f}% [{lvl[1]:+5.1f},{lvl[2]:+5.1f}]")


# ---------------------------------------------------------------------------
# Disagreement: does |Sleeper - ESPN| predict bigger misses?
# ---------------------------------------------------------------------------

def disagreement(d):
    print("\n=== Sleeper vs ESPN disagreement (TEST + REP pooled; |log(E/S)| quartiles) ===")
    for market in YARD_MARKETS:
        g = d[(d.market == market) & (d.split != "FIT")].copy()
        g["ad"] = g.dSE.abs()
        g["q"] = pd.qcut(g.ad, 4, labels=["Q1 agree", "Q2", "Q3", "Q4 disagree"])
        g["mid"] = (g.S + g.E) / 2
        g["rel_err"] = (g.y - g.mid).abs() / g.mid
        out = g.groupby("q", observed=True).agg(n=("y", "size"), med_gap=("ad", "median"),
                                                mae_S=("S", lambda s: np.mean(np.abs(g.loc[s.index, "y"] - s))),
                                                mae_E=("E", lambda s: np.mean(np.abs(g.loc[s.index, "y"] - s))),
                                                relerr_mid=("rel_err", "mean"))
        # where they disagree, who is right? share of actual movement toward ESPN
        big = g[g.ad > 0.15]
        toward_e = np.mean(np.sign(big.y - big.S) == np.sign(big.E - big.S))
        rho = g[["ad", "rel_err"]].corr(method="spearman").iloc[0, 1]
        print(f"\n  {market}: spearman(|gap|, rel. miss of midpoint) = {rho:+.2f};"
              f" gap>15% (n={len(big)}): actual lands on ESPN's side of Sleeper {toward_e:.0%}")
        print(out.round(3).to_string())


# ---------------------------------------------------------------------------
# Anytime TD
# ---------------------------------------------------------------------------

def td(d):
    g = d[d.market == "anytime_td"].copy()
    fit = g[g.split == "FIT"]

    def probs(lam):
        return np.clip(1 - np.exp(-np.asarray(lam, float)), 1e-4, 1 - 1e-4)

    def ll(y, p):
        return -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))

    def fit_exp(cols, use_e=False):
        mu, sd = fit[cols].mean(), fit[cols].std().replace(0, 1)

        def lam(x, b):
            base = (b[-1] * x.S + (1 - b[-1]) * x.E) if use_e else x.S
            return base.to_numpy() * np.exp(b[0] + _design(x, cols, mu, sd) @ b[1:1 + len(cols)])

        nb = 1 + len(cols) + (1 if use_e else 0)
        x0 = np.zeros(nb)
        if use_e:
            x0[-1] = 0.5
        obj = lambda b: ll(fit.y.to_numpy(), probs(lam(fit, b))) + 0.01 * np.sum(b[1:1 + len(cols)] ** 2)
        b = minimize(obj, x0, method="L-BFGS-B",
                     bounds=[(None, None)] * (1 + len(cols)) + ([(0, 1)] if use_e else [])).x
        return lambda x: lam(x, b)

    models = {"Sleeper": lambda x: x.S, "ESPN": lambda x: x.E, "blend": fit_exp([], True),
              "level only": fit_exp([])}
    for k, cols in FEATURES.items():
        models[f"exp:{k}"] = fit_exp(cols)
    models["exp:vegas+ESPN"] = fit_exp(FEATURES["vegas"], True)
    models["exp:imp only"] = fit_exp(["vegas"])
    models["exp:all+ESPN"] = fit_exp(FEATURES["all"], True)
    print(f"\n=== anytime TD (RB/WR/TE, Sleeper lambda >= 0.15): FIT n={len(fit)} TEST n={sum(g.split == 'TEST')} REP n={sum(g.split == 'REP')}")
    print("  Note: live, td_rate_scale already rescales every TD rate to the game's Vegas total.")
    for split in ("TEST", "REP"):
        t = g[g.split == split]
        y = t.y.to_numpy()
        p0 = probs(t.S)
        codes, uniq = pd.factorize(t.game)
        idx = RNG.integers(0, len(uniq), (B, len(uniq)))
        print(f"  [{split}] base rate {y.mean():.3f}; Sleeper mean p {p0.mean():.3f}")
        for name, f in models.items():
            p = probs(f(t))
            # level-matched: scale lambda so mean p matches Sleeper's per week
            lam = np.asarray(f(t), float)
            lam_l = level_match(t, lam) if name != "Sleeper" else lam
            br0, br1 = (y - p0) ** 2, (y - p) ** 2
            bl = (y - probs(lam_l)) ** 2
            s0 = np.bincount(codes, br0, len(uniq))[idx].sum(1)
            s1 = np.bincount(codes, br1, len(uniq))[idx].sum(1)
            d_ = (s1 - s0) / s0 * 100
            print(f"    {name:14} Brier {br1.mean():.4f} ({(br1.mean() / br0.mean() - 1) * 100:+5.1f}% "
                  f"[{np.percentile(d_, 2.5):+5.1f},{np.percentile(d_, 97.5):+5.1f}])  logloss {ll(y, p):.4f}"
                  f"  | lvl Brier {(bl.mean() / br0.mean() - 1) * 100:+5.1f}%")


# ---------------------------------------------------------------------------
# Bias table: where is Sleeper systematically off? (ratio of sums actual/proj)
# ---------------------------------------------------------------------------

def bias(d):
    print("\n=== Sleeper bias: sum(actual)/sum(proj) by slice, FIT | TEST | REP (n) ===")
    for market in YARD_MARKETS + ["anytime_td"]:
        g = d[d.market == market].copy()
        g["size"] = g.groupby(["season", "week"]).S.transform(lambda s: pd.qcut(s.rank(method="first"), 3, labels=["low", "mid", "high"]))
        g["gap"] = pd.cut(g.dSE, [-9, -0.15, 0.15, 9], labels=["E<S-15%", "close", "E>S+15%"])
        g["hist"] = np.where(g.few_games == 1, "<3 games hist", ">=3 games")
        g["wk"] = np.where(g.week <= 3, "wk1-3", np.where(g.week <= 10, "wk4-10", "wk11-17"))
        print(f"\n  {market}")
        for col in ("size", "pos", "gap", "hist", "wk"):
            parts = []
            for lvl, h in g.groupby(col, observed=True):
                cells = []
                for sp in ("FIT", "TEST", "REP"):
                    x = h[h.split == sp]
                    cells.append(f"{x.y.sum() / x.S.sum():.2f}({len(x)})" if len(x) >= 20 else "  -  ")
                parts.append(f"{lvl}: " + " ".join(cells))
            print(f"    {col:5} " + " | ".join(parts))


# ---------------------------------------------------------------------------
# Extras: ESPN centered like live (espn_scale), asymmetric blend, wider fit
# ---------------------------------------------------------------------------

def center_espn(d):
    """E rescaled to Sleeper's weekly mean per market (live centers both on the market)."""
    k = d.groupby(["season", "week", "market"]).S.transform("sum") / d.groupby(["season", "week", "market"]).E.transform("sum")
    d["Ec"] = d.E * k
    d["gap_c"] = d.Ec - d.S
    d["dn"] = d.gap_c.clip(upper=0)
    d["up"] = d.gap_c.clip(lower=0)
    return d


def extras(d):
    d = center_espn(d)
    print("\n=== ESPN centered per week (as live), asymmetric blend, and 2024+2025wk4-10 'wide' fit -> TEST ===")
    for market in YARD_MARKETS:
        g = d[d.market == market]
        t = g[g.split == "TEST"]
        base = t.S.to_numpy()
        print(f"\n  {market} TEST n={len(t)}  Sleeper MAE {np.mean(np.abs(t.y - base)):.3f}")
        # side rate when centered sources disagree by >15%
        for split in ("TEST", "REP"):
            h = g[(g.split == split) & ((g.Ec / g.S - 1).abs() > 0.15)]
            hit = (np.sign(h.y - h.S) == np.sign(h.Ec - h.S)).astype(float)
            codes, uniq = pd.factorize(h.game)
            idx = RNG.integers(0, len(uniq), (B, len(uniq)))
            r = np.bincount(codes, hit, len(uniq))[idx].sum(1) / np.bincount(codes, None, len(uniq))[idx].sum(1)
            dn = h[h.Ec < h.S]
            upp = h[h.Ec > h.S]
            print(f"    [{split}] centered gap>15%: n={len(h)}, actual on ESPN's side {hit.mean():.1%} "
                  f"[{np.percentile(r, 2.5):.1%},{np.percentile(r, 97.5):.1%}]; ESPN lower: sum y/S {dn.y.sum() / dn.S.sum():.2f}, "
                  f"y/Ec {dn.y.sum() / dn.Ec.sum():.2f} (n={len(dn)}); ESPN higher: y/S {upp.y.sum() / upp.S.sum():.2f}, "
                  f"y/Ec {upp.y.sum() / upp.Ec.sum():.2f} (n={len(upp)})")
        for label, fit in (("FIT", g[g.split == "FIT"]), ("wide", g[g.split.isin(["FIT", "REP"])])):
            Z = np.column_stack([fit.S, fit.dn, fit.up])
            bb = np.linalg.lstsq(Z, fit.y, rcond=None)[0]
            ws = np.linspace(0, 1, 101)
            w = ws[np.argmin([np.mean((fit.y - (fit.S + (1 - w) * fit.gap_c)) ** 2) for w in ws])]
            cands = {
                f"centered blend w_S={w:.2f}": t.S + (1 - w) * t.gap_c,
                f"asym: S*{bb[0]:.2f} + {bb[1]:.2f}*down + {bb[2]:.2f}*up": bb[0] * t.S + bb[1] * t.dn + bb[2] * t.up,
                "fixed 50/50 centered": t.S + 0.5 * t.gap_c,
                "ESPN-lower only (S + 0.5*down)": t.S + 0.5 * t.dn,
            }
            if label == "wide":
                for k, cols in (("vegas", FEATURES["vegas"]), ("usage", FEATURES["usage"]), ("opp", FEATURES["opp"]),
                                ("bias", FEATURES["bias"]), ("all+ESPN", FEATURES["all"] + ["dSE"])):
                    cands[f"ridge:{k}"] = fit_mult(fit, cols)[0](t)
            for name, pred in cands.items():
                pred = np.asarray(pred, float)
                raw, lvl = boot(t, base, pred), boot(t, base, level_match(t, pred))
                print(f"    fit={label:4} {name:42} raw {fmt(raw)} | lvl {lvl[0]:+5.1f}% [{lvl[1]:+5.1f},{lvl[2]:+5.1f}]")


if __name__ == "__main__":
    d = load()
    which = sys.argv[1:] or ["yards", "disagree", "td", "bias", "extras"]
    if "yards" in which:
        for m in YARD_MARKETS:
            yard_market(d, m)
    if "disagree" in which:
        disagreement(d)
    if "td" in which:
        td(d)
    if "bias" in which:
        bias(d)
    if "extras" in which:
        extras(d)
