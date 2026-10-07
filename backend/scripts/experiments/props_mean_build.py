"""Build the player-prop case table (with features) for the props-mean experiments.

One row per (player, week, market) on the same case filter as
scripts/backtest_projections.py: the player played (gp) and Sleeper projected a
prop-sized amount (QB pass >= 150, rush/rec yds >= 20, receptions >= 2). Anytime
TD rows are RB/WR/TE with Sleeper rush_td + rec_td >= 0.15.

Weeks: 2024 wk 4-17, 2025 wk 4-17, 2026 wk 1-4 (2026 early weeks use the
player's 2025 games as their usage history; 2024 wk 1-3 seed 2024's).

Every feature uses only games before the case's week (no peeking).

    python scripts/experiments/props_mean_build.py   # -> .cache/backtest/props_mean_cases.pkl
"""
import csv
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..")
sys.path.insert(0, BACKEND)
from app.services.weekly_projections import normalize_name  # noqa: E402

CACHE = os.path.join(BACKEND, ".cache", "backtest")
SEASON_WEEKS = {2024: range(1, 19), 2025: range(1, 19), 2026: range(1, 5)}
CASE_WEEKS = {2024: range(4, 18), 2025: range(4, 18), 2026: range(1, 5)}
STATS = {  # stat -> (market, position filter, floor)
    "pass_yd": ("pass_yds", "QB", 150.0),
    "rush_yd": ("rush_yds", None, 20.0),
    "rec_yd": ("rec_yds", None, 20.0),
    "rec": ("receptions", None, 2.0),
}
NFLVERSE_TEAM = {"LA": "LAR"}  # nflverse -> Sleeper
ROLL = 4  # games of usage history


def load(kind, season, week):
    path = os.path.join(CACHE, f"{kind}_{season}_{week}.json")
    if not os.path.exists(path):
        raise SystemExit(f"missing {path}: run props_mean_fetch.py first")
    with open(path) as f:
        return json.load(f)


def implied_totals():
    """{(season, week, team): (implied points, opp implied, spread for team (neg = favored))}"""
    out = {}
    with open(os.path.join(CACHE, "nflverse_games.csv")) as f:
        for r in csv.DictReader(f):
            if r["game_type"] != "REG" or int(r["season"]) not in SEASON_WEEKS or not r["total_line"]:
                continue
            s, w = int(r["season"]), int(r["week"])
            tot, sp = float(r["total_line"]), float(r["spread_line"])  # spread_line > 0: home favored
            home, away = (NFLVERSE_TEAM.get(r[k], r[k]) for k in ("home_team", "away_team"))
            h, a = (tot + sp) / 2, (tot - sp) / 2
            out[(s, w, home)] = (h, a, -sp)
            out[(s, w, away)] = (a, h, sp)
    return out


def main():
    vegas = implied_totals()
    # ---- actual stats, team totals, player histories ---------------------
    actual = {}            # (season, week, pid) -> stats
    meta = {}              # (season, week, pid) -> (team, opp, pos)
    team_tot = defaultdict(lambda: defaultdict(float))   # (s, w, team) -> stat sums
    allowed = defaultdict(lambda: defaultdict(float))    # (s, w, defense) -> pos_stat sums
    for s, weeks in SEASON_WEEKS.items():
        for w in weeks:
            for r in load("stats", s, w):
                st = r.get("stats") or {}
                if not st.get("gp"):
                    continue
                pid, team, opp = r["player_id"], r.get("team"), r.get("opponent")
                pos = (r.get("player") or {}).get("position")
                actual[(s, w, pid)] = st
                meta[(s, w, pid)] = (team, opp, pos)
                for k in ("rec_tgt", "rush_att", "rec_air_yd", "pass_att"):
                    team_tot[(s, w, team)][k] += float(st.get(k) or 0)
                team_tot[(s, w, team)]["tm_off_snp"] = max(team_tot[(s, w, team)]["tm_off_snp"], float(st.get("tm_off_snp") or 0))
                for k in ("pass_yd", "rush_yd", "rec_yd", "rec", "rush_td", "rec_td"):
                    allowed[(s, w, opp)][f"{pos}_{k}"] += float(st.get(k) or 0)
                allowed[(s, w, opp)]["games"] = 1

    def share(st, tot, k):
        return float(st.get(k) or 0) / tot[k] if tot[k] > 0 else np.nan

    history = defaultdict(list)  # pid -> [(s, w, usage dict)] chronological
    for (s, w, pid), st in sorted(actual.items()):
        team = meta[(s, w, pid)][0]
        tot = team_tot[(s, w, team)]
        u = {
            "tgt_sh": share(st, tot, "rec_tgt"), "car_sh": share(st, tot, "rush_att"),
            "ay_sh": share(st, tot, "rec_air_yd"),
            "snap_sh": float(st.get("off_snp") or 0) / tot["tm_off_snp"] if tot["tm_off_snp"] else np.nan,
            "tgt": float(st.get("rec_tgt") or 0), "car": float(st.get("rush_att") or 0),
            "ay": float(st.get("rec_air_yd") or 0), "patt": float(st.get("pass_att") or 0),
            **{k: float(st.get(k) or 0) for k in ("pass_yd", "rush_yd", "rec_yd", "rec")},
        }
        history[pid].append((s, w, u))

    order = {(s, w): i for i, (s, w) in enumerate((s, w) for s, ws in SEASON_WEEKS.items() for w in ws)}

    def recent(pid, s, w):
        idx = order[(s, w)]
        prev = [u for (ps, pw, u) in history.get(pid, []) if order[(ps, pw)] < idx][-ROLL:]
        if not prev:
            return {}
        out = {f"r_{k}": float(np.nanmean([p[k] for p in prev])) if any(not math.isnan(p[k]) for p in prev) else np.nan
               for k in prev[0]}
        out["r_n"] = len(prev)
        return out

    # league-average allowed per defense-game by position-stat, per season (expanding, prior weeks only)
    def opp_factor(s, w, opp, pos, stat):
        """Opponent's yards/receptions allowed to this position over prior weeks this season
        (2026 wk1-3 also uses 2025), shrunk toward league average with 4 pseudo-games."""
        key = f"{pos}_{stat}"
        weeks = [(s, pw) for pw in SEASON_WEEKS[s] if pw < w]
        if s == 2026:
            weeks += [(2025, pw) for pw in range(10, 19)]
        own = [allowed[(ss, ww, opp)][key] for ss, ww in weeks if allowed[(ss, ww, opp)]["games"]]
        lg = [v[key] for (ss, ww, d), v in allowed.items() if (ss, ww) in set(weeks) and v["games"]]
        if not lg:
            return np.nan
        avg = float(np.mean(lg))
        if avg <= 0:
            return np.nan
        k = 4.0
        est = (sum(own) + k * avg) / (len(own) + k)
        return math.log(est / avg)

    # ---- cases ------------------------------------------------------------
    rows = []
    for s, weeks in CASE_WEEKS.items():
        for w in weeks:
            proj = load("projections", s, w)
            espn = load("espn_projections", s, w)
            # Sleeper-implied team TDs (for the Vegas ratio)
            team_td = defaultdict(float)
            team_proj = defaultdict(lambda: defaultdict(float))
            for r in proj:
                p = r.get("stats") or {}
                team_td[r.get("team")] += float(p.get("rush_td") or 0) + float(p.get("rec_td") or 0)
                for k in ("rec_tgt", "rush_att", "pass_yd", "rush_yd", "rec_yd"):
                    team_proj[r.get("team")][k] += float(p.get(k) or 0)
            for r in proj:
                pid = r["player_id"]
                st = actual.get((s, w, pid))
                if st is None:
                    continue
                p = r.get("stats") or {}
                pl = r.get("player") or {}
                pos = pl.get("position")
                if pos not in ("QB", "RB", "WR", "TE"):
                    continue
                team, opp = r.get("team"), r.get("opponent")
                e = espn.get(normalize_name(f"{pl.get('first_name', '')} {pl.get('last_name', '')}"), {})
                vg = vegas.get((s, w, team))
                base = {
                    "season": s, "week": w, "pid": pid, "pos": pos, "team": team, "opp": opp,
                    "game": f"{s}-{w}-{'-'.join(sorted([team or '', opp or '']))}",
                    "imp": vg[0] if vg else np.nan, "opp_imp": vg[1] if vg else np.nan,
                    "spread": vg[2] if vg else np.nan,
                    "sl_team_pts": 7 * team_td[team],
                    "proj_tgt": float(p.get("rec_tgt") or np.nan), "proj_car": float(p.get("rush_att") or np.nan),
                    "proj_tm_tgt": team_proj[team]["rec_tgt"], "proj_tm_car": team_proj[team]["rush_att"],
                    "years_exp": pl.get("years_exp"),
                    **recent(pid, s, w),
                }
                for stat, (market, only, floor) in STATS.items():
                    sp = p.get(stat)
                    if (only and pos != only) or sp is None or sp < floor:
                        continue
                    rows.append({**base, "market": market, "stat": stat, "S": float(sp),
                                 "E": float(e[stat]) if stat in e else np.nan,
                                 "y": float(st.get(stat) or 0),
                                 "opp_f": opp_factor(s, w, opp, pos, stat)})
                lam = float(p.get("rush_td") or 0) + float(p.get("rec_td") or 0)
                if pos != "QB" and lam >= 0.15:
                    le = (e.get("rush_td", 0.0) + e.get("rec_td", 0.0)) if e else np.nan
                    rows.append({**base, "market": "anytime_td", "stat": "td", "S": lam, "E": le,
                                 "y": float((st.get("rush_td") or 0) + (st.get("rec_td") or 0) > 0),
                                 "opp_f": opp_factor(s, w, opp, pos, "rush_td" if pos == "RB" else "rec_td")})
    df = pd.DataFrame(rows)
    out = os.path.join(CACHE, "props_mean_cases.pkl")
    df.to_pickle(out)
    print(f"{len(df)} rows -> {out}")
    print(df.groupby(["season", "market"]).agg(n=("y", "size"), espn=("E", lambda x: x.notna().mean()),
                                               vegas=("imp", lambda x: x.notna().mean()),
                                               hist=("r_n", lambda x: x.notna().mean())).to_string())


if __name__ == "__main__":
    main()
