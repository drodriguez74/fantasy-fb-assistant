"""Is Monte Carlo precision a source of error in the prop model?

    cd backend && source venv/bin/activate
    python scripts/experiments/props_dist_mc.py

Compares betting_model.simulate_stat's P(over) (production: N_SIMS=20,000
draws, crc32 seed per prop; centering uses 4,000) with the exact value from
numerical integration of the same two-level model (normal true mean, then
gamma / Poisson), on the real 2025 weeks 11-17 cases at goblin / standard /
demon lines. Also measures how much the slate-centering scale moves when only
the random seeds change, and the Brier score the noise costs on real outcomes.
"""
import os
import sys

import numpy as np
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", ".."))
import props_dist_data as D  # noqa: E402
from app.services import betting_model as bm  # noqa: E402

GH_X, GH_W = np.polynomial.hermite_e.hermegauss(200)  # probabilists' Gauss-Hermite
GH_W = GH_W / GH_W.sum()


def exact_over(market, mean, line):
    """P(X > line) for simulate_stat's model by quadrature over the true mean
    (the clip at 0.01 handled as in the sim)."""
    tm = np.clip(mean + bm.projection_error(market) * mean * GH_X, 0.01, None)
    if market in bm.YARDS_CV:
        shape = 1 / bm.yards_cv(market, mean) ** 2
        p = stats.gamma.sf(line, shape, scale=tm / shape)
    else:
        p = stats.poisson.sf(np.floor(line), tm)
    return float(np.sum(GH_W * p))


def main():
    sp = D.load_splits()
    cs = sp["test_2025_w11-17"]
    rows = []
    for i, c in enumerate(cs):
        for r in (0.6, 1.0, 1.3):
            line = np.floor(r * c["proj"]) + 0.5
            seed = f"prop|{c['pid']}|{c['market']}|{c['week']}"
            s20 = bm.simulate_stat(c["market"], c["proj"], seed)
            s4 = bm.simulate_stat(c["market"], c["proj"], seed, n=4000)
            ex = exact_over(c["market"], c["proj"], line)
            rows.append((c["market"], r, ex, float(np.mean(s20 > line)), float(np.mean(s4 > line)), float(c["actual"] > line)))
    rows = np.array(rows, dtype=object)
    print(f"{len(cs)} cases x 3 lines (2025 weeks 11-17)\n")
    print(f"{'market':22} {'line':>5} {'n':>5} | N=20k err: RMS  max | N=4k err: RMS  max | Brier exact  N=20k  diff")
    for m in D.MARKETS:
        for r in (0.6, 1.0, 1.3):
            sel = (rows[:, 0] == m) & (rows[:, 1] == r)
            ex, p20, p4, y = (rows[sel, k].astype(float) for k in (2, 3, 4, 5))
            e20, e4 = p20 - ex, p4 - ex
            b_ex, b20 = np.mean((ex - y) ** 2), np.mean((p20 - y) ** 2)
            print(f"{m:22} {r:5.1f} {sel.sum():5d} | {np.sqrt(np.mean(e20**2)):.4f} {np.abs(e20).max():.4f} |"
                  f" {np.sqrt(np.mean(e4**2)):.4f} {np.abs(e4).max():.4f} | {b_ex:.5f} {b20:.5f} {b20 - b_ex:+.6f}")
    # EV impact at -110 (decimal 1.909): dEV = dP * 1.909; the blend scales the model's P by MODEL_WEIGHT.
    allerr = rows[:, 3].astype(float) - rows[:, 2].astype(float)
    print(f"\nall lines: N=20k P error RMS {np.sqrt(np.mean(allerr**2)):.4f}, 99th pct |err| {np.percentile(np.abs(allerr), 99):.4f}"
          f" -> EV error at -110 after the 30% model weight: RMS {np.sqrt(np.mean(allerr**2)) * 1.909 * bm.MODEL_WEIGHT * 100:.2f}% (MIN_EV is 3%)")

    # Slate-centering scale: same (projection, line) pairs, different random seeds.
    rng = np.random.default_rng(0)
    for m in ("player_reception_yds", "player_rush_yds", "player_pass_yds", "player_receptions"):
        mc = [c for c in cs if c["market"] == m and c["week"] == 12][:30]
        pairs = [(c["proj"], float(np.floor(c["proj"] * rng.uniform(0.8, 1.0)) + 0.5)) for c in mc]
        scales = []
        orig = bm._rng
        for k in range(8):
            bm._rng = (lambda kk: (lambda t: orig(f"{t}|rep{kk}")))(k)
            scales.append(bm.fit_projection_scale(m, pairs))
        bm._rng = orig
        print(f"centering scale, {m:22} {len(pairs)} props, 8 seed sets: {np.round(scales, 3).tolist()}  sd {np.std(scales):.4f}")


if __name__ == "__main__":
    main()
