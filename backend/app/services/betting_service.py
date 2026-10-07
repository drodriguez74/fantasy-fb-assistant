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

import numpy as np

from app.services import betting_model as bm
from app.services.betting_tracking import record_board
from app.services.espn_projections import fetch_espn_weekly_projections
from app.services import prizepicks_board
from app.services.espn_game_predictor import fetch_home_win_probs
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
    "the projection itself. Each week, projections for each stat are rescaled so the model agrees with the "
    "market on the typical prop -- edges come from players projected unusually far from their line. ESPN's "
    "projection must also favor the side over the market, or the bet gets no units. Blended 30/70 with the de-vigged consensus of DraftKings, FanDuel and Hard Rock "
    "Bet. Game lines: projected scores from Sleeper's player projections (touchdowns and kicker points), "
    "blended 30/70 with the consensus, with ESPN's matchup predictor and player projections as the cross-check. "
    "Stakes are quarter-Kelly, capped at 3 units, and only when expected value is at least 3% "
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


def _fair_over(books: Dict[str, Any]) -> Dict[float, float]:
    """Market fair P(over) at each line, averaged across books quoting both sides there."""
    fair: Dict[float, float] = {}
    for point in {pt for pts in books.values() for pt in pts if pt is not None}:
        pairs = [pts[point] for pts in books.values() if point in pts and {"Over", "Under"} <= set(pts[point])]
        if pairs:
            fair[point] = bm.median(bm.devig_pair(s["Over"], s["Under"])[0] for s in pairs)
    return fair


def _td_yes_prices(books: Dict[str, Any]) -> Dict[str, float]:
    return {b: pts[None]["Yes"] for b, pts in books.items() if None in pts and "Yes" in pts[None]}


def _td_implied(yes_prices: Dict[str, float]) -> Optional[float]:
    return bm.median(bm.implied_prob(p) for p in yes_prices.values())


def _td_market_prob(yes_prices: Dict[str, float], td_scale: Optional[float]) -> Optional[float]:
    p = _td_implied(yes_prices)
    return bm.td_fair_prob(p, td_scale) if p is not None else None


def market_center(market: str, offers: Dict[str, Any], td_scale: Optional[float] = None) -> Optional[float]:
    """The market's 50% line (yards, receptions) or fair P(score) (anytime TD)."""
    if market == "player_anytime_td":
        return _td_market_prob(_td_yes_prices(offers["books"]), td_scale)
    fair = _fair_over(offers["books"])
    return min(fair, key=lambda pt: abs(fair[pt] - 0.5)) if fair else None


def evaluate_player_prop(
    player: str,
    market: str,
    offers: Dict[str, Any],
    mean: float,
    seed: str,
    scale: float = 1.0,
    td_scale: Optional[float] = None,
    espn_projection: Optional[float] = None,
    espn_scale: float = 1.0,
) -> Optional[Dict[str, Any]]:
    """Best-priced side of one player prop, priced by the blended model.
    `scale` is this slate's centering factor for the market (betting_model.
    fit_projection_scale); `td_scale` is the game's TD rate scale
    (betting_model.td_rate_scale). `espn_projection` (centered by
    `espn_scale`) is the second opinion: a side ESPN doesn't also favor over
    the market gets no units. None when no book quotes a usable market."""
    books = offers["books"]
    projection, mean = mean, mean * scale
    samples = bm.simulate_stat(market, mean, seed)
    espn_samples = (bm.simulate_stat(market, espn_projection * espn_scale, f"{seed}|espn")
                    if espn_projection and espn_projection > 0 else None)

    candidates: List[Dict[str, Any]] = []
    if market == "player_anytime_td":
        yes_prices = _td_yes_prices(books)
        if not yes_prices:
            return None
        p_market = _td_market_prob(yes_prices, td_scale)
        p_model = float((samples >= 1).mean())
        for book, price in yes_prices.items():
            candidates.append(_candidate("Yes", None, book, price, p_model, p_market, 0.0))
    else:
        fair_over = _fair_over(books)
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
    if espn_samples is not None:
        candidates = [_espn_check(c, espn_samples) for c in candidates]
    if market == "player_anytime_td":
        market_line, outlier = None, bm.projection_outlier(market, mean, market_td_prob=p_market)
    else:
        # The market's center: the quoted line whose fair P(over) is closest to 50%.
        market_line = min(fair_over, key=lambda pt: abs(fair_over[pt] - 0.5))
        outlier = bm.projection_outlier(market, mean, market_line=market_line)
    if outlier:
        candidates = [{**c, "units": 0.0, "confidence": "none"} for c in candidates]
    best = max(candidates, key=lambda c: c["ev"])
    # Watch: positive EV that every source agrees with but too small to size.
    best["watch"] = bool(best["units"] == 0 and best["ev"] > 0 and not outlier and best["model_agrees"]
                         and best.get("espn_agrees") is not False)
    pp_line = offers.get("prizepicks")
    pp_leg = (_prizepicks_leg(pp_line, samples, fair_over, espn_samples)
              if pp_line is not None and market != "player_anytime_td" and not outlier else None)
    return {
        "market_line": market_line,
        # Projection far from the market -- most likely a stale projection,
        # so no units (see betting_model.projection_outlier).
        "projection_outlier": outlier,
        "type": "player_prop",
        "player": player,
        "market": market,
        "market_label": MARKET_LABELS[market],
        "projection": round(projection, 2),
        # The projection after this slate's centering -- what was simulated.
        "model_mean": round(mean, 2),
        "espn_projection": round(espn_projection, 2) if espn_projection else None,
        "prizepicks_line": pp_line,
        "prizepicks": pp_leg,
        "books_quoting": len(books),
        **best,
    }


def _side_prob(samples, side: str, line: Optional[float]) -> float:
    if side == "Yes":
        return float((samples >= 1).mean())
    over, push = bm.prob_over(samples, line)
    return over if side in ("Over", "More") else max(0.0, 1 - over - push)


def _espn_check(c: Dict[str, Any], espn_samples) -> Dict[str, Any]:
    """ESPN's probability for this side; no units unless it also beats the market."""
    p = _side_prob(espn_samples, c["side"], c["line"])
    agrees = p > c["market_prob"]
    c = {**c, "espn_prob": round(p, 4), "espn_agrees": agrees}
    return c if agrees else {**c, "units": 0.0, "confidence": "none"}


def _prizepicks_leg(pp_line: float, samples, fair_over: Dict[float, float], espn_samples=None,
                    sides=frozenset({"over", "under"})) -> Optional[Dict[str, Any]]:
    """Better side of PrizePicks' line, priced like any other offer. The
    books rarely quote PrizePicks' exact number, so the market's fair
    P(over) is taken at the nearest book line and shifted by how much the
    simulated distribution moves between the two lines."""
    nearest = min(fair_over, key=lambda pt: abs(pt - pp_line))
    model_over, push = bm.prob_over(samples, pp_line)
    model_at_nearest, _ = bm.prob_over(samples, nearest)
    market_over = min(0.99, max(0.01, fair_over[nearest] + model_over - model_at_nearest))
    p_over = bm.blend(model_over, market_over)
    p_under = max(0.0, 1 - p_over - push)
    # The better side PrizePicks allows (goblins/demons are usually More only).
    if not sides & {"over", "under"}:
        return None
    over = (p_over >= p_under and "over" in sides) or "under" not in sides
    market_side = market_over if over else max(0.0, 1 - market_over - push)
    espn_p = _side_prob(espn_samples, "More" if over else "Less", pp_line) if espn_samples is not None else None
    return {
        "espn_prob": round(espn_p, 4) if espn_p is not None else None,
        # None when ESPN has no projection; pairs skip legs where it's False.
        "espn_agrees": (espn_p > market_side) if espn_p is not None else None,
        "line": pp_line,
        "side": "More" if over else "Less",
        "p_win": round(p_over if over else p_under, 4),
        "p_push": round(push, 4),
        "model_prob": round(model_over if over else max(0.0, 1 - model_over - push), 4),
        "market_prob": round(market_side, 4),
        "book_line": nearest,
    }


def prizepicks_pairs(props: List[Dict[str, Any]], limit: int = 25) -> Dict[str, Any]:
    """Best 2-pick Power Plays (3x) from the board's PrizePicks legs.
    Same-game legs are priced with their correlation (betting_model.
    leg_correlation). PrizePicks requires players from at least two
    different teams, so same-team pairs (e.g. a QB and his receiver) and the
    same player twice are never built. Legs ESPN's projection disagrees with
    are left out."""
    legs = [p for p in props if p.get("prizepicks") and p["prizepicks"]["p_win"] >= 0.5
            and p["prizepicks"].get("espn_agrees") is not False]
    legs.sort(key=lambda p: -p["prizepicks"]["p_win"])

    def leg_view(p):
        return {"player": p["player"], "team": p.get("team"), "game": p.get("game"), "kickoff": p.get("kickoff"),
                "market": p["market"], "market_label": p["market_label"], "projection": p["projection"],
                "espn_projection": p.get("espn_projection"),
                **p["prizepicks"]}

    pairs = []
    for i, a in enumerate(legs):
        for b in legs[i + 1:]:
            if a["player"] == b["player"] or (a.get("team") and a.get("team") == b.get("team")):
                continue
            same_game = a.get("game") == b.get("game")
            rho = bm.leg_correlation(a["market"], b["market"], same_game, a.get("team") == b.get("team"))
            sign = (1 if a["prizepicks"]["side"] == "More" else -1) * (1 if b["prizepicks"]["side"] == "More" else -1)
            pa, pb = a["prizepicks"]["p_win"], b["prizepicks"]["p_win"]
            joint = bm.joint_prob(pa, pb, rho * sign)
            priced = bm.price_offer(joint, bm.POWER_PLAY_2_PRICE)
            pairs.append({"legs": [leg_view(a), leg_view(b)], "same_game": same_game,
                          "correlation": round(rho * sign, 2), "joint_prob": round(joint, 4),
                          "independent_prob": round(pa * pb, 4), **priced})
    pairs.sort(key=lambda r: -r["ev"])
    return {
        "payout": bm.POWER_PLAY_2_PRICE / 100 + 1,
        "breakeven_leg": round(bm.POWER_PLAY_2_BREAKEVEN, 4),
        "legs": [leg_view(p) for p in legs[:60]],
        "pairs": pairs[:limit],
        "positive_ev_pairs": sum(1 for r in pairs if r["ev"] > 0),
    }


def price_uploaded_board(uploaded: Dict[str, Any], matched: List[tuple], week: int, scales: Dict[str, float],
                         td_scales: Dict[str, Optional[float]], espn_means: Dict[Tuple[str, str], Optional[float]],
                         espn_scales: Dict[str, float]) -> Dict[str, Any]:
    """The prizepicks section from the user's uploaded board (prizepicks_board):
    every line whose player and stat the books also price, standard lines
    paired into 2-picks, goblins/demons ranked by hit chance (their payouts
    aren't in the file, so no EV). Lines without a book market are skipped."""
    by_key = {(normalize_name(m[5]), m[6]): m for m in matched}
    priced: List[Dict[str, Any]] = []
    unmatched = 0
    for line in uploaded.get("lines") or []:
        m = by_key.get((normalize_name(line["player"]), line["market"]))
        if not m:
            unmatched += 1
            continue
        g, label, team, home, away, player, market, offers, mean = m
        seed = f"{week}|{player}|{market}"
        model_mean = mean * scales.get(market, 1.0)
        samples = bm.simulate_stat(market, model_mean, seed)
        espn_mean = espn_means.get((player, market))
        esamp = (bm.simulate_stat(market, espn_mean * espn_scales.get(market, 1.0), f"{seed}|espn")
                 if espn_mean and espn_mean > 0 else None)
        allowed = set(line.get("allowed") or ["over", "under"])
        if market == "player_anytime_td":
            if line["line"] != 0.5 or "over" not in allowed:
                continue
            p_mkt = _td_market_prob(_td_yes_prices(offers["books"]), td_scales.get(g["id"]))
            if p_mkt is None:
                continue
            p_mod = float((samples >= 1).mean())
            ep = float((esamp >= 1).mean()) if esamp is not None else None
            leg = {"line": 0.5, "side": "More", "p_win": round(bm.blend(p_mod, p_mkt), 4), "p_push": 0.0,
                   "model_prob": round(p_mod, 4), "market_prob": round(p_mkt, 4), "book_line": None,
                   "espn_prob": round(ep, 4) if ep is not None else None,
                   "espn_agrees": (ep > p_mkt) if ep is not None else None}
            outlier = bm.projection_outlier(market, model_mean, market_td_prob=p_mkt)
        else:
            fair = _fair_over(offers["books"])
            if not fair:
                continue
            leg = _prizepicks_leg(line["line"], samples, fair, esamp, sides=allowed)
            if leg is None:
                continue
            outlier = bm.projection_outlier(market, model_mean, market_line=min(fair, key=lambda pt: abs(fair[pt] - 0.5)))
        if outlier:
            continue  # stale projection: don't rank it
        priced.append({"player": player, "team": team, "game": label, "kickoff": g.get("commence_time"),
                       "market": market, "market_label": MARKET_LABELS[market], "projection": round(mean, 2),
                       "espn_projection": round(espn_mean, 2) if espn_mean else None,
                       "odds_type": line.get("odds_type", "standard"), "prizepicks": leg})

    section = prizepicks_pairs([p for p in priced if p["odds_type"] == "standard"])

    def ranked(kind):
        rows = [p for p in priced if p["odds_type"] == kind and p["prizepicks"].get("espn_agrees") is not False]
        rows.sort(key=lambda p: -p["prizepicks"]["p_win"])
        return [{k: v for k, v in p.items() if k != "prizepicks"} | p["prizepicks"] for p in rows[:25]]

    return {**section, "source": "upload", "uploaded_at": uploaded.get("uploaded_at"),
            "lines_priced": len(priced), "lines_unmatched": unmatched,
            "goblins": ranked("goblin"), "demons": ranked("demon")}


def prizepicks_entries(legs: List[Dict[str, Any]], power: Optional[Dict[int, float]] = None,
                       flex: Optional[Dict[int, Dict[int, float]]] = None, pool: int = 12,
                       per_size: int = 3) -> List[Dict[str, Any]]:
    """Best PrizePicks entries -- 3-6 pick Power (2-pick Power is the pairs
    list) and 2-6 pick Flex -- from the most likely
    legs. Rules: one pick per player and players from at least two teams.
    Opposing players in the same game are simulated together (leg
    correlation); everything else is independent."""
    from itertools import combinations
    power = power or bm.POWER_PAYOUTS
    flex = flex or bm.FLEX_PAYOUTS
    top = sorted(legs, key=lambda l: -l["p_win"])[:pool]
    out: List[Dict[str, Any]] = []
    for size in range(2, 7):
        if size not in power and size not in flex:
            continue
        found: Dict[str, List[Dict[str, Any]]] = {"power": [], "flex": []}
        for combo in combinations(top, size):
            if len({l["player"] for l in combo}) < size or len({l.get("team") for l in combo}) < 2:
                continue
            corr = np.eye(size)
            for i, a in enumerate(combo):
                for j in range(i + 1, size):
                    b = combo[j]
                    if a.get("game") == b.get("game") and a.get("team") != b.get("team"):
                        sign = (1 if a["side"] == "More" else -1) * (1 if b["side"] == "More" else -1)
                        corr[i, j] = corr[j, i] = sign * bm.leg_correlation(a["market"], b["market"], True, False)
            dist = bm.hit_count_distribution([l["p_win"] for l in combo], corr, "|".join(l["player"] for l in combo))
            power_table = {size: power[size]} if size >= 3 and power.get(size) else None
            for kind, table in (("power", power_table), ("flex", flex.get(size))):
                if not table:
                    continue
                found[kind].append({"size": size, "type": kind, "ev": round(bm.entry_ev(dist, table), 4),
                                    "p_all": round(float(dist[size]), 4), "payouts": table,
                                    "p_paid": round(float(sum(dist[k] for k in table)), 4),
                                    "legs": list(combo)})
        for kind in ("power", "flex"):
            out.extend(sorted(found[kind], key=lambda e: -e["ev"])[:per_size])
    return out


def _candidate(side, point, book, price, p_model, p_market, p_push) -> Dict[str, Any]:
    p = bm.blend(p_model, p_market)
    priced = bm.price_offer(p, price, p_push)
    # The model must agree with the side; a market-only "edge" is just vig noise.
    if p_model <= p_market:
        priced = {**priced, "units": 0.0, "confidence": "none"}
    return {
        "model_agrees": p_model > p_market,
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

def evaluate_game(game: Dict[str, Any], model: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Best-priced side of the spread and the total for one game.

    `model` (optional): {"margin", "total"} -- the projected home margin and
    total (Sleeper team points) -- plus "check_margin" (ESPN's matchup
    predictor) and "check_total" (ESPN player projections). With a model the
    win probability is blended 30/70 with the consensus and a side needs the
    model and the check to favor it; without one, sims center on consensus
    and only an off-market book's price can show an edge."""
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
    seed = f"{game.get('id')}|game"
    market = bm.simulate_game(home_spread, total_line, seed)
    sims = {"model": None, "check": None}
    if model and model.get("margin") is not None and model.get("total") is not None:
        sims["model"] = bm.simulate_game(-model["margin"], model["total"], seed + "|model")
        if model.get("check_margin") is not None or model.get("check_total") is not None:
            sims["check"] = bm.simulate_game(-(model.get("check_margin") if model.get("check_margin") is not None else model["margin"]),
                                             model.get("check_total") if model.get("check_total") is not None else model["total"],
                                             seed + "|check")
    label = f"{_team(away) or away} @ {_team(home) or home}"
    out = []

    def side_probs(sim, kind, name, point):
        margin, total = sim
        if kind == "spread":
            diff = (margin if name == home else -margin) + point
        else:
            diff = (total - point) if name == "Over" else (point - total)
        return float((diff > 0).mean()), float((diff == 0).mean())

    def best_of(rows, kind):
        cands = []
        for book, name, point, price in rows:
            p_mkt, p_push = side_probs(market, kind, name, point)
            p_mod = side_probs(sims["model"], kind, name, point)[0] if sims["model"] else None
            p_check = side_probs(sims["check"], kind, name, point)[0] if sims["check"] else None
            priced = bm.price_offer(bm.blend(p_mod, p_mkt), price, p_push)
            agrees = p_mod is None or p_mod > p_mkt
            check_ok = None if p_check is None else p_check > p_mkt
            if not agrees or check_ok is False:
                priced = {**priced, "units": 0.0, "confidence": "none"}
            side = (_team(name) or name) if kind == "spread" else name
            cands.append({"side": side, "line": point, "book": BOOK_LABELS.get(book, book), "price": int(price),
                          "model_prob": round(p_mod, 4) if p_mod is not None else None,
                          "market_prob": round(p_mkt, 4), "check_prob": round(p_check, 4) if p_check is not None else None,
                          "watch": bool(p_mod is not None and agrees and check_ok is not False and priced["ev"] > 0),
                          **priced})
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
                # Model projections in the market's terms: home spread (negative =
                # home favored) or total points.
                "model_line": (round(-model["margin"], 1) if kind == "spread" else round(model["total"], 1)) if sims["model"] else None,
                "check_line": ((round(-model["check_margin"], 1) if model.get("check_margin") is not None else None) if kind == "spread"
                               else (round(model["check_total"], 1) if model.get("check_total") is not None else None)) if sims["model"] else None,
                "books_quoting": len({r[0] for r in rows}),
                **best,
            })
    return out


def game_combos(game: Dict[str, Any], model: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Cover + over/under same-game parlays at the consensus spread and
    total: the chance each combo hits and its fair (no-vig) odds. The Odds
    API has no same-game-parlay prices, so these are for comparing with the
    sportsbook's own SGP price -- value is a book paying more than fair."""
    home, away = game.get("home_team"), game.get("away_team")
    rows = [(m.get("key"), o) for b in game.get("bookmakers") or [] for m in b.get("markets") or []
            for o in m.get("outcomes") or [] if o.get("point") is not None]
    home_spread = bm.median(o["point"] for k, o in rows if k == "spreads" and o["name"] == home)
    total_line = bm.median(o["point"] for k, o in rows if k == "totals" and o["name"] == "Over")
    if home_spread is None or total_line is None:
        return None
    margin_mean, total_mean = -home_spread, total_line
    if model and model.get("margin") is not None and model.get("total") is not None:
        margin_mean = bm.blend(model["margin"], -home_spread)
        total_mean = bm.blend(model["total"], total_line)
    home_favored = home_spread < 0
    rho = bm.COVER_TOTAL_RHO * (1 if home_favored else -1)
    margin, total = bm.simulate_game_joint(margin_mean, total_mean, rho, f"{game.get('id')}|combo")
    h, a = _team(home) or home, _team(away) or away
    combos = []
    for team, cover in ((h, margin + home_spread > 0), (a, -margin - home_spread > 0)):
        team_line = home_spread if team == h else -home_spread
        for side, hit in (("Over", total > total_line), ("Under", total < total_line)):
            p = float((cover & hit).mean())
            combos.append({"label": f"{team} {'+' if team_line > 0 else ''}{team_line:g} & {side} {total_line:g}",
                           "team": team, "spread": team_line, "total_side": side, "total": total_line,
                           "prob": round(p, 4), "fair_odds": bm.fair_american(p)})
    combos.sort(key=lambda c: -c["prob"])
    return {"game": f"{a} @ {h}", "kickoff": game.get("commence_time"), "favorite": h if home_favored else a,
            "modeled": bool(model), "combos": combos}


def _team_points(sleeper_rows: List[Dict[str, Any]], espn: Dict[str, Dict[str, Any]]) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Projected points per team: 6 x rushing/receiving TDs + kicker points.
    Returns (Sleeper, ESPN) -- ESPN's projections here have no kickers, so
    its version reuses Sleeper's kicker points."""
    sleeper: Dict[str, float] = {}
    kicker: Dict[str, float] = {}
    for r in sleeper_rows:
        st = r.get("stats") or {}
        p = r.get("player") or {}
        team = odds_service.normalize_team(r.get("team") or p.get("team"))
        if not team:
            continue
        if p.get("position") in ("QB", "RB", "WR", "TE"):
            sleeper[team] = sleeper.get(team, 0.0) + 6 * (float(st.get("rush_td") or 0) + float(st.get("rec_td") or 0))
        elif p.get("position") == "K":
            k = 3 * float(st.get("fgm") or 0) + float(st.get("xpm") or 0)
            kicker[team] = kicker.get(team, 0.0) + k
    espn_pts: Dict[str, float] = {}
    for row in espn.values():
        team = odds_service.normalize_team(row.get("team"))
        if team:
            espn_pts[team] = espn_pts.get(team, 0.0) + 6 * (float(row.get("rush_td") or 0) + float(row.get("rec_td") or 0))
    for team, k in kicker.items():
        sleeper[team] = sleeper.get(team, 0.0) + k
        if team in espn_pts:
            espn_pts[team] += k
    return sleeper, espn_pts


def game_models(games: List[Dict[str, Any]], sleeper_pts: Dict[str, float], espn_pts: Dict[str, float],
                win_probs: Dict[str, float]) -> Dict[str, Dict[str, Any]]:
    """Per game id: projected home margin / total (Sleeper), and the ESPN
    checks. Totals are centered so the slate's median model total matches
    the market's (same idea as betting_model.fit_projection_scale)."""
    def consensus_total(g):
        return _consensus_total(g)

    raw = {}
    for g in games:
        h, a = _team(g.get("home_team")), _team(g.get("away_team"))
        if h in sleeper_pts and a in sleeper_pts:
            raw[g["id"]] = (g, h, a)
    ratios = [(sleeper_pts[h] + sleeper_pts[a]) / consensus_total(g)
              for g, h, a in raw.values() if consensus_total(g)]
    espn_ratios = [(espn_pts[h] + espn_pts[a]) / consensus_total(g)
                   for g, h, a in raw.values() if consensus_total(g) and h in espn_pts and a in espn_pts]
    scale = 1 / bm.median(ratios) if len(ratios) >= bm.CENTERING_MIN_PROPS else 1.0
    espn_scale = 1 / bm.median(espn_ratios) if len(espn_ratios) >= bm.CENTERING_MIN_PROPS else 1.0
    out = {}
    for gid, (g, h, a) in raw.items():
        out[gid] = {
            "margin": (sleeper_pts[h] - sleeper_pts[a]) * scale,
            "total": (sleeper_pts[h] + sleeper_pts[a]) * scale,
            "check_margin": bm.margin_from_win_prob(win_probs[h]) if h in win_probs else None,
            "check_total": (espn_pts[h] + espn_pts[a]) * espn_scale if h in espn_pts and a in espn_pts else None,
        }
    return out


# ---------------------------------------------------------------------------
# Board
# ---------------------------------------------------------------------------

def _consensus_total(game: Dict[str, Any]) -> Optional[float]:
    return bm.median(o["point"] for b in game.get("bookmakers") or [] for m in b.get("markets") or []
                     if m.get("key") == "totals" for o in m.get("outcomes") or []
                     if o.get("name") == "Over" and o.get("point") is not None)


async def build_board(force: bool = False) -> Dict[str, Any]:
    cached = _board_cache.get("board")
    if cached and not force and time.monotonic() - cached[0] < _BOARD_TTL_SECONDS:
        return cached[1]

    from app.core.config import settings
    if not settings.ODDS_API_KEY:
        return {"available": False, "detail": "Betting odds aren't configured (ODDS_API_KEY is not set).",
                "disclaimer": DISCLAIMER}

    now = datetime.now(timezone.utc)
    # Only games that haven't kicked off: in-game odds aren't what we'd
    # recommend, and they'd pollute the tracked record.
    games = [g for g in odds_service.this_week(await odds_service.get_game_lines(), now)
             if g.get("commence_time", "") > now.strftime("%Y-%m-%dT%H:%M:%SZ")]
    state = await sleeper_service.get_nfl_state()
    week = state.get("week") if isinstance(state, dict) else None
    season = int(state.get("season") or now.year) if isinstance(state, dict) else now.year
    if not games or not week:
        return {"available": False, "detail": "No NFL lines available right now.", "disclaimer": DISCLAIMER}

    rows, espn, win_probs = await asyncio.gather(fetch_weekly_projections(season, int(week)),
                                                 fetch_espn_weekly_projections(season, int(week)),
                                                 fetch_home_win_probs(season, int(week)))
    projections = _projection_index(rows)

    sem = asyncio.Semaphore(_PROP_CONCURRENCY)

    async def props_for(g):
        async with sem:
            return g, await odds_service.get_event_props(g["id"])

    fetched = await asyncio.gather(*(props_for(g) for g in games))

    games_without_props: List[str] = []
    unmatched = 0
    matched = []  # (game, label, team, home, away, player, market, offers, mean)
    for g, event in fetched:
        home, away = _team(g.get("home_team")), _team(g.get("away_team"))
        teams = (home, away)
        label = f"{away} @ {home}"
        if not event:
            games_without_props.append(label)
            continue
        for (player, market), offers in _group_offers(event).items():
            team = next((t for t in teams if projections.get((normalize_name(player), t)) is not None), None)
            stats = projections.get((normalize_name(player), team)) if team else None
            mean = _projected_mean(stats, market) if stats else None
            if mean is None or mean <= 0:
                unmatched += 1
                continue
            matched.append((g, label, team, home, away, player, market, offers, mean))
    espn_means = {(player, market): _projected_mean(espn[normalize_name(player)], market)
                  for *_, player, market, offers, mean in matched if normalize_name(player) in espn}

    # Anytime TD de-vig: each game's implied scoring rates scaled to what its
    # Vegas total supports; partial prop lists use the slate's median scale.
    td_scales: Dict[str, Optional[float]] = {}
    for g, event in fetched:
        if event:
            implied = [p for (_, m), offers in _group_offers(event).items() if m == "player_anytime_td"
                       for p in [_td_implied(_td_yes_prices(offers["books"]))] if p is not None]
            td_scales[g["id"]] = bm.td_rate_scale(implied, _consensus_total(g))
    slate_td_scale = bm.median(v for v in td_scales.values() if v is not None)
    td_scales = {k: (v if v is not None else slate_td_scale) for k, v in td_scales.items()}

    # Center each market's projections on the market across the slate
    # (betting_model.fit_projection_scale) before pricing anything.
    centers: Dict[str, List[Tuple[float, float]]] = {}
    for g, *_, market, offers, mean in matched:
        c = market_center(market, offers, td_scales.get(g["id"]))
        if c is not None:
            centers.setdefault(market, []).append((mean, c))
    scales = {m: await asyncio.to_thread(bm.fit_projection_scale, m, pairs) for m, pairs in centers.items()}
    espn_centers: Dict[str, List[Tuple[float, float]]] = {}
    for g, *_, player, market, offers, mean in matched:
        c = market_center(market, offers, td_scales.get(g["id"]))
        e = espn_means.get((player, market))
        if c is not None and e:
            espn_centers.setdefault(market, []).append((e, c))
    espn_scales = {m: await asyncio.to_thread(bm.fit_projection_scale, m, pairs) for m, pairs in espn_centers.items()}

    uploaded = await prizepicks_board.load_recent()

    player_props: List[Dict[str, Any]] = []
    for g, label, team, home, away, player, market, offers, mean in matched:
        rec = evaluate_player_prop(player, market, offers, mean, f"{week}|{player}|{market}",
                                   scales.get(market, 1.0), td_scales.get(g["id"]),
                                   espn_means.get((player, market)), espn_scales.get(market, 1.0))
        if rec:
            rec.update(game=label, kickoff=g.get("commence_time"), team=team, home=home, away=away)
            player_props.append(rec)

    sleeper_pts, espn_pts = _team_points(rows, espn)
    models = game_models(games, sleeper_pts, espn_pts, win_probs)
    game_props = [
        {**rec, "home": _team(g.get("home_team")), "away": _team(g.get("away_team"))}
        for g in games for rec in evaluate_game(g, models.get(g["id"]))
    ]
    combos = [c for g in games for c in [game_combos(g, models.get(g["id"]))] if c]
    try:
        await asyncio.to_thread(record_board, season, int(week), player_props + game_props)
    except Exception as e:  # noqa: BLE001 - tracking must never break the board
        logger.warning("Recording betting board failed: %s", e)

    def ranked(recs):
        # Bets first, then the watch list, then the rest; stale-projection
        # rows last -- their "EV" is the stale projection talking.
        return sorted(recs, key=lambda r: (-r["units"], not r.get("watch"), bool(r.get("projection_outlier")), -r["ev"]))

    board = {
        "available": True,
        "week": week,
        "season": season,
        "generated_at": now.isoformat(),
        "player_props": ranked(player_props),
        "game_props": ranked(game_props),
        # The uploaded PrizePicks board when there's a recent one, else the
        # Odds API's PrizePicks standard lines.
        "prizepicks": (price_uploaded_board(uploaded, matched, int(week), scales, td_scales, espn_means, espn_scales)
                       if uploaded else {**prizepicks_pairs(player_props), "source": "odds_api"}),
        "projection_scale": scales,
        "espn_projection_scale": espn_scales,
        "game_combos": combos,
        "watch_count": sum(1 for r in player_props + game_props if r.get("watch")),
        "recommended_count": sum(1 for r in player_props + game_props if r["units"] > 0),
        "evaluated": {"player_props": len(player_props), "games": len(games), "props_without_projection": unmatched},
        "games_without_props": games_without_props,
        "credits_remaining": await odds_service.credits_remaining_async(),
        "sources": {"odds": odds_service.SOURCE,
                    "projections": "Sleeper (RotoWire) weekly projections; ESPN weekly projections as a cross-check"},
        "method": METHOD,
        "disclaimer": DISCLAIMER,
    }
    _board_cache["board"] = (time.monotonic(), board)
    return board
