"""Backtest the player-prop engine on real 2025 sportsbook lines.

The Odds API's historical endpoint (paid: 10 credits per market returned per
game, so ~50 a game for the five PROP_MARKETS) gives one pre-kickoff
snapshot of every book's prop lines. Those lines go through the shipped
pricing code -- betting_service.evaluate_player_prop with slate centering,
the anytime-TD de-vig, the zero-game chances and the ESPN check -- and every
priced line is graded against Sleeper's actual stats. This is the test the
graded weeks can't give fast enough: the 70/30 blend, the 3% EV bar, the
ESPN check and calibration, out of sample (BETTING_GUIDE section 9).

    # spend credits (every response cached; a cached game is never refetched)
    python scripts/backtest_props.py fetch --season 2025 --week 11 --max-games 5 --max-credits 260
    # price + grade whatever is cached (free)
    python scripts/backtest_props.py run --season 2025

Credit rules: the fetch stops before a call that could take the spend past
--max-credits or the account below RESERVE (2,000). The request URL carries
the key, so it is never printed or logged.

Reconstruction choices:
- Snapshot SNAPSHOT_LEAD before each kickoff (near the close: the strictest
  test; live, a game's props are fetched up to 36h earlier).
- Slate centering and the TD scale's slate median use the cached games of
  that week only (live: the whole week's not-yet-started slate).
- The game total for the TD de-vig is nflverse's closing total (live: the
  seven-book consensus at the time of the board).
- Zero-catch/zero-rush chances come from the week's Sleeper projections, as
  live.
"""
import argparse
import asyncio
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from app.core.config import settings  # noqa: E402
from app.services import betting_model as bm  # noqa: E402
from app.services import betting_service as bs  # noqa: E402
from app.services import odds_service  # noqa: E402
from app.services.betting_tracking import prop_outcome  # noqa: E402
from app.services.weekly_projections import normalize_name  # noqa: E402
from backtest_game_lines import FULL_NAME, espn_projections, load_games  # noqa: E402
from backtest_projections import CACHE, _get  # noqa: E402

HIST = os.path.join(CACHE, "odds_hist")
API = "https://api.the-odds-api.com/v4/historical/sports/americanfootball_nfl"
RESERVE = 2000
SNAPSHOT_LEAD = timedelta(hours=3)
COST_PER_MARKET = 10


# ---------------------------------------------------------------------------
# Fetch (credits)
# ---------------------------------------------------------------------------

class Budget:
    def __init__(self, max_credits: int):
        self.max, self.spent, self.remaining = max_credits, 0, None

    def allows(self, cost: int) -> bool:
        if self.spent + cost > self.max:
            return False
        return self.remaining is None or self.remaining - cost >= RESERVE


def _hist_get(path: str, params: dict, budget: Budget):
    query = urllib.parse.urlencode({"apiKey": settings.ODDS_API_KEY, **params})
    req = urllib.request.Request(f"{API}{path}?{query}", headers={"User-Agent": "ff-assistant-backtest"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
            headers = r.headers
    except urllib.error.HTTPError as e:  # never print the URL: it carries the key
        print(f"  Odds API {path} failed: HTTP {e.code}")
        return None
    last, remaining = headers.get("x-requests-last"), headers.get("x-requests-remaining")
    if last is not None:
        budget.spent += int(float(last))
    if remaining is not None:
        budget.remaining = int(float(remaining))
    print(f"  {path.rsplit('/', 1)[-1]}: cost {last}, spent {budget.spent}, account {budget.remaining}")
    return data


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def week_rows(season: int, week: int):
    return [r for r in load_games(season) if int(r["week"]) == week]


def _kickoff_utc(r) -> datetime:
    """nflverse gameday + gametime are US Eastern."""
    from zoneinfo import ZoneInfo
    local = datetime.strptime(f"{r['gameday']} {r['gametime']}", "%Y-%m-%d %H:%M")
    return local.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)


def fetch(season: int, week: int, max_games: int, max_credits: int):
    if not settings.ODDS_API_KEY:
        sys.exit("ODDS_API_KEY is not set")
    os.makedirs(HIST, exist_ok=True)
    budget = Budget(max_credits)
    rows = sorted(week_rows(season, week), key=lambda r: (_kickoff_utc(r), r["game_id"]))
    ev_path = os.path.join(HIST, f"events_{season}_{week}.json")
    if not os.path.exists(ev_path):
        first = _kickoff_utc(rows[0]) - timedelta(hours=12)
        if not budget.allows(1):
            sys.exit("Budget doesn't allow the event list call")
        data = _hist_get("/events", {"date": _iso(first)}, budget)
        if not data:
            sys.exit("No event list")
        with open(ev_path, "w") as f:
            json.dump(data, f)
    with open(ev_path) as f:
        events = json.load(f).get("data") or []
    by_teams = {(e["home_team"], e["away_team"]): e for e in events}

    done = 0
    for r in rows:
        if done >= max_games:
            break
        ev = by_teams.get((FULL_NAME[odds_service.normalize_team(r["home_team"])],
                           FULL_NAME[odds_service.normalize_team(r["away_team"])]))
        if not ev:
            print(f"  {r['game_id']}: not in the event list")
            continue
        path = os.path.join(HIST, f"props_{r['game_id']}.json")
        if os.path.exists(path):
            done += 1
            continue
        cost = COST_PER_MARKET * len(odds_service.PROP_MARKETS)
        if not budget.allows(cost):
            print(f"  Stopping: next game could cost {cost} (spent {budget.spent}/{budget.max}, account {budget.remaining})")
            break
        snap = _kickoff_utc(r) - SNAPSHOT_LEAD
        data = _hist_get(f"/events/{ev['id']}/odds", {
            "date": _iso(snap),
            "bookmakers": ",".join(odds_service.PROP_BOOKMAKERS),
            "markets": ",".join(odds_service.PROP_MARKETS),
            "oddsFormat": "american",
        }, budget)
        if not data or not data.get("data"):
            print(f"  {r['game_id']}: no data")
            continue
        with open(path, "w") as f:
            json.dump({**data, "game_id": r["game_id"], "kickoff": _iso(_kickoff_utc(r))}, f)
        books = {b["key"] for b in data["data"].get("bookmakers") or []}
        print(f"  {r['game_id']}: snapshot {data.get('timestamp')}, books {sorted(books)}")
        done += 1
    print(f"Done: {done} games cached for {season} week {week}; spent {budget.spent} credits; account {budget.remaining}")


# ---------------------------------------------------------------------------
# Price + grade (free)
# ---------------------------------------------------------------------------

def _index(rows):
    """{(normalized name, team): stats} -- betting_service._projection_index's keys."""
    return bs._projection_index(rows)


def price_week(season: int, week: int, cached, games_csv, books: str):
    """Every cached prop of one week through the shipped engine, the way
    _build_board_now prices it. `books` is BETTING_MY_BOOKS ("" = all)."""
    settings.BETTING_MY_BOOKS = books
    projections = _index(_get("projections", season, week))
    actual = _index(_get("stats", season, week))
    espn = dict(espn_projections(season, week) or {})
    totals = {r["game_id"]: float(r["total_line"]) for r in games_csv}

    matched = []
    bs._zero_catch.clear()
    bs._zero_rush.clear()
    for gid, event in cached:
        g = {"home_team": event["home_team"], "away_team": event["away_team"]}
        teams = (bs._team(g["home_team"]), bs._team(g["away_team"]))
        for (player, market), offers in bs._group_offers(event).items():
            team = next((t for t in teams if projections.get((normalize_name(player), t)) is not None), None)
            stats = projections.get((normalize_name(player), team)) if team else None
            mean = bs._projected_mean(stats, market) if stats else None
            if mean is None or mean <= 0:
                continue
            matched.append((gid, team, player, market, offers, mean))
            if market in bm.ZERO_CATCH_MARKETS:
                p0 = bm.zero_catch_prob(bs._projected_mean(stats, "player_receptions"))
                if p0 is not None:
                    bs._zero_catch[normalize_name(player)] = p0
            elif market == "player_rush_yds":
                p0 = bm.zero_rush_prob(mean)
                if p0 is not None:
                    bs._zero_rush[normalize_name(player)] = p0
    espn_means = {(pl, m): bs._projected_mean(espn[normalize_name(pl)], m)
                  for _, _, pl, m, _, _ in matched if normalize_name(pl) in espn}

    td_scales = {}
    for gid, event in cached:
        implied = [p for (_, m), offers in bs._group_offers(event).items() if m == "player_anytime_td"
                   for p in [bs._td_implied(bs._td_yes_prices(offers["books"]))] if p is not None]
        td_scales[gid] = bm.td_rate_scale(implied, totals.get(gid))
    slate = bm.median(v for v in td_scales.values() if v is not None)
    td_scales = {k: (v if v is not None else slate) for k, v in td_scales.items()}

    centers, espn_centers = defaultdict(list), defaultdict(list)
    for gid, _, player, market, offers, mean in matched:
        c = bs.market_center(market, offers, td_scales.get(gid))
        if c is None:
            continue
        centers[market].append((mean, c, bs._p_zero(player, market)))
        e = espn_means.get((player, market))
        if e:
            espn_centers[market].append((e, c, bs._p_zero(player, market)))
    scales = {m: bm.fit_projection_scale(m, pairs) for m, pairs in centers.items()}
    espn_scales = {m: bm.fit_projection_scale(m, pairs) for m, pairs in espn_centers.items()}

    out = []
    for gid, team, player, market, offers, mean in matched:
        st = actual.get((normalize_name(player), team))
        if st is None or not st.get("gp"):
            continue  # didn't play: books void these
        value = bs._projected_mean(st, market) or 0.0
        seed = f"{week}|{player}|{market}"
        espn_p = espn_means.get((player, market))
        rec = bs.evaluate_player_prop(player, market, offers, mean, seed, scales.get(market, 1.0),
                                      td_scales.get(gid), espn_p, espn_scales.get(market, 1.0))
        if not rec:
            continue
        no_espn = bs.evaluate_player_prop(player, market, offers, mean, seed, scales.get(market, 1.0),
                                          td_scales.get(gid))
        # Calibration at the market's own line: the books' fair chance vs the
        # engine's (Sleeper, ESPN), each before blending.
        samples = bs._sim(market, mean * scales.get(market, 1.0), seed, player)
        espn_s = (bs._sim(market, espn_p * espn_scales.get(market, 1.0), f"{seed}|espn", player)
                  if espn_p and espn_p > 0 else None)
        if market == "player_anytime_td":
            line, p_book = None, bs.market_center(market, offers, td_scales.get(gid))
            side = "Yes"
        else:
            line = rec["market_line"]
            p_book, side = bs._fair_over(offers["books"])[line], "Over"
        o = prop_outcome(market, "Over" if side == "Yes" else side, line, value)
        calib = None if o == "push" or p_book is None else {
            "hit": o == "won", "p_book": p_book, "p_sleeper": bs._side_prob(samples, side, line),
            "p_espn": bs._side_prob(espn_s, side, line) if espn_s is not None else None}
        out.append({"week": week, "game": gid, "player": player, "market": market, "actual": value,
                    "rec": rec, "no_espn": no_espn, "calib": calib,
                    "outlier": rec["projection_outlier"]})
    return out, scales


def _settle(rec, actual, market):
    o = prop_outcome(market, "Over" if rec["side"] == "Yes" else rec["side"], rec["line"], actual)
    pnl = {"won": bm.american_to_decimal(rec["price"]) - 1, "lost": -1.0}.get(o, 0.0)
    return o, pnl


def _record(rows, key="rec"):
    bets = [(r[key], *_settle(r[key], r["actual"], r["market"])) for r in rows if r[key] and r[key]["units"] > 0]
    w = sum(1 for _, o, _ in bets if o == "won")
    lo = sum(1 for _, o, _ in bets if o == "lost")
    staked = sum(b["units"] for b, o, _ in bets if o in ("won", "lost"))
    pl = sum(b["units"] * p for b, _, p in bets)
    flat = sum(p for _, o, p in bets if o in ("won", "lost"))
    pred = np.mean([b["p_win"] for b, _, _ in bets]) if bets else float("nan")
    return {"n": len(bets), "w": w, "l": lo, "staked": staked, "pl": pl, "flat": flat, "pred": pred}


def _fmt(label, s):
    if not s["n"]:
        return f"  {label:34} no bets"
    roi = s["pl"] / s["staked"] if s["staked"] else float("nan")
    return (f"  {label:34} {s['w']}-{s['l']} (n={s['n']}), predicted {s['pred']:.1%}, hit "
            f"{s['w'] / max(1, s['w'] + s['l']):.1%}; {s['pl']:+.2f}u on {s['staked']:.1f}u ({roi:+.1%}); "
            f"flat 1u each {s['flat']:+.2f}u")


def _brier(rows, field, weight=None):
    xs = [(r["calib"][field] if weight is None else bm.blend(r["calib"]["p_sleeper"], r["calib"]["p_book"], weight),
           r["calib"]["hit"]) for r in rows if r["calib"] and (weight is not None or r["calib"][field] is not None)]
    return np.mean([(p - y) ** 2 for p, y in xs]) if xs else float("nan"), len(xs)


TRAIN_WEEKS = range(1, 10)  # fit here, score on the rest (no peeking)
WEIGHTS = np.round(np.arange(0, 1.01, 0.05), 2)


def _boot_ci(values_by_game, stat, n=2000, seed=7):
    """95% CI of stat(list of values), resampling whole games (props in one
    game are correlated)."""
    rng = np.random.default_rng(seed)
    games = list(values_by_game)
    out = []
    for _ in range(n):
        pick = rng.integers(0, len(games), len(games))
        out.append(stat([v for i in pick for v in values_by_game[games[i]]]))
    return np.percentile(out, [2.5, 97.5])


def heldout(rows):
    cal = [r for r in rows if r["calib"]]
    train = [r for r in cal if r["week"] in TRAIN_WEEKS]
    test = [r for r in cal if r["week"] not in TRAIN_WEEKS]
    if not train or not test:
        print("\n(held-out split needs weeks on both sides of", TRAIN_WEEKS, ")")
        return
    print(f"\n=== Held-out: fit on weeks {TRAIN_WEEKS.start}-{TRAIN_WEEKS.stop - 1} ({len(train)} props), "
          f"scored on the rest ({len(test)}) ===")
    for m in odds_service.PROP_MARKETS + (None,):
        tr = [r for r in train if m is None or r["market"] == m]
        te = [r for r in test if m is None or r["market"] == m]
        if not tr or not te:
            continue
        best = min(WEIGHTS, key=lambda w: _brier(tr, None, w)[0])
        by_game = defaultdict(list)
        for r in te:
            c = r["calib"]
            d = (bm.blend(c["p_sleeper"], c["p_book"], best) - c["hit"]) ** 2 - (bm.blend(c["p_sleeper"], c["p_book"], 0.3) - c["hit"]) ** 2
            by_game[r["game"]].append(d)
        diff = np.mean([d for v in by_game.values() for d in v])
        lo, hi = _boot_ci(by_game, np.mean)
        print(f"  {(m or 'all').replace('player_', ''):14} best w on train {best:.2f}; test Brier books {_brier(te, 'p_book')[0]:.4f}, "
              f"w=0.3 {_brier(te, None, 0.3)[0]:.4f}, w={best:.2f} {_brier(te, None, best)[0]:.4f} "
              f"(diff vs 0.3 {diff:+.5f} [{lo:+.5f}, {hi:+.5f}])")

    print("\n  Flat 1u on the engine's best side, by its EV (all props, units or not), test weeks:")
    for label, sel in (("ESPN agrees or n/a", lambda r: r["rec"].get("espn_agrees") is not False),
                       ("ESPN disagrees", lambda r: r["rec"].get("espn_agrees") is False)):
        for lo_, hi_ in ((0, 0.03), (0.03, 0.05), (0.05, 0.08), (0.08, 0.15), (0.15, 9)):
            picks = [r for r in rows if r["week"] not in TRAIN_WEEKS and r["rec"]["model_agrees"]
                     and not r["outlier"] and sel(r) and lo_ <= r["rec"]["ev"] < hi_]
            by_game = defaultdict(list)
            for r in picks:
                o, pnl = _settle(r["rec"], r["actual"], r["market"])
                if o in ("won", "lost"):
                    by_game[r["game"]].append(pnl)
            vals = [v for vs in by_game.values() for v in vs]
            if len(vals) < 10:
                continue
            ci = _boot_ci(by_game, np.mean)
            name = f"EV {lo_:.0%}-{hi_:.0%}" if hi_ < 9 else f"EV {lo_:.0%}+"
            print(f"    {label:20} {name:9} n={len(vals):5d} ROI {np.mean(vals):+.1%} [{ci[0]:+.1%}, {ci[1]:+.1%}]")

    print("\n  Over/Under lean, all weeks (books' fair P(over) at their line vs how often it went over):")
    for m in odds_service.PROP_MARKETS[:4]:
        sel = [r["calib"] for r in cal if r["market"] == m]
        if sel:
            print(f"    {m.replace('player_', ''):14} n={len(sel):5d} books said {np.mean([c['p_book'] for c in sel]):.1%} "
                  f"over, went over {np.mean([c['hit'] for c in sel]):.1%}")


def run(season: int):
    games_csv = load_games(season)
    week_of = {r["game_id"]: int(r["week"]) for r in games_csv}
    by_week = defaultdict(list)
    for name in sorted(os.listdir(HIST)):
        if name.startswith("props_"):
            with open(os.path.join(HIST, name)) as f:
                d = json.load(f)
            if d["game_id"] in week_of:
                by_week[week_of[d["game_id"]]].append((d["game_id"], d["data"]))
    if not by_week:
        sys.exit("Nothing cached: run fetch first")
    for books, label in (("", "any book"), ("hardrockbet", "Hard Rock only")):
        rows = []
        if books == "hardrockbet":
            heldout(all_rows)
        for week, cached in sorted(by_week.items()):
            priced, scales = price_week(season, week, cached, [r for r in games_csv if int(r["week"]) == week], books)
            rows += priced
            if books == "":
                print(f"Week {week}: {len(cached)} games, {len(priced)} priced props (played); centering "
                      + ", ".join(f"{m.replace('player_', '')} x{v:.2f}" for m, v in sorted(scales.items())))
        if books == "":
            all_rows = rows
        print(f"\n=== Bets, units at {label} ===")
        print(_fmt("Shipped engine (ESPN check on)", _record(rows)))
        print(_fmt("Without the ESPN check", _record(rows, "no_espn")))
        vetoed = [r for r in rows if r["no_espn"] and r["no_espn"]["units"] > 0 and r["rec"]["units"] == 0]
        print(_fmt("Vetoed by the ESPN check", _record(vetoed, "no_espn")))
        for m in odds_service.PROP_MARKETS:
            print(_fmt(m, _record([r for r in rows if r["market"] == m])))
        for side in ("Over", "Under", "Yes"):
            print(_fmt(f"side {side}", _record([r for r in rows if r["rec"]["side"] == side])))
        for lo, hi in ((0.03, 0.05), (0.05, 0.08), (0.08, 9)):
            print(_fmt(f"EV {lo:.0%}-{hi:.0%}" if hi < 9 else f"EV {lo:.0%}+",
                       _record([r for r in rows if lo <= r["rec"]["ev"] < hi])))
        watch = [r for r in rows if r["rec"].get("watch")]
        ws = [_settle(r["rec"], r["actual"], r["market"]) for r in watch]
        if ws:
            print(f"  Watch list: {sum(o == 'won' for o, _ in ws)}-{sum(o == 'lost' for o, _ in ws)}, "
                  f"flat 1u {sum(p for _, p in ws):+.2f}u")

    print("\n=== Calibration at the books' line (Over / Yes), Brier, lower is better ===")
    for m in odds_service.PROP_MARKETS + (None,):
        sel = [r for r in rows if m is None or r["market"] == m]
        b, n = _brier(sel, "p_book")
        cells = [f"books {b:.4f}", f"Sleeper {_brier(sel, 'p_sleeper')[0]:.4f}",
                 f"ESPN {_brier(sel, 'p_espn')[0]:.4f}"]
        cells += [f"w={w:.1f} {_brier(sel, None, w)[0]:.4f}" for w in (0.1, 0.2, 0.3, 0.5)]
        print(f"  {(m or 'all').replace('player_', ''):16} n={n:4d}  " + "  ".join(cells))
    print("\n  Blend (w=0.3) said vs hit, all markets:")
    pts = [(bm.blend(r["calib"]["p_sleeper"], r["calib"]["p_book"]), r["calib"]["hit"]) for r in rows if r["calib"]]
    for lo, hi in ((0, 0.3), (0.3, 0.45), (0.45, 0.55), (0.55, 0.7), (0.7, 1.01)):
        sel = [(p, y) for p, y in pts if lo <= p < hi]
        if sel:
            print(f"    {lo:.0%}-{min(hi, 1):.0%}: n={len(sel):4d} said {np.mean([p for p, _ in sel]):.1%} "
                  f"hit {np.mean([y for _, y in sel]):.1%}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--season", type=int, default=2025)
    f.add_argument("--week", type=int, required=True)
    f.add_argument("--max-games", type=int, default=99)
    f.add_argument("--max-credits", type=int, required=True)
    r = sub.add_parser("run")
    r.add_argument("--season", type=int, default=2025)
    args = ap.parse_args()
    if args.cmd == "fetch":
        fetch(args.season, args.week, args.max_games, args.max_credits)
    else:
        run(args.season)


if __name__ == "__main__":
    main()
