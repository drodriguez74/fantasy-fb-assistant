"""Backtest the NFL game-line model (spreads + totals) on a past season with
real closing lines and final scores.

It runs the shipped pricing code itself -- betting_service._team_points,
game_models and evaluate_game -- with each game's closing line standing in
for the live market, then grades every priced line against the final score.
No Odds API credits: all data is free and cached in backend/.cache/backtest/.

    python scripts/backtest_game_lines.py                 # 2025, weeks 1-18
    python scripts/backtest_game_lines.py --weeks 4-17
    python scripts/backtest_game_lines.py --season 2026   # once a season is complete

Data:
- nflverse games.csv: closing spread/total, both sides' prices, final scores.
  spread_line > 0 means the home team is favored (checked against the
  moneylines), so the home team's spread in Odds API terms is -spread_line.
- Sleeper weekly projections (QB/RB/WR/TE, plus K fetched separately: the
  live game model adds kicker points).
- ESPN fantasy weekly projections (leaguedefaults accepts a past
  scoringPeriodId), fetched with the live espn_projections function.
- ESPN's matchup predictor. The live code reads it from the site API's
  `summary`, which drops `predictor` once a game is final, so the backtest
  reads the same number (homeTeam gameProjection) from ESPN's core API
  (.../competitions/{id}/predictor), which keeps the pregame value.

Reconstruction choices (live-only state rebuilt from history):
- One "book" per game quoting the closing line at the closing prices; the
  live board takes the median of three books and the best price among them.
- The slate for totals centering (game_models) is the whole week's games;
  live it's only the games that haven't kicked off when the board is built.
- ESPN's projection rows carry each player's *current* team (proTeamId), so
  a player's team is taken from that week's Sleeper row when the names match
  (live, current team == that week's team).
"""
import argparse
import asyncio
import csv
import json
import math
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from app.services import betting_model as bm  # noqa: E402
from app.services import betting_service as bs  # noqa: E402
from app.services import odds_service  # noqa: E402
from app.services.espn_projections import fetch_espn_weekly_projections  # noqa: E402
from app.services.weekly_projections import normalize_name  # noqa: E402
from backtest_projections import CACHE, _get  # noqa: E402

GAMES_URL = "https://github.com/nflverse/nfldata/raw/master/data/games.csv"
PREDICTOR_URL = ("https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{id}"
                 "/competitions/{id}/predictor")
FULL_NAME = {abbr: name for name, abbr in odds_service.TEAM_ABBR.items()}
BOOK = "closing"


# ---------------------------------------------------------------------------
# Data (all cached)
# ---------------------------------------------------------------------------

def _fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "ff-assistant-backtest"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def _cached(name: str, fetch):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name)
    if not os.path.exists(path):
        data = fetch()
        if not data:
            return data  # failures aren't cached
        with open(path, "w") as f:
            json.dump(data, f)
    with open(path) as f:
        return json.load(f)


def load_games(season: int):
    path = os.path.join(CACHE, "nflverse_games.csv")
    if not os.path.exists(path):
        os.makedirs(CACHE, exist_ok=True)
        req = urllib.request.Request(GAMES_URL, headers={"User-Agent": "ff-assistant-backtest"})
        with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
            f.write(r.read())
    with open(path) as f:
        rows = [r for r in csv.DictReader(f) if r["season"] == str(season) and r["game_type"] == "REG"]
    return [r for r in rows if r["home_score"] and r["spread_line"] and r["total_line"]
            and r["home_spread_odds"] and r["away_spread_odds"] and r["over_odds"] and r["under_odds"]]


def kicker_projections(season: int, week: int):
    url = f"https://api.sleeper.app/projections/nfl/{season}/{week}?season_type=regular&position[]=K"
    return _cached(f"projections_K_{season}_{week}.json", lambda: _fetch_json(url))


def espn_projections(season: int, week: int):
    return _cached(f"espn_projections_{season}_{week}.json",
                   lambda: asyncio.run(fetch_espn_weekly_projections(season, week)))


def espn_predictor(season: int, event_ids):
    """{espn event id: home win probability (pregame)}."""
    path = os.path.join(CACHE, f"espn_predictor_{season}.json")
    have = {}
    if os.path.exists(path):
        with open(path) as f:
            have = json.load(f)
    missing = [e for e in event_ids if e and e not in have]

    def one(eid):
        try:
            d = _fetch_json(PREDICTOR_URL.format(id=eid))
            stats = (d.get("homeTeam") or {}).get("statistics") or []
            v = next((s.get("value") for s in stats if s.get("name") == "gameProjection"), None)
            return eid, (float(v) / 100 if v is not None else None)
        except Exception:  # noqa: BLE001
            return eid, None

    if missing:
        with ThreadPoolExecutor(8) as ex:
            for eid, p in ex.map(one, missing):
                if p is not None:
                    have[eid] = p
        with open(path, "w") as f:
            json.dump(have, f)
        time.sleep(0.2)
    return have


# ---------------------------------------------------------------------------
# Pricing (the shipped code)
# ---------------------------------------------------------------------------

def odds_game(r, sides=("home", "away")):
    """A games.csv row as an Odds API event with one book at the closing line.
    `sides` restricts the outcomes (("home",) = home spread + Over only)."""
    home, away = FULL_NAME[odds_service.normalize_team(r["home_team"])], FULL_NAME[odds_service.normalize_team(r["away_team"])]
    sl, tl = float(r["spread_line"]), float(r["total_line"])
    spreads, totals = [], []
    if "home" in sides:
        spreads.append({"name": home, "point": -sl, "price": float(r["home_spread_odds"])})
        totals.append({"name": "Over", "point": tl, "price": float(r["over_odds"])})
    if "away" in sides:
        spreads.append({"name": away, "point": sl, "price": float(r["away_spread_odds"])})
        totals.append({"name": "Under", "point": tl, "price": float(r["under_odds"])})
    # Median line needs the home spread and Over quoted, so a one-side event
    # for the away/Under side still carries them at no usable price.
    if "home" not in sides:
        spreads.append({"name": home, "point": -sl, "price": None})
        totals.append({"name": "Over", "point": tl, "price": None})
    return {"id": r["game_id"], "home_team": home, "away_team": away, "commence_time": r["gameday"],
            "bookmakers": [{"key": BOOK, "markets": [{"key": "spreads", "outcomes": spreads},
                                                     {"key": "totals", "outcomes": totals}]}]}


def week_models(season, week, rows_csv, predictor):
    sleeper_rows = _get("projections", season, week) + (kicker_projections(season, week) or [])
    espn = dict(espn_projections(season, week) or {})
    # ESPN rows carry the player's current team; use that week's (Sleeper's).
    week_team = {}
    for r in sleeper_rows:
        p = r.get("player") or {}
        t = odds_service.normalize_team(r.get("team"))
        if t:
            week_team[normalize_name(f"{p.get('first_name', '')} {p.get('last_name', '')}")] = t
    espn = {n: {**row, "team": week_team.get(n, row.get("team"))} for n, row in espn.items()}
    games = [odds_game(r) for r in rows_csv]
    win_probs = {odds_service.normalize_team(r["home_team"]): predictor[r["espn"]]
                 for r in rows_csv if r["espn"] in predictor}
    sleeper_pts, espn_pts = bs._team_points(sleeper_rows, espn)
    return games, bs.game_models(games, sleeper_pts, espn_pts, win_probs), bool(espn)


def grade(r, kind, side, line):
    hs, as_ = int(r["home_score"]), int(r["away_score"])
    home = odds_service.normalize_team(r["home_team"])
    if kind == "spread":
        diff = ((hs - as_) if side == home else (as_ - hs)) + line
    else:
        diff = (hs + as_ - line) if side == "Over" else (line - hs - as_)
    return "W" if diff > 0 else "P" if diff == 0 else "L"


def profit(result, price):
    return (bm.american_to_decimal(price) - 1) if result == "W" else 0.0 if result == "P" else -1.0


def run(season, weeks):
    games_csv = load_games(season)
    predictor = espn_predictor(season, [r["espn"] for r in games_csv])
    recs, fixed, diag = [], [], []
    for week in weeks:
        rows_csv = [r for r in games_csv if int(r["week"]) == week]
        if not rows_csv:
            continue
        games, models, has_espn = week_models(season, week, rows_csv, predictor)
        for r, g in zip(rows_csv, games):
            m = models.get(g["id"])
            home = odds_service.normalize_team(r["home_team"])
            base = {"week": week, "game": f"{r['away_team']}@{r['home_team']}", "home": home}
            # Variant runs: shipped (with ESPN check) and without the check.
            variants = {"shipped": m, "no_check": ({**m, "check_margin": None, "check_total": None} if m else None)}
            for variant, model in variants.items():
                for rec in bs.evaluate_game(g, model, model_weight=MODEL_WEIGHT):
                    res = grade(r, rec["market"], rec["side"], rec["line"])
                    recs.append({**base, "variant": variant, "kind": rec["market"], "side": rec["side"],
                                 "line": rec["line"], "price": rec["price"], "p_win": rec["p_win"],
                                 "ev": rec["ev"], "units": rec["units"], "watch": rec["watch"],
                                 "model_prob": rec["model_prob"], "market_prob": rec["market_prob"],
                                 "check_prob": rec["check_prob"], "result": res,
                                 "fav": rec["market"] == "spread" and rec["line"] < 0,
                                 "is_home": rec["side"] == home})
            # Fixed side (home cover, Over) for unselected calibration.
            for rec in bs.evaluate_game(odds_game(r, ("home",)), m, model_weight=MODEL_WEIGHT):
                fixed.append({**base, "kind": rec["market"], "model_prob": rec["model_prob"],
                              "market_prob": rec["market_prob"], "check_prob": rec["check_prob"],
                              "p_push": rec["p_push"], "result": grade(r, rec["market"], rec["side"], rec["line"])})
            if m:
                hs, as_ = int(r["home_score"]), int(r["away_score"])
                diag.append({"week": week, "margin": hs - as_, "total": hs + as_, "line_margin": float(r["spread_line"]),
                             "line_total": float(r["total_line"]), "model_margin": m["margin"], "model_total": m["total"],
                             "espn_margin": m["check_margin"], "espn_total": m["check_total"]})
        print(f"  week {week:2}: {len(rows_csv)} games, {len(models)} modeled, ESPN projections {'yes' if has_espn else 'NO'}",
              file=sys.stderr)
    return recs, fixed, diag


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def wilson(w, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = w / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def summarize(rows, stake=lambda r: 1.0, boot=2000):
    n = len(rows)
    w = sum(r["result"] == "W" for r in rows)
    lo = sum(r["result"] == "L" for r in rows)
    p = n - w - lo
    flat = [profit(r["result"], r["price"]) for r in rows]
    st = [stake(r) for r in rows]
    unit = [f * s for f, s in zip(flat, st)]
    out = {"n": n, "W": w, "L": lo, "P": p, "hit": w / (w + lo) if w + lo else float("nan"),
           "ci": wilson(w, w + lo), "flat_profit": sum(flat), "flat_roi": sum(flat) / n if n else float("nan"),
           "units_staked": sum(st), "unit_profit": sum(unit),
           "unit_roi": sum(unit) / sum(st) if sum(st) else float("nan"),
           "breakeven": float(np.mean([bm.implied_prob(r["price"]) for r in rows])) if rows else float("nan")}
    if n and boot:
        rng = np.random.default_rng(1)
        arr = np.array(flat)
        sims = arr[rng.integers(0, n, (boot, n))].mean(axis=1)
        out["roi_ci"] = (float(np.percentile(sims, 2.5)), float(np.percentile(sims, 97.5)))
    else:
        out["roi_ci"] = (float("nan"), float("nan"))
    return out


def line(label, s):
    if not s["n"]:
        return f"{label:24} n=0"
    return (f"{label:24} n={s['n']:3}  {s['W']}-{s['L']}-{s['P']}  hit {s['hit']:.1%} [{s['ci'][0]:.0%},{s['ci'][1]:.0%}]"
            f"  BE {s['breakeven']:.1%}  flat {s['flat_profit']:+6.1f}u ROI {s['flat_roi']:+.1%} "
            f"[{s['roi_ci'][0]:+.0%},{s['roi_ci'][1]:+.0%}]  sized {s['unit_profit']:+6.1f}u/{s['units_staked']:.1f}u"
            f" ROI {s['unit_roi']:+.1%}")


def brier(rows, key, w=None):
    xs = [r for r in rows if r["result"] != "P" and r[key if w is None else "model_prob"] is not None]
    if w is None:
        ps = [r[key] for r in xs]
    else:
        ps = [w * r["model_prob"] + (1 - w) * r["market_prob"] for r in xs]
    ys = [1.0 if r["result"] == "W" else 0.0 for r in xs]
    # Market sims include push mass; renormalize to P(win | no push) for scoring.
    if key == "market_prob" and w is None:
        ps = [p / (1 - r["p_push"]) if r["p_push"] < 1 else p for p, r in zip(ps, xs)]
    return float(np.mean([(p - y) ** 2 for p, y in zip(ps, ys)])), len(xs)


def report(recs, fixed, diag, weeks):
    shipped = [r for r in recs if r["variant"] == "shipped"]
    bets = [r for r in shipped if r["units"] > 0]
    watch = [r for r in shipped if r["watch"]]
    units = lambda r: r["units"]  # noqa: E731
    print(f"\n=== Weeks {weeks[0]}-{weeks[-1]}: {len(shipped)} priced lines ({len(fixed) // 2} games x 2 markets) ===")
    print("Tier totals (sized = model units at closing price; BE = break-even hit rate at those prices)")
    print(line("Bets", summarize(bets, units)))
    print(line("Watch (flat 1u)", summarize(watch)))
    print(line("No-bet lines (best side)", summarize([r for r in shipped if r["units"] == 0 and not r["watch"]])))
    print(line("All priced (best side)", summarize(shipped)))

    print("\nBets split")
    for label, f in (("spreads", lambda r: r["kind"] == "spread"), ("totals", lambda r: r["kind"] == "total"),
                     ("  favorites", lambda r: r["kind"] == "spread" and r["fav"]),
                     ("  underdogs", lambda r: r["kind"] == "spread" and not r["fav"]),
                     ("  home side", lambda r: r["kind"] == "spread" and r["is_home"]),
                     ("  away side", lambda r: r["kind"] == "spread" and not r["is_home"]),
                     ("  overs", lambda r: r["side"] == "Over"), ("  unders", lambda r: r["side"] == "Under"),
                     ("1u or less", lambda r: r["units"] <= 1), ("1.5u+", lambda r: r["units"] >= 1.5),
                     ("weeks <=10 (fit half)", lambda r: r["week"] <= 10),
                     ("weeks >=11 (held-out)", lambda r: r["week"] >= 11)):
        print(line(label, summarize([r for r in bets if f(r)], units)))
    print("\nWatch split")
    for label, f in (("spreads", lambda r: r["kind"] == "spread"), ("totals", lambda r: r["kind"] == "total")):
        print(line(label, summarize([r for r in watch if f(r)])))

    print("\nSide lean across ALL priced lines (best side chosen by the model) and across bets")
    for kind, a, b in (("total", "Over", "Under"),):
        allk = [r for r in shipped if r["kind"] == kind]
        print(f"  totals: picked Over {sum(r['side'] == a for r in allk)} / Under {sum(r['side'] == b for r in allk)};"
              f" bets Over {sum(r['side'] == a for r in bets)} / Under {sum(r['side'] == b for r in bets)}")
    sp = [r for r in shipped if r["kind"] == "spread"]
    print(f"  spreads: picked fav {sum(r['fav'] for r in sp)} / dog {sum(not r['fav'] for r in sp)};"
          f" bets fav {sum(r['fav'] for r in bets if r['kind'] == 'spread')} / dog "
          f"{sum(not r['fav'] for r in bets if r['kind'] == 'spread')}; home {sum(r['is_home'] for r in sp)} / away "
          f"{sum(not r['is_home'] for r in sp)}")
    tot = [r for r in fixed if r["kind"] == "total" and r["result"] != "P"]
    print(f"  base rates: Over hit {np.mean([r['result'] == 'W' for r in tot]):.1%} of {len(tot)} totals;"
          f" home covered {np.mean([r['result'] == 'W' for r in fixed if r['kind'] == 'spread' and r['result'] != 'P']):.1%}")

    print("\nBy week (bets): n  W-L-P  sized profit | watch n W-L")
    for wk in weeks:
        b = [r for r in bets if r["week"] == wk]
        wt = [r for r in watch if r["week"] == wk]
        if not b and not wt:
            continue
        s = summarize(b, units, boot=0) if b else None
        bw = sum(r["result"] == "W" for r in wt)
        bl = sum(r["result"] == "L" for r in wt)
        bet_txt = f"{s['n']:2}  {s['W']}-{s['L']}-{s['P']}  {s['unit_profit']:+5.1f}u" if s else " 0"
        ov = sum(r["side"] == "Over" for r in b)
        un = sum(r["side"] == "Under" for r in b)
        print(f"  wk {wk:2}: {bet_txt:22} (O/U {ov}/{un}) | watch {len(wt)} {bw}-{bl}")

    print("\nCalibration, ALL priced lines (best side; blended p_win vs actual, pushes excluded)")
    bins = [0.40, 0.48, 0.50, 0.52, 0.54, 0.56, 0.60, 1.0]
    graded = [r for r in shipped if r["result"] != "P"]
    for lo, hi in zip(bins, bins[1:]):
        xs = [r for r in graded if lo <= r["p_win"] < hi]
        if xs:
            w = sum(r["result"] == "W" for r in xs)
            ci = wilson(w, len(xs))
            print(f"  p_win {lo:.2f}-{hi:.2f}: n={len(xs):3} predicted {np.mean([r['p_win'] for r in xs]):.1%}"
                  f"  actual {w / len(xs):.1%} [{ci[0]:.0%},{ci[1]:.0%}]")
    print("Calibration of the raw Sleeper model, fixed side (home cover / Over), no selection")
    fx = [r for r in fixed if r["result"] != "P" and r["model_prob"] is not None]
    for lo, hi in zip([0, 0.3, 0.4, 0.45, 0.5, 0.55, 0.6, 0.7], [0.3, 0.4, 0.45, 0.5, 0.55, 0.6, 0.7, 1.01]):
        xs = [r for r in fx if lo <= r["model_prob"] < hi]
        if xs:
            w = sum(r["result"] == "W" for r in xs)
            ci = wilson(w, len(xs))
            print(f"  model {lo:.2f}-{hi:.2f}: n={len(xs):3} predicted {np.mean([r['model_prob'] for r in xs]):.1%}"
                  f"  actual {w / len(xs):.1%} [{ci[0]:.0%},{ci[1]:.0%}]")

    print("\nBrier score, fixed side (lower is better; 0.25 = coin flip)")
    for kind in ("spread", "total"):
        xs = [r for r in fixed if r["kind"] == kind]
        parts = [f"market {brier(xs, 'market_prob')[0]:.4f}", f"Sleeper model {brier(xs, 'model_prob')[0]:.4f}",
                 f"ESPN check {brier(xs, 'check_prob')[0]:.4f}", f"blend 30% {brier(xs, None, 0.3)[0]:.4f}"]
        print(f"  {kind:6} (n={brier(xs, 'market_prob')[1]}): " + ", ".join(parts))

    print("\nOut-of-sample MODEL_WEIGHT check (fit Brier on weeks 4-10, score weeks 11-17; not shipped)")
    grid = np.round(np.arange(0, 1.01, 0.05), 2)
    for kind in ("spread", "total"):
        fit = [r for r in fixed if r["kind"] == kind and 4 <= r["week"] <= 10]
        val = [r for r in fixed if r["kind"] == kind and 11 <= r["week"] <= 17]
        if not fit or not val:
            continue
        best = min(grid, key=lambda w: brier(fit, None, w)[0])
        print(f"  {kind:6}: fitted w={best:.2f} | held-out Brier w=0 {brier(val, None, 0.0)[0]:.4f}, "
              f"w=0.30 (shipped) {brier(val, None, 0.3)[0]:.4f}, w={best:.2f} {brier(val, None, best)[0]:.4f}")

    print("\nWith vs without the ESPN check")
    nc = [r for r in recs if r["variant"] == "no_check"]
    nc_bets = [r for r in nc if r["units"] > 0]
    print(line("Bets, shipped (check)", summarize(bets, units)))
    print(line("Bets, no ESPN check", summarize(nc_bets, units)))
    key = lambda r: (r["game"], r["kind"])  # noqa: E731
    shipped_keys = {key(r) for r in bets}
    vetoed = [r for r in nc_bets if key(r) not in shipped_keys]
    print(line("  vetoed by the check", summarize(vetoed, units)))

    print("\nLeakage / skill diagnostic: who predicts the actual result better? (mean absolute error, points)")
    d = diag
    am, at = np.array([x["margin"] for x in d]), np.array([x["total"] for x in d])
    for label, mk, tk in (("closing line", "line_margin", "line_total"), ("Sleeper model", "model_margin", "model_total")):
        m, t = np.array([x[mk] for x in d]), np.array([x[tk] for x in d])
        print(f"  {label:14} margin MAE {np.mean(np.abs(am - m)):.2f} (corr {np.corrcoef(am, m)[0, 1]:.3f})"
              f"  total MAE {np.mean(np.abs(at - t)):.2f} (corr {np.corrcoef(at, t)[0, 1]:.3f})")
    e = [x for x in d if x["espn_margin"] is not None]
    if e:
        m = np.array([x["espn_margin"] for x in e])
        a = np.array([x["margin"] for x in e])
        print(f"  ESPN predictor margin MAE {np.mean(np.abs(a - m)):.2f} (corr {np.corrcoef(a, m)[0, 1]:.3f}, n={len(e)})")
    e = [x for x in d if x["espn_total"] is not None]
    if e:
        t = np.array([x["espn_total"] for x in e])
        a = np.array([x["total"] for x in e])
        print(f"  ESPN projections total MAE {np.mean(np.abs(a - t)):.2f} (corr {np.corrcoef(a, t)[0, 1]:.3f}, n={len(e)})")
    lm = np.array([x["line_margin"] for x in d])
    mm = np.array([x["model_margin"] for x in d])
    print(f"  Sleeper margin vs closing line: corr {np.corrcoef(lm, mm)[0, 1]:.3f}, MAE {np.mean(np.abs(lm - mm)):.2f},"
          f" spread of margins (sd) model {np.std(mm):.2f} vs line {np.std(lm):.2f}"
          f" (slope of model on line {np.polyfit(lm, mm, 1)[0]:.2f}; 1.0 = same scale)")
    lt = np.array([x["line_total"] for x in d])
    mt = np.array([x["model_total"] for x in d])
    print(f"  Sleeper total vs closing line: corr {np.corrcoef(lt, mt)[0, 1]:.3f}, sd model {np.std(mt):.2f} vs line"
          f" {np.std(lt):.2f} (slope {np.polyfit(lt, mt, 1)[0]:.2f}); mean model-line {np.mean(mt - lt):+.2f}")


def parse_weeks(text):
    a, _, b = text.partition("-")
    return list(range(int(a), int(b or a) + 1))


MODEL_WEIGHT = bm.GAME_MODEL_WEIGHT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2025)
    ap.add_argument("--weeks", default="1-18")
    ap.add_argument("--csv", help="write every priced line to this CSV")
    ap.add_argument("--model-weight", type=float, default=None,
                    help="game model weight (default: the shipped GAME_MODEL_WEIGHT; 0.30 reproduces the "
                         "2026-10-07 review, when the model still had weight)")
    args = ap.parse_args()
    global MODEL_WEIGHT
    if args.model_weight is not None:
        MODEL_WEIGHT = args.model_weight
    weeks = parse_weeks(args.weeks)
    recs, fixed, diag = run(args.season, weeks)
    report(recs, fixed, diag, weeks)
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(recs[0].keys()))
            w.writeheader()
            w.writerows(recs)


if __name__ == "__main__":
    main()
