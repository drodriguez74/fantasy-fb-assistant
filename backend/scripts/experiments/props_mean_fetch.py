"""Fetch (and cache) the free data the props-mean experiments need.

Sleeper weekly projections + stats (QB/RB/WR/TE) and ESPN fantasy weekly
projections for 2024 wk 1-18, 2025 wk 1-18 and 2026 wk 1-4. Everything lands
in backend/.cache/backtest/ using the same file names as
scripts/backtest_projections.py and scripts/backtest_game_lines.py.

    cd backend && source venv/bin/activate
    python scripts/experiments/props_mean_fetch.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
from backtest_projections import _get  # noqa: E402
from backtest_game_lines import espn_projections  # noqa: E402

PLAN = {2024: range(1, 19), 2025: range(1, 19), 2026: range(1, 5)}

if __name__ == "__main__":
    for season, weeks in PLAN.items():
        for w in weeks:
            s = _get("stats", season, w)
            p = _get("projections", season, w)
            e = espn_projections(season, w) or {}
            print(season, w, "stats", len(s), "proj", len(p), "espn", len(e), flush=True)
