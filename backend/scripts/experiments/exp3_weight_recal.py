"""Experiment 3: MODEL_WEIGHT 0 / 0.15 / 0.30 for the shipped Sleeper game
model, and isotonic / Platt recalibration of the blended probability.

Reuses scripts/backtest_game_lines.py's reconstruction (shipped
betting_service.game_models + evaluate_game at the closing line/prices)
for 2025 wk1-18 and 2026 wk1-4. The Sleeper model only exists for these
seasons, so recalibration is cross-fitted leave-one-week-out (each week's
probabilities come from a calibrator fitted on the other 21 weeks).

    python scripts/experiments/exp3_weight_recal.py
"""
import os
import sys

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import backtest_game_lines as bgl  # noqa: E402
from app.services import betting_service as bs  # noqa: E402
from app.services import odds_service  # noqa: E402
from gl_common import bet_report, boot_ci  # noqa: E402

WEIGHTS = (0.0, 0.15, 0.30)


def collect():
    fixed, bets = [], {w: [] for w in WEIGHTS}
    for season, weeks in ((2025, range(1, 19)), (2026, range(1, 5))):
        games_csv = bgl.load_games(season)
        pred = bgl.espn_predictor(season, [r["espn"] for r in games_csv])
        for week in weeks:
            rows = [r for r in games_csv if int(r["week"]) == week]
            if not rows:
                continue
            games, models, _ = bgl.week_models(season, week, rows, pred)
            for r, g in zip(rows, games):
                m = models.get(g["id"])
                for w in WEIGHTS:
                    for rec in bs.evaluate_game(g, m, model_weight=w):
                        if rec["units"] > 0:
                            bets[w].append({"win": bgl.grade(r, rec["market"], rec["side"], rec["line"]) == "W",
                                            "push": bgl.grade(r, rec["market"], rec["side"], rec["line"]) == "P",
                                            "price": rec["price"], "units": rec["units"], "kind": rec["market"]})
                ih, ia = 1 / bgl.bm.american_to_decimal(float(r["home_spread_odds"])), 1 / bgl.bm.american_to_decimal(float(r["away_spread_odds"]))
                io, iu = 1 / bgl.bm.american_to_decimal(float(r["over_odds"])), 1 / bgl.bm.american_to_decimal(float(r["under_odds"]))
                for rec in bs.evaluate_game(bgl.odds_game(r, ("home",)), m):
                    if rec["model_prob"] is None:
                        continue
                    res = bgl.grade(r, rec["market"], rec["side"], rec["line"])
                    fixed.append({"season": season, "week": week, "kind": rec["market"], "res": res,
                                  "model": rec["model_prob"], "market": rec["market_prob"], "push": rec["p_push"],
                                  "price_devig": ih / (ih + ia) if rec["market"] == "spread" else io / (io + iu)})
            print(f"  {season} wk {week}", file=sys.stderr)
    return fixed, bets


def main():
    fixed, bets = collect()
    print("Bets under the live rule at closing prices, by MODEL_WEIGHT (2025 + 2026 wk1-4)")
    for w in WEIGHTS:
        b = bets[w]
        for kind in ("spread", "total"):
            x = [r for r in b if r["kind"] == kind]
            print("  " + bet_report(f"w={w:.2f} {kind}", [r["win"] for r in x], [r["push"] for r in x], [r["price"] for r in x]))
    for kind in ("spread", "total"):
        xs = [r for r in fixed if r["kind"] == kind and r["res"] != "P"]
        y = np.array([r["res"] == "W" for r in xs], float)
        mkt = np.array([r["market"] / (1 - r["push"]) for r in xs])
        mod = np.array([r["model"] / (1 - r["push"]) for r in xs])
        price = np.array([r["price_devig"] for r in xs])
        wk = np.array([r["season"] * 100 + r["week"] for r in xs])
        print(f"\n{kind}: fixed side (home cover / Over), pushes excluded, n={len(y)}; Brier (diff vs line-only market, 95% CI)")
        base = (mkt - y) ** 2

        def show(name, p):
            b = (p - y) ** 2
            lo, hi = boot_ci(b - base)
            print(f"  {name:38} {b.mean():.4f}  diff {np.mean(b - base):+.4f} [{lo:+.4f},{hi:+.4f}]")

        show("market, line only (shipped p_mkt)", mkt)
        show("market, de-vigged closing price", price)
        for w in WEIGHTS[1:] + (0.5, 1.0):
            show(f"blend w={w}", w * mod + (1 - w) * mkt)
        blend = 0.3 * mod + 0.7 * mkt
        iso, platt = np.zeros(len(y)), np.zeros(len(y))
        for k in np.unique(wk):
            tr, te = wk != k, wk == k
            ir = IsotonicRegression(out_of_bounds="clip", y_min=0.01, y_max=0.99).fit(blend[tr], y[tr])
            iso[te] = ir.predict(blend[te])
            lg = LogisticRegression(C=1.0).fit(np.log(blend[tr] / (1 - blend[tr]))[:, None], y[tr])
            platt[te] = lg.predict_proba(np.log(blend[te] / (1 - blend[te]))[:, None])[:, 1]
        show("blend w=0.30, isotonic (LOWO CV)", iso)
        show("blend w=0.30, Platt (LOWO CV)", platt)
        lg = LogisticRegression(C=1.0).fit(np.log(blend / (1 - blend))[:, None], y)
        print(f"  Platt slope on logit(blend w=0.30), all data: {lg.coef_[0][0]:+.2f} (1 = calibrated, 0 = no information)")
        lg = LogisticRegression(C=1e6).fit(np.c_[np.log(mod / (1 - mod))], y)
        print(f"  logistic slope on logit(Sleeper model) alone: {lg.coef_[0][0]:+.2f}")


if __name__ == "__main__":
    main()
