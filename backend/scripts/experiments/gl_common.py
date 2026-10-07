"""Shared helpers for the game-line experiments (not app code).

Data: nflverse games.csv (cached by scripts/backtest_game_lines.py at
backend/.cache/backtest/nflverse_games.csv). Conventions:
- spread_line > 0: home favored by that many points; home covers when
  result (home - away) > spread_line.
- Fit window 2015-2024 (all game types); out-of-sample (OOS) = 2025 REG +
  2026 REG weeks 1-4, matching scripts/backtest_game_lines.py.
"""
import math
import os
import urllib.request

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "..", "..", ".cache", "backtest")
GAMES = os.path.join(CACHE, "nflverse_games.csv")
GAMES_URL = "https://github.com/nflverse/nfldata/raw/master/data/games.csv"


def american_to_decimal(p):
    p = np.asarray(p, float)
    return np.where(p > 0, 1 + p / 100, 1 + 100 / -p)


def implied(p):
    return 1 / american_to_decimal(p)


def load():
    if not os.path.exists(GAMES):
        os.makedirs(CACHE, exist_ok=True)
        req = urllib.request.Request(GAMES_URL, headers={"User-Agent": "ff-assistant-backtest"})
        with urllib.request.urlopen(req, timeout=60) as r, open(GAMES, "wb") as f:
            f.write(r.read())
    d = pd.read_csv(GAMES)
    d = d[d.home_score.notna() & d.spread_line.notna() & d.total_line.notna()].copy()
    d["margin"] = (d.home_score - d.away_score).astype(int)      # home margin
    d["points"] = (d.home_score + d.away_score).astype(int)
    ok = d[["home_spread_odds", "away_spread_odds", "over_odds", "under_odds"]].notna().all(axis=1)
    d = d[ok].copy()
    ih, ia = implied(d.home_spread_odds), implied(d.away_spread_odds)
    d["mkt_home"] = ih / (ih + ia)                                 # de-vigged home cover prob
    io, iu = implied(d.over_odds), implied(d.under_odds)
    d["mkt_over"] = io / (io + iu)
    d["oos"] = ((d.season == 2025) & (d.game_type == "REG")) | ((d.season == 2026) & (d.week <= 4) & (d.game_type == "REG"))
    d["fit"] = d.season.between(2015, 2024)
    return d.reset_index(drop=True)


def wilson(w, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = w / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return c - h, c + h


def boot_ci(x, n_boot=4000, seed=1, stat=np.mean):
    x = np.asarray(x, float)
    if len(x) == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    s = np.array([stat(x[rng.integers(0, len(x), len(x))]) for _ in range(n_boot)])
    return float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5))


def profit(win, push, price):
    """Flat 1u profit per bet at American price."""
    return np.where(push, 0.0, np.where(win, american_to_decimal(price) - 1, -1.0))


def ev(p_win, p_push, price):
    return p_win * (american_to_decimal(price) - 1) - np.clip(1 - p_win - p_push, 0, None)


def bet_report(label, win, push, price):
    win, push, price = np.asarray(win, bool), np.asarray(push, bool), np.asarray(price, float)
    n = len(win)
    if n == 0:
        return f"{label:34} n=0"
    pr = profit(win, push, price)
    w, l = int((win & ~push).sum()), int((~win & ~push).sum())
    ci = boot_ci(pr)
    return (f"{label:34} n={n:4} {w}-{l}-{n - w - l}  hit {w / max(w + l, 1):.1%}  flat {pr.sum():+6.1f}u"
            f"  ROI {pr.mean():+.1%} [95% {ci[0]:+.1%}, {ci[1]:+.1%}]")
