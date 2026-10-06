"""This week's betting board: player props and game lines priced against
the de-vigged market and (for player props) a Monte Carlo of Sleeper's
projected stat lines -- see betting_model.py for the method.

Data: The Odds API (odds_service) for DraftKings / FanDuel / Hard Rock Bet
prices (PrizePicks lines shown alongside player props); Sleeper's weekly
projections for each player's expected stat line. A prop with no matching
projection is skipped, never guessed at.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.services import betting_model as bm
from app.services import odds_service
from app.services.sleeper_service import sleeper_service
from app.services.weekly_projections import fetch_weekly_projections, normalize_name

logger = logging.getLogger(__name__)

MARKET_LABELS = {
    "player_pass_yds": "Passing yards",
    "player_rush_yds": "Rushing yards",
    "player_reception_yds": "Receiving yards",
    "player_receptions": "Receptions",
    "player_anytime_td": "Anytime TD",
}
# Sleeper projected-stat key(s) behind each market's mean.
MARKET_STATS = {
    "player_pass_yds": ("pass_yd",),
    "player_rush_yds": ("rush_yd",),
    "player_reception_yds": ("rec_yd",),
    "player_receptions": ("rec",),
    "player_anytime_td": ("rush_td", "rec_td"),
}
BOOK_LABELS = {"draftkings": "DraftKings", "fanduel": "FanDuel", "hardrockbet": "Hard Rock Bet", "prizepicks": "PrizePicks"}

DISCLAIMER = (
    "For entertainment and research. These are model estimates, not guarantees -- markets are efficient "
    "and most edges are small. 1 unit = 1% of your bankroll; never bet more than you can afford to lose. "
    "Must be 21+ and in a state where sports betting is legal. Gambling problem? Call 1-800-GAMBLER."
)
METHOD = (
    "Player props: a Monte Carlo simulation of Sleeper's projected stat line, including uncertainty in "
    "the projection itself, blended 30/70 with the de-vigged consensus of DraftKings, FanDuel and Hard Rock "
    "Bet. Game lines: simulations centered on the consensus spread and total, so they flag only books off "
    "the market. Stakes are quarter-Kelly, capped at 3 units, and only when expected value is at least 3% "
    "and the model agrees with the side."
)

_BOARD_TTL_SECONDS = 15 * 60
_board_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_PROP_CONCURRENCY = 4


def _team(name: Optional[str]) -> Optional[str]:
    return odds_service.TEAM_ABBR.get(name or "")


def _projection_index(rows: List[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in rows:
        p = r.get("player") or {}
        name = normalize_name(f"{p.get('first_name', '')} {p.get('last_name', '')}")
        team = odds_service.normalize_team(r.get("team") or p.get("team"))
        if name and team:
            out[(name, team)] = r.get("stats") or {}
    return out


def _projected_mean(stats: Dict[str, Any], market: str) -> Optional[float]:
    keys = MARKET_STATS[market]
    if not any(stats.get(k) is not None for k in keys):
        return None
    return float(sum(float(stats.get(k) or 0.0) for k in keys))


# ---------------------------------------------------------------------------
# Player props
# ---------------------------------------------------------------------------

def _group_offers(event: Dict[str, Any]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """{(player, market): {"books": {book: {point: {side: price}}}, "prizepicks": point}}"""
    grouped: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for book in event.get("bookmakers") or []:
        bkey = book.get("key")
        for market in book.get("markets") or []:
            mkey = market.get("key")
            if mkey not in MARKET_STATS:
                continue
            for o in market.get("outcomes") or []:
                player = o.get("description")
                if not player or o.get("price") is None:
                    continue
                g = grouped.setdefault((player, mkey), {"books": {}, "prizepicks": None})
                if bkey == "prizepicks":
                    if o.get("point") is not None:
                        g["prizepicks"] = float(o["point"])
                    continue
                point = float(o["point"]) if o.get("point") is not None else None
                g["books"].setdefault(bkey, {}).setdefault(point, {})[o.get("name")] = float(o["price"])
    return grouped


def evaluate_player_prop(
    player: str,
    market: str,
    offers: Dict[str, Any],
    mean: float,
    seed: str,
) -> Optional[Dict[str, Any]]:
    """Best-priced side of one player prop, priced by the blended model.
    None when no book quotes a usable market."""
    books = offers["books"]
    samples = bm.simulate_stat(market, mean, seed)

    candidates: List[Dict[str, Any]] = []
    if market == "player_anytime_td":
        yes_prices = {b: pts[None]["Yes"] for b, pts in books.items() if None in pts and "Yes" in pts[None]}
        if not yes_prices:
            return None
        p_market = bm.median(bm.implied_prob(p) for p in yes_prices.values()) / (1 + bm.ONE_SIDED_HOLD)
        p_model = float((samples >= 1).mean())
        for book, price in yes_prices.items():
            candidates.append(_candidate("Yes", None, book, price, p_model, p_market, 0.0))
    else:
        # Market fair P(over) at each line, averaged across books quoting both sides there.
        fair_over: Dict[float, float] = {}
        for point in {pt for pts in books.values() for pt in pts if pt is not None}:
            pairs = [pts[point] for pts in books.values() if point in pts and {"Over", "Under"} <= set(pts[point])]
            if pairs:
                fair_over[point] = bm.median(bm.devig_pair(s["Over"], s["Under"])[0] for s in pairs)
        if not fair_over:
            return None
        for book, pts in books.items():
            for point, sides in pts.items():
                if point not in fair_over:
                    continue
                p_over, p_push = bm.prob_over(samples, point)
                for side, price in sides.items():
                    if side == "Over":
                        candidates.append(_candidate(side, point, book, price, p_over, fair_over[point], p_push))
                    elif side == "Under":
                        p_under = max(0.0, 1 - p_over - p_push)
                        candidates.append(_candidate(side, point, book, price, p_under, 1 - fair_over[point], p_push))
    if not candidates:
        return None
    if market == "player_anytime_td":
        market_line, outlier = None, bm.projection_outlier(market, mean, market_td_prob=p_market)
    else:
        # The market's center: the quoted line whose fair P(over) is closest to 50%.
        market_line = min(fair_over, key=lambda pt: abs(fair_over[pt] - 0.5))
        outlier = bm.projection_outlier(market, mean, market_line=market_line)
    if outlier:
        candidates = [{**c, "units": 0.0, "confidence": "none"} for c in candidates]
    best = max(candidates, key=lambda c: c["ev"])
    return {
        "market_line": market_line,
        # Projection far from the market -- most likely a stale projection,
        # so no units (see betting_model.projection_outlier).
        "projection_outlier": outlier,
        "type": "player_prop",
        "player": player,
        "market": market,
        "market_label": MARKET_LABELS[market],
        "projection": round(mean, 2),
        "prizepicks_line": offers.get("prizepicks"),
        "books_quoting": len(books),
        **best,
    }


def _candidate(side, point, book, price, p_model, p_market, p_push) -> Dict[str, Any]:
    p = bm.blend(p_model, p_market)
    priced = bm.price_offer(p, price, p_push)
    # The model must agree with the side; a market-only "edge" is just vig noise.
    if p_model <= p_market:
        priced = {**priced, "units": 0.0, "confidence": "none"}
    return {
        "side": side,
        "line": point,
        "book": BOOK_LABELS.get(book, book),
        "price": int(price),
        "model_prob": round(p_model, 4),
        "market_prob": round(p_market, 4),
        **priced,
    }


# ---------------------------------------------------------------------------
# Game lines
# ---------------------------------------------------------------------------

def evaluate_game(game: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Best-priced side of the spread and the total for one game."""
    home, away = game.get("home_team"), game.get("away_team")
    spreads: List[Tuple[str, str, float, float]] = []   # (book, team, point, price)
    totals: List[Tuple[str, str, float, float]] = []    # (book, Over/Under, point, price)
    for book in game.get("bookmakers") or []:
        for m in book.get("markets") or []:
            for o in m.get("outcomes") or []:
                if o.get("point") is None or o.get("price") is None:
                    continue
                row = (book["key"], o["name"], float(o["point"]), float(o["price"]))
                (spreads if m.get("key") == "spreads" else totals if m.get("key") == "totals" else []).append(row)
    home_spread = bm.median(pt for _, team, pt, _ in spreads if team == home)
    total_line = bm.median(pt for _, side, pt, _ in totals if side == "Over")
    if home_spread is None or total_line is None:
        return []
    margin, total = bm.simulate_game(home_spread, total_line, f"{game.get('id')}|game")
    label = f"{_team(away) or away} @ {_team(home) or home}"
    out = []

    def best_of(rows, kind):
        cands = []
        for book, name, point, price in rows:
            if kind == "spread":
                diff = (margin if name == home else -margin) + point
            else:
                diff = (total - point) if name == "Over" else (point - total)
            p_win, p_push = float((diff > 0).mean()), float((diff == 0).mean())
            priced = bm.price_offer(p_win, price, p_push)
            side = (_team(name) or name) if kind == "spread" else name
            cands.append({"side": side, "line": point, "book": BOOK_LABELS.get(book, book), "price": int(price),
                          "model_prob": round(p_win, 4), "market_prob": None, **priced})
        return max(cands, key=lambda c: c["ev"]) if cands else None

    for kind, rows, consensus in (("spread", spreads, home_spread), ("total", totals, total_line)):
        best = best_of(rows, kind)
        if best:
            out.append({
                "type": "game",
                "game": label,
                "kickoff": game.get("commence_time"),
                "market": kind,
                "market_label": "Spread" if kind == "spread" else "Total",
                "consensus_line": consensus,
                "books_quoting": len({r[0] for r in rows}),
                **best,
            })
    return out


# ---------------------------------------------------------------------------
# Board
# ---------------------------------------------------------------------------

async def build_board(force: bool = False) -> Dict[str, Any]:
    cached = _board_cache.get("board")
    if cached and not force and time.monotonic() - cached[0] < _BOARD_TTL_SECONDS:
        return cached[1]

    from app.core.config import settings
    if not settings.ODDS_API_KEY:
        return {"available": False, "detail": "Betting odds aren't configured (ODDS_API_KEY is not set).",
                "disclaimer": DISCLAIMER}

    now = datetime.now(timezone.utc)
    games = odds_service.this_week(await odds_service.get_game_lines(), now)
    state = await sleeper_service.get_nfl_state()
    week = state.get("week") if isinstance(state, dict) else None
    season = int(state.get("season") or now.year) if isinstance(state, dict) else now.year
    if not games or not week:
        return {"available": False, "detail": "No NFL lines available right now.", "disclaimer": DISCLAIMER}

    rows = await fetch_weekly_projections(season, int(week))
    projections = _projection_index(rows)

    sem = asyncio.Semaphore(_PROP_CONCURRENCY)

    async def props_for(g):
        async with sem:
            return g, await odds_service.get_event_props(g["id"])

    fetched = await asyncio.gather(*(props_for(g) for g in games))

    player_props: List[Dict[str, Any]] = []
    games_without_props: List[str] = []
    unmatched = 0
    for g, event in fetched:
        teams = {_team(g.get("home_team")), _team(g.get("away_team"))}
        label = f"{_team(g.get('away_team'))} @ {_team(g.get('home_team'))}"
        if not event:
            games_without_props.append(label)
            continue
        for (player, market), offers in _group_offers(event).items():
            stats = next((projections.get((normalize_name(player), t)) for t in teams
                          if projections.get((normalize_name(player), t)) is not None), None)
            mean = _projected_mean(stats, market) if stats else None
            if mean is None or mean <= 0:
                unmatched += 1
                continue
            rec = evaluate_player_prop(player, market, offers, mean, f"{week}|{player}|{market}")
            if rec:
                rec["game"] = label
                rec["kickoff"] = g.get("commence_time")
                player_props.append(rec)

    game_props = [rec for g in games for rec in evaluate_game(g)]

    def ranked(recs):
        return sorted(recs, key=lambda r: (-r["units"], -r["ev"]))

    board = {
        "available": True,
        "week": week,
        "season": season,
        "generated_at": now.isoformat(),
        "player_props": ranked(player_props),
        "game_props": ranked(game_props),
        "recommended_count": sum(1 for r in player_props + game_props if r["units"] > 0),
        "evaluated": {"player_props": len(player_props), "games": len(games), "props_without_projection": unmatched},
        "games_without_props": games_without_props,
        "credits_remaining": await odds_service.credits_remaining_async(),
        "sources": {"odds": odds_service.SOURCE, "projections": "Sleeper (RotoWire) weekly projections"},
        "method": METHOD,
        "disclaimer": DISCLAIMER,
    }
    _board_cache["board"] = (time.monotonic(), board)
    return board
