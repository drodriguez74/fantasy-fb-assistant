"""Experiment 4: quick checks.
  a) Is the closing PRICE informative beyond the line? (the shipped p_mkt for
     game lines ignores juice: a -3 at -125 and at +105 get the same p_mkt)
  b) Margin / total error SD by period, week bucket, and spread size
     (SPREAD_SD = 13.5, TOTAL_SD = 13.0 shipped).
  c) Wind-threshold unders and home-backup-QB unders, by period, to see
     whether exp2's regression hints replicate out of sample.

    python scripts/experiments/exp4_quick_checks.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from exp2_ratings import prep  # noqa: E402
from gl_common import bet_report, boot_ci  # noqa: E402

PERIODS = (("2006-14", lambda d: d.season.between(2006, 2014)), ("2015-24", lambda d: d.season.between(2015, 2024)),
           ("OOS 25-26", lambda d: d.oos))


def main():
    d = prep()
    print("a) Brier at the closing line, home cover / Over (pushes excluded): de-vigged price vs 50/50")
    for name, f in PERIODS:
        x = d[f(d)]
        for kind, res, line, p in (("spread", x.margin, x.spread_line, x.mkt_home), ("total", x.points, x.total_line, x.mkt_over)):
            keep = (res != line).values
            y = (res > line).values[keep].astype(float)
            pp = p.values[keep]
            b, b0 = (pp - y) ** 2, (0.5 - y) ** 2
            lo, hi = boot_ci(b - b0)
            print(f"  {name:9} {kind:6} n={keep.sum():4}: price {b.mean():.4f} vs 0.5 {b0.mean():.4f}  diff {np.mean(b - b0):+.5f} [{lo:+.5f},{hi:+.5f}]"
                  f"  mean |p-0.5| {np.mean(np.abs(pp - 0.5)):.3f}")
    # Bets on the side the juice favors when |p - 0.5| >= 0.02 (market says that side is more likely)
    for name, f in PERIODS:
        x = d[f(d)]
        sel = (x.mkt_home - 0.5).abs() >= 0.02
        x = x[sel]
        home = (x.mkt_home > 0.5).values
        win = np.where(home, x.margin > x.spread_line, x.margin < x.spread_line)
        print("  " + bet_report(f"{name} juiced side covers? (|p-.5|>=.02)", win, (x.margin == x.spread_line).values,
                                np.full(len(x), -110.0)) + "  (graded at -110 to show the hit rate)")

    print("\nb) Error SD (RMSE of result - close)")
    for name, f in PERIODS:
        x = d[f(d)]
        print(f"  {name:9}: margin {np.sqrt(np.mean((x.margin - x.spread_line) ** 2)):.2f}  total {np.sqrt(np.mean((x.points - x.total_line) ** 2)):.2f}  n={len(x)}")
    x = d[d.season.between(2015, 2024)]
    for lab, m in (("weeks 1-4", x.week <= 4), ("weeks 5-13", x.week.between(5, 13)), ("weeks 14+", x.week >= 14),
                   ("|spread| <= 3", x.spread_line.abs() <= 3), ("|spread| 3.5-7", x.spread_line.abs().between(3.5, 7)),
                   ("|spread| > 7", x.spread_line.abs() > 7), ("total < 42", x.total_line < 42), ("total >= 48", x.total_line >= 48)):
        y = x[m]
        rm = np.sqrt(np.mean((y.margin - y.spread_line) ** 2))
        rt = np.sqrt(np.mean((y.points - y.total_line) ** 2))
        print(f"  2015-24 {lab:15} margin {rm:.2f}  total {rt:.2f}  n={len(y)}")

    print("\nc) Under angles by period (flat 1u at the closing under price)")
    angles = {f"outdoor wind >= {w}": (lambda d, w=w: (d.outdoor == 1) & (d.wind >= w)) for w in (10, 12, 15, 18)}
    angles["home team backup QB"] = lambda d: d.bk_h == 1
    angles["either team backup QB"] = lambda d: (d.bk_h == 1) | (d.bk_a == 1)
    for name, sel in angles.items():
        for pname, f in PERIODS:
            x = d[f(d) & sel(d)]
            print("  " + bet_report(f"{name:24} {pname}", (x.points < x.total_line).values,
                                    (x.points == x.total_line).values, x.under_odds.values))


if __name__ == "__main__":
    main()
