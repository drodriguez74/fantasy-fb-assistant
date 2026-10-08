"""Backtest the college game-line model on a past season with real lines.

The live college board prices spreads with ESPN's matchup predictor (win
probability -> margin, CFB_SPREAD_SD) blended at CFB_MODEL_WEIGHT with the
market, capped at CFB_MAX_UNITS; totals are market-only. This replays that
exact pricing (betting_service.evaluate_game) on every FBS regular-season
game of a season using free ESPN data:

- the pregame ESPN BET spread and total (sports.core.api.espn.com .../odds),
- ESPN's pregame predictor (.../predictor, home gameProjection),
- the final score (site API scoreboard).

One book at -110 per side is the market, so -- like the NFL backtest -- a bet
can only come from the predictor, never from line shopping. Reports bets,
record, ROI, calibration and whether the predictor adds anything to the line
(Brier vs the line alone, and the weight that would have scored best on the
first half of the season, checked on the second).

    cd backend && source venv/bin/activate
    python scripts/backtest_cfb_lines.py [--season 2025] [--weeks 1-14] [--weight 0.15]
"""
import argparse
import asyncio
import json
import math
import os
import sys

import httpx
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.services import betting_model as bm  # noqa: E402
from app.services import betting_service as bs  # noqa: E402

CACHE = os.path.join(os.path.dirname(__file__), "..", ".cache", "backtest")
SITE = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard"
CORE = "https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/events/{e}/competitions/{e}"


def parse_weeks(text):
    a, _, b = text.partition("-")
    return list(range(int(a), int(b or a) + 1))


async def fetch_season(season, weeks):
    path = os.path.join(CACHE, f"cfb_games_{season}.json")
    if os.path.exists(path):
        cached = json.load(open(path))
        if all(str(w) in cached for w in weeks):
            return cached
    else:
        cached = {}
    sem = asyncio.Semaphore(12)
    async with httpx.AsyncClient(timeout=30) as client:
        async def get(url, **params):
            async with sem:
                for _ in range(3):
                    try:
                        r = await client.get(url, params=params)
                        if r.status_code == 200:
                            return r.json()
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(1)
                return None

        async def game(ev):
            comp = ev["competitions"][0]
            if not comp.get("status", {}).get("type", {}).get("completed"):
                return None
            teams = {c["homeAway"]: c for c in comp["competitors"]}
            odds, pred = await asyncio.gather(get(CORE.format(e=ev["id"]) + "/odds"),
                                              get(CORE.format(e=ev["id"]) + "/predictor"))
            line = next((o for o in (odds or {}).get("items", []) if "Live" not in (o.get("provider") or {}).get("name", "")
                         and o.get("spread") is not None), None)
            stats = {s.get("name"): s.get("value") for s in ((pred or {}).get("homeTeam") or {}).get("statistics", [])}
            if not line or stats.get("gameProjection") is None:
                return None
            return {"id": ev["id"], "home": teams["home"]["team"]["displayName"], "away": teams["away"]["team"]["displayName"],
                    "home_score": float(teams["home"]["score"]), "away_score": float(teams["away"]["score"]),
                    "home_spread": float(line["spread"]), "total": line.get("overUnder"),
                    "p_home": float(stats["gameProjection"]) / 100, "date": ev.get("date")}

        for w in weeks:
            if str(w) in cached:
                continue
            board = await get(SITE, dates=season, seasontype=2, week=w, groups=80, limit=400)
            events = (board or {}).get("events", [])
            rows = [g for g in await asyncio.gather(*(game(e) for e in events)) if g]
            cached[str(w)] = rows
            print(f"  week {w}: {len(events)} FBS games, {len(rows)} with a line and a predictor", flush=True)
            os.makedirs(CACHE, exist_ok=True)
            json.dump(cached, open(path, "w"))
    return cached


def odds_game(g):
    """A games.csv-style row as one book quoting the spread (and total) at -110."""
    markets = [{"key": "spreads", "outcomes": [{"name": g["home"], "point": g["home_spread"], "price": -110},
                                               {"name": g["away"], "point": -g["home_spread"], "price": -110}]}]
    if g.get("total"):
        markets.append({"key": "totals", "outcomes": [{"name": "Over", "point": float(g["total"]), "price": -110},
                                                      {"name": "Under", "point": float(g["total"]), "price": -110}]})
    return {"id": g["id"], "home_team": g["home"], "away_team": g["away"], "commence_time": g.get("date"),
            "bookmakers": [{"key": "espnbet", "markets": markets}]}


def wilson(k, n):
    if not n:
        return (float("nan"), float("nan"))
    p, z = k / n, 1.96
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2025)
    ap.add_argument("--weeks", default="1-14")
    ap.add_argument("--weight", type=float, default=bm.CFB_MODEL_WEIGHT)
    args = ap.parse_args()
    weeks = parse_weeks(args.weeks)
    data = asyncio.run(fetch_season(args.season, weeks))
    games = [(int(w), g) for w in weeks for g in data.get(str(w), [])]
    sds = (bm.CFB_SPREAD_SD, bm.CFB_TOTAL_SD)

    bets, lines = [], []
    for w, g in games:
        model = {"margin": bm.margin_from_win_prob(g["p_home"], bm.CFB_SPREAD_SD)}
        for rec in bs.evaluate_game(odds_game(g), model, sds, args.weight, bm.CFB_MAX_UNITS):
            if rec["market"] != "spread":
                continue
            side_home = rec["side"] == (bs._team(g["home"]) or g["home"])
            margin = g["home_score"] - g["away_score"]
            diff = (margin if side_home else -margin) + rec["line"]
            result = "push" if diff == 0 else ("won" if diff > 0 else "lost")
            row = {"week": w, "p_win": rec["p_win"], "model": rec["model_prob"], "market": rec["market_prob"],
                   "units": rec["units"], "result": result}
            lines.append(row)
            if rec["units"] > 0:
                bets.append(row)

    def summary(rows, label):
        dec = [r for r in rows if r["result"] != "push"]
        k = sum(r["result"] == "won" for r in dec)
        profit = sum((r["units"] or 1) * (100 / 110 if r["result"] == "won" else -1) for r in dec)
        staked = sum((r["units"] or 1) for r in dec)
        lo, hi = wilson(k, len(dec))
        print(f"{label:28} n={len(rows):4d}  {k}-{len(dec) - k}-{len(rows) - len(dec)}  hit {k / max(1, len(dec)):.1%} "
              f"[{lo:.0%}, {hi:.0%}]  break-even 52.4%  units {profit:+.1f} on {staked:.1f} (ROI {profit / max(staked, 1e-9):+.1%})")

    print(f"\n=== {args.season} college, weeks {args.weeks}: {len(games)} FBS games with a line and ESPN's predictor ===")
    print(f"model weight {args.weight}, max units {bm.CFB_MAX_UNITS}, spread SD {bm.CFB_SPREAD_SD}")
    summary(bets, "Bets (shipped rule)")
    half = weeks[len(weeks) // 2]
    summary([b for b in bets if b["week"] < half], f"  weeks < {half}")
    summary([b for b in bets if b["week"] >= half], f"  weeks >= {half}")

    # Does the predictor add information to the line? Fixed side: the home team covers.
    rows = []
    for w, g in games:
        margin = g["home_score"] - g["away_score"]
        if margin + g["home_spread"] == 0:
            continue
        p_model = 1 - __import__("statistics").NormalDist(-g["home_spread"], bm.CFB_SPREAD_SD).cdf(
            -bm.margin_from_win_prob(g["p_home"], bm.CFB_SPREAD_SD) * 0 + 0)  # placeholder, replaced below
        m = bm.margin_from_win_prob(g["p_home"], bm.CFB_SPREAD_SD)
        p_model = 1 - __import__("statistics").NormalDist(m, bm.CFB_SPREAD_SD).cdf(-g["home_spread"])
        rows.append((w, p_model, float(margin + g["home_spread"] > 0)))
    W = np.array([r[0] for r in rows]); P = np.array([r[1] for r in rows]); Y = np.array([r[2] for r in rows])

    def brier(p, y):
        return float(np.mean((p - y) ** 2))
    print("\nHome-cover Brier (lower is better; 0.25 = coin flip):")
    print(f"  line alone (50%)   {brier(np.full_like(Y, 0.5), Y):.4f}")
    print(f"  predictor alone    {brier(P, Y):.4f}")
    for wt in (0.15, 0.30):
        print(f"  blend at {wt:.2f}       {brier(wt * P + (1 - wt) * 0.5, Y):.4f}")
    fit, test = W < half, W >= half
    grid = np.round(np.arange(0, 1.01, 0.05), 2)
    best = min(grid, key=lambda wt: brier(wt * P[fit] + (1 - wt) * 0.5, Y[fit]))
    print(f"  best weight on weeks < {half}: {best}; held-out weeks >= {half}: "
          f"{brier(best * P[test] + (1 - best) * 0.5, Y[test]):.4f} vs line {brier(np.full(test.sum(), 0.5), Y[test]):.4f} "
          f"vs shipped {brier(bm.CFB_MODEL_WEIGHT * P[test] + (1 - bm.CFB_MODEL_WEIGHT) * 0.5, Y[test]):.4f}")
    print("\nCalibration of the predictor on the home side (predicted cover vs actual):")
    for lo, hi in ((0, .4), (.4, .45), (.45, .5), (.5, .55), (.55, .6), (.6, 1.01)):
        sel = (P >= lo) & (P < hi)
        if sel.sum() >= 20:
            print(f"  {lo:.2f}-{min(hi, 1):.2f}: n={sel.sum():4d}  predicted {P[sel].mean():.1%}  actual {Y[sel].mean():.1%}")


if __name__ == "__main__":
    main()
