"""Tune the betting engine from its own graded results (bet_picks).

Every priced line, "Best available" fill and "Most likely to win" PrizePicks
pick is tracked with the books' probability, the engine's probability and
the blended win chance it was shown at, then graded from real results
(betting_tracking.py). This reads them back and answers, with the same rules
as the 2026-10-07 review (fit on earlier weeks, score on the latest ones,
bootstrap CIs -- BETTING_GUIDE.md section 9):

1. Calibration: when we said X%, how often did it win? Per tier (bets,
   fills, most-likely picks, no-bet lines), with Wilson 95% intervals.
2. Engine vs books: Brier score of the books alone, the engine alone and the
   shipped blend, on graded player props and most-likely picks.
3. Engine weight: the MODEL_WEIGHT that would have scored best on the
   earlier weeks, checked on the held-out latest weeks. It recommends a
   change only when the held-out gain's CI excludes zero and there are
   enough lines (MIN_LINES); otherwise it says to keep collecting.

Read-only: it never writes to the database or changes a setting.

    cd backend && source venv/bin/activate
    python scripts/tune_from_results.py [--season 2026] [--holdout-weeks 2]
"""
import argparse
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.db.base import SessionLocal  # noqa: E402
from app.models.bet_pick import BetPick  # noqa: E402
import app.models  # noqa: E402,F401  (registers every model)
from app.services import betting_model as bm  # noqa: E402

MIN_LINES = 300          # graded engine-vs-books lines before any weight change is considered
WEIGHTS = np.round(np.arange(0.0, 0.81, 0.05), 2)


def wilson(k: int, n: int):
    if n == 0:
        return (float("nan"), float("nan"))
    p, z = k / n, 1.96
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def tier(p: BetPick) -> str:
    if p.kind == "pp_leg":
        return "most likely (PrizePicks)"
    if p.confidence == "fill":
        return "best available (fill)"
    if p.recommended:
        return "bets"
    return "no-bet lines"


def load(season):
    with SessionLocal() as db:
        q = db.query(BetPick).filter(BetPick.status.in_(("won", "lost")))
        if season:
            q = q.filter(BetPick.season == season)
        return q.all()


def calibration_report(picks):
    print("1. Calibration (decided lines; pushes and voids excluded)")
    groups = {}
    for p in picks:
        groups.setdefault(tier(p), []).append(p)
    for name, ps in sorted(groups.items()):
        n, k = len(ps), sum(p.status == "won" for p in ps)
        lo, hi = wilson(k, n)
        pred = sum(p.p_win for p in ps) / n
        flag = "  <- outside the interval" if not lo <= pred <= hi else ""
        print(f"  {name:26} n={n:4d}  predicted {pred:5.1%}  actual {k / n:5.1%} [{lo:.0%}, {hi:.0%}]{flag}")
    print()


def brier(p, y):
    return float(np.mean((p - y) ** 2))


def engine_vs_books(picks):
    rows = [p for p in picks if p.kind in ("player_prop", "pp_leg")
            and p.model_prob is not None and p.market_prob is not None]
    print(f"2. Engine vs books (graded props with both probabilities: n={len(rows)})")
    if not rows:
        print("  nothing graded yet\n")
        return rows
    y = np.array([p.status == "won" for p in rows], float)
    books = np.array([p.market_prob for p in rows])
    engine = np.array([p.model_prob for p in rows])
    shown = np.array([p.p_win for p in rows])
    for name, v in (("books alone", books), ("engine alone", engine), ("shipped blend", shown)):
        print(f"  {name:14} Brier {brier(v, y):.4f}")
    print("  (lower is better; 0.25 is a coin flip)\n")
    return rows


def weight_check(rows, holdout_weeks, rng):
    print(f"3. Engine weight (shipped MODEL_WEIGHT = {bm.MODEL_WEIGHT})")
    weeks = sorted({(p.season, p.week) for p in rows})
    if len(rows) < MIN_LINES or len(weeks) <= holdout_weeks:
        print(f"  Keep collecting: {len(rows)} graded lines over {len(weeks)} week(s); a change needs "
              f"{MIN_LINES}+ lines and more weeks than the {holdout_weeks}-week holdout.\n")
        return
    test_weeks = set(weeks[-holdout_weeks:])
    fit = [p for p in rows if (p.season, p.week) not in test_weeks]
    test = [p for p in rows if (p.season, p.week) in test_weeks]

    def arrays(ps):
        return (np.array([p.model_prob for p in ps]), np.array([p.market_prob for p in ps]),
                np.array([p.status == "won" for p in ps], float))
    m_f, b_f, y_f = arrays(fit)
    best = min(WEIGHTS, key=lambda w: brier(w * m_f + (1 - w) * b_f, y_f))
    m_t, b_t, y_t = arrays(test)
    cur = (bm.MODEL_WEIGHT * m_t + (1 - bm.MODEL_WEIGHT) * b_t - y_t) ** 2
    new = (best * m_t + (1 - best) * b_t - y_t) ** 2
    diff = new - cur
    boots = [float(np.mean(diff[rng.integers(0, len(diff), len(diff))])) for _ in range(2000)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    print(f"  fit on {len(fit)} lines ({len(weeks) - holdout_weeks} weeks): best weight {best}")
    print(f"  held-out {len(test)} lines: Brier change vs shipped {np.mean(diff):+.4f} [{lo:+.4f}, {hi:+.4f}]")
    if best != bm.MODEL_WEIGHT and hi < 0:
        print(f"  -> Evidence supports MODEL_WEIGHT = {best} (held-out gain, CI excludes 0). Record it in the guide.")
    else:
        print("  -> Keep the shipped weight: no held-out gain that clears noise.")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=None)
    ap.add_argument("--holdout-weeks", type=int, default=2)
    args = ap.parse_args()
    picks = load(args.season)
    print(f"Graded, decided lines: {len(picks)}\n")
    calibration_report(picks)
    rows = engine_vs_books(picks)
    weight_check(rows, args.holdout_weeks, np.random.default_rng(7))


if __name__ == "__main__":
    main()
