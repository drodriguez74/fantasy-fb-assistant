"""Role-conditioned spread for the current gamma model (rush / receiving yards).

    cd backend && source venv/bin/activate
    python scripts/experiments/props_dist_role.py

props_dist_diag.py showed the current model's 80% band covers only ~70% for
low-snap / low-target-share / low-projection players (20% below q10) and
~83% for high ones. This tests whether conditioning the gamma model on lagged
snap share fixes that out of sample:

- gamma_vol   : refit VOLUME_EXPONENT (and cv) only
- gamma_snap  : cv multiplied by exp(g * (snap_share - mean)), g fitted
- gamma_snapdud: plus a dud rate rising as snap share falls
                 (p_dud = clip(d0 + d1 * (mean - snap), 0, .3))

Each fitted on 2025 wk 4-10 by pinball (common random numbers), scored on the
three held-out sets, train level and centered. Also prints the standard-line
P(over) bias for the low-snap third, the guard against re-creating the
low-volume Under lean the guide warns about (VOLUME_EXPONENT decision).
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import props_dist_data as D  # noqa: E402
import props_dist_eval as E  # noqa: E402
from app.services import betting_model as bm  # noqa: E402


class GammaRole(E.Current):
    def __init__(self, name, keys):
        self.name, self.keys = name, keys

    def sim(self, market, cs, p, seed, scale=1.0, n=E.S):
        proj = E.arr(cs, "proj")
        snap = E.arr(cs, "snap_share")
        snap = np.where(np.isnan(snap), p["snap_mean"], snap) - p["snap_mean"]
        rng = np.random.default_rng(seed)
        mm = proj * p["level"] * scale
        m = mm[:, None]
        tm = np.clip(m + p["proj_err"] * m * rng.standard_normal((len(cs), n)), 0.01, None)
        cv = p["cv"] * (bm.YARDS_REF_MEAN[market] / np.maximum(mm, 1.0)) ** p["e"] * np.exp(p["g"] * snap)
        cv = np.clip(cv, p["cv"] * 0.5, bm.MAX_YARDS_CV)[:, None]
        shape = 1 / cv ** 2
        out = rng.gamma(np.broadcast_to(shape, tm.shape), tm / shape)
        pd = np.clip(p["d0"] + p["d1"] * (-snap), 0, 0.3)[:, None]
        dud = rng.random(out.shape) < pd
        scaled = out * (1 - pd * bm.DUD_FRACTION / 2) / (1 - pd)
        out = np.where(dud, tm * rng.uniform(0, bm.DUD_FRACTION, out.shape), scaled)
        return np.sort(out, axis=1)

    GRID = {"level": np.arange(0.9, 1.15, 0.02), "proj_err": np.arange(0.0, 0.41, 0.05),
            "cv": np.arange(0.4, 0.91, 0.025), "e": np.arange(0.0, 0.81, 0.1),
            "g": np.arange(-3.0, 0.01, 0.25), "d0": np.arange(0.0, 0.11, 0.01), "d1": np.arange(0.0, 0.61, 0.05)}

    def fit(self, market, tr):
        snap_mean = float(np.nanmean(E.arr(tr, "snap_share")))
        p = {**{"level": 1.0, "proj_err": bm.PROJECTION_ERROR, "cv": bm.YARDS_CV[market],
                       "e": bm.VOLUME_EXPONENT, "g": 0.0, "d0": 0.0, "d1": 0.0}, "snap_mean": snap_mean}
        a = E.arr(tr, "actual")

        def loss(pp):
            q = self.sim(market, tr, pp, 5, n=1500)[:, (E.DECILES * 1500).astype(int)]
            d = a[:, None] - q
            return np.mean(np.maximum(E.DECILES * d, (E.DECILES - 1) * d))
        best = loss(p)
        for _ in range(2):
            for k in ["level", "proj_err", "cv"] + self.keys:
                for v in self.GRID[k]:
                    t = {**p, k: float(v)}
                    s = loss(t)
                    if s < best - 1e-9:
                        best, p = s, t
        return p

    def predict(self, market, model, cs, scale=1.0):
        return self.sim(market, cs, model, 11, scale)


def main():
    sp = D.load_splits()
    train = sp["train_2025_w4-10"]
    methods = [E.Current(), GammaRole("gamma_vol", ["e"]), GammaRole("gamma_snap", ["g"]),
               GammaRole("gamma_snapdud", ["g", "d0", "d1"])]
    for market in ("player_reception_yds", "player_rush_yds"):
        tr = [c for c in train if c["market"] == market]
        models = {m.name: m.fit(market, tr) for m in methods}
        for name, mo in models.items():
            print(f"[fit] {market} {name} " + str({k: round(float(v), 3) for k, v in mo.items()}))
        for split in [k for k in sp if k.startswith("test")]:
            cs = [c for c in sp[split] if c["market"] == market]
            cl = E.clusters(cs)
            snap = E.arr(cs, "snap_share")
            low = snap < np.nanquantile(snap, 1 / 3)
            for centered in (False, True):
                print(f"--- {market} {split} n={len(cs)} {'centered' if centered else 'train level'}")
                base = None
                for m in methods:
                    sc = E.center_scale(m, market, models[m.name], cs) if centered else 1.0
                    M = m.predict(market, models[m.name], cs, sc)
                    pin, u, reg = E.per_case_scores(M, cs, np.random.default_rng(21))
                    brier = {k: ((P - Y) ** 2).mean(1) for k, (P, Y) in reg.items()}
                    if base is None:
                        base = (pin, brier)
                    dp = E.boot_ci((pin - base[0]) / base[0].mean() * 100, cl)
                    db = [E.boot_ci((brier[k] - base[1][k]) * 1e3, cl) for k in E.REGIONS]
                    P, Y = reg["standard"]
                    lowbias = (P[low] - Y[low]).mean()
                    inband_low = np.mean((u[low] >= .1) & (u[low] <= .9))
                    print(f"  {m.name:14} pinball {pin.mean():7.3f} d {dp[0]:+.2f}% [{dp[1]:+.2f},{dp[2]:+.2f}]"
                          f" | PIT<.1 {np.mean(u < .1):.3f} >.9 {np.mean(u > .9):.3f} | low-snap 80%-band {inband_low:.3f}"
                          f" std-line bias(low snap) {lowbias:+.3f} | dBrier x1e3 " +
                          " / ".join(f"{k} {b[0]:+.1f}[{b[1]:+.1f},{b[2]:+.1f}]" for k, b in zip(E.REGIONS, db)))


if __name__ == "__main__":
    main()
