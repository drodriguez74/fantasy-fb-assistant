"""Shared data for the props_dist_* experiments (prop outcome distributions).

Builds one row per (player-week, market) from Sleeper's free weekly
projections and actual stats (cached in backend/.cache/backtest/, same files
as scripts/backtest_projections.py), plus lagged role features computed only
from weeks BEFORE the row's week (no leakage):

- snap_share   mean offensive snap share over the player's prior games this season
- tgt_share    mean share of team targets over prior games this season
- hist         list of the player's earlier [projection, actual] pairs in this
               market (this season's prior weeks + the whole previous season);
               used for per-player (empirical-Bayes) dispersion

Same case filter as the calibration backtest: the player played, and was
projected for a prop-sized amount (QB pass >= 150, rush/rec yds >= 20, rec >= 2).
"""
import json
import os
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import backtest_projections as bp  # noqa: E402  (reuses its cached Sleeper fetcher)

STATS = bp.STATS
MARKETS = [m for m, _, _ in STATS.values()]
STAT_OF = {m: s for s, (m, _, _) in STATS.items()}
FLOOR = {m: f for _, (m, _, f) in STATS.items()}
YARDS = {"player_pass_yds", "player_rush_yds", "player_reception_yds"}


def _season(season: int, weeks=range(1, 19)):
    """{week: (proj rows by pid, stat rows by pid)} for weeks that have data."""
    out = {}
    for w in weeks:
        try:
            st = bp._get("stats", season, w)
            pr = bp._get("projections", season, w)
        except Exception:
            continue
        if not st:
            continue
        out[w] = ({r["player_id"]: r for r in pr}, {r["player_id"]: r for r in st if (r.get("stats") or {}).get("gp")})
    return out


def _team_targets(stat_rows):
    t = defaultdict(float)
    for r in stat_rows.values():
        t[r.get("team")] += float((r.get("stats") or {}).get("rec_tgt") or 0)
    return t


def build(season: int, weeks, history_seasons=1):
    """Cases for `season` at `weeks`, with lagged features."""
    data = _season(season)
    prev = {}
    for s in range(season - history_seasons, season):
        prev[s] = _season(s)

    def residual_rows(d):
        """(week, pid, market, [proj, actual]) for every prop-sized player-week in d."""
        rows = []
        for w, (pr, st) in sorted(d.items()):
            for pid, srow in st.items():
                prow = pr.get(pid)
                if not prow:
                    continue
                proj = prow.get("stats") or {}
                pos = (prow.get("player") or {}).get("position")
                for stat, (market, only_pos, floor) in STATS.items():
                    p = proj.get(stat)
                    if (only_pos and pos != only_pos) or p is None or p < floor:
                        continue
                    a = float(srow["stats"].get(stat) or 0.0)
                    rows.append((w, pid, market, [float(p), a]))
        return rows

    hist_prev = defaultdict(list)
    for s, d in prev.items():
        for w, pid, m, lr in residual_rows(d):
            hist_prev[(pid, m)].append(lr)
    cur_rows = residual_rows(data)
    hist_cur = defaultdict(list)  # (pid, m) -> [(week, lr)]
    for w, pid, m, lr in cur_rows:
        hist_cur[(pid, m)].append((w, lr))

    # Lagged role features from actual stats.
    snaps = defaultdict(list)   # pid -> [(week, share)]
    tgts = defaultdict(list)
    for w, (pr, st) in data.items():
        tt = _team_targets(st)
        for pid, r in st.items():
            s = r["stats"]
            if s.get("tm_off_snp"):
                snaps[pid].append((w, float(s.get("off_snp") or 0) / float(s["tm_off_snp"])))
            if tt.get(r.get("team")):
                tgts[pid].append((w, float(s.get("rec_tgt") or 0) / tt[r.get("team")]))

    def lag_mean(lst, w):
        v = [x for ww, x in lst if ww < w]
        return float(np.mean(v)) if v else np.nan

    cases = []
    for w in weeks:
        if w not in data:
            continue
        pr, st = data[w]
        for pid, prow in pr.items():
            srow = st.get(pid)
            if srow is None:
                continue
            proj = prow.get("stats") or {}
            pos = (prow.get("player") or {}).get("position")
            for stat, (market, only_pos, floor) in STATS.items():
                p = proj.get(stat)
                if (only_pos and pos != only_pos) or p is None or p < floor:
                    continue
                hist = hist_prev.get((pid, market), []) + [lr for ww, lr in hist_cur.get((pid, market), []) if ww < w]
                cases.append({
                    "season": season, "week": w, "pid": pid, "pos": pos, "team": prow.get("team"),
                    "market": market, "proj": float(p), "actual": float(srow["stats"].get(stat) or 0.0),
                    "proj_tgt": float(proj.get("rec_tgt") or 0), "proj_rush_att": float(proj.get("rush_att") or 0),
                    "proj_pass_att": float(proj.get("pass_att") or 0),
                    "snap_share": lag_mean(snaps.get(pid, []), w), "tgt_share": lag_mean(tgts.get(pid, []), w),
                    "hist": hist,
                })
    return cases


SPLITS = {
    "train_2025_w4-10": (2025, range(4, 11)),
    "test_2025_w11-17": (2025, range(11, 18)),
    "test_2026_w1-4": (2026, range(1, 5)),
    "test_2024_w4-17": (2024, range(4, 18)),
}
CACHE_FILE = os.path.join(HERE, "..", "..", ".cache", "backtest", "props_dist_cases.json")


def load_splits(refresh=False):
    if os.path.exists(CACHE_FILE) and not refresh:
        with open(CACHE_FILE) as f:
            return json.load(f)
    out = {}
    for name, (season, weeks) in SPLITS.items():
        out[name] = build(season, list(weeks))
    with open(CACHE_FILE, "w") as f:
        json.dump(out, f)
    return out


if __name__ == "__main__":
    sp = load_splits(refresh=True)
    for name, cs in sp.items():
        cnt = defaultdict(int)
        for c in cs:
            cnt[c["market"]] += 1
        print(name, len(cs), dict(cnt))
