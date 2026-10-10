"""Picks made on radio shows and podcasts ("Shows" on the Bets page).

The founder supplies transcripts (SiriusXM can't be downloaded: paid,
DRM'd streams, and its terms forbid it). The picks are extracted by hand in
a Claude Code session -- no AI credits -- into a JSON file and loaded with
scripts/import_analyst_picks.py. Each pick keeps a snapshot of what our
board said about it when imported, and is graded like My entries (Sleeper
stats, ESPN finals; no Odds API credits).

Tracked, never priced. Projections don't beat the closing line, and on-air
picks are no different until a show's graded record says otherwise: a show
gets weight in the model only after a held-out test on 300+ graded picks
(the same bar as scripts/tune_from_results.py). Until then, a pick is
context: the "On air" note on a board row, and a reason to look twice when
a host gives a concrete reason against one of our picks.

Import file shape:
    {"source": "Fantasy Football Morning", "network": "SiriusXM Fantasy Sports Radio",
     "sport": "nfl" | "cfb", "aired_on": "2026-10-08", "season": 2026, "week": 5,
     "picks": [{"analyst", "segment", "player", "team", "game", "market",
                "side": "More"|"Less", "line", "line_stated", "price",
                "conviction": "bet"|"lean", "quote"}]}
`week` is the NFL betting week (Thu-Mon) the picks' games fall in -- for
college too, as everywhere on the Bets page (college week 6 = NFL week 5).
Legs use the My entries shape (user_entries.MARKETS): DAL -8.5 is
team_spread More 8.5 on "DAL"; an Over is game_total More on "TB @ DAL"
with team = the home team. College picks use the college board's full
team names ("UCLA Bruins"), and a pick's line is compared with the board's
line for the same side (`line_value`: positive when the market has since
moved toward the pick -- an early closing-line check).
"""
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.db.base import SessionLocal
from app.models.analyst_pick import AnalystPick
from app.services import user_entries
from app.services.odds_service import normalize_team
from app.services.weekly_projections import normalize_name

logger = logging.getLogger(__name__)

CONVICTIONS = ("bet", "lean")
SPORTS = ("nfl", "cfb")
# A prop pick this far from the board's line (share of the line) isn't the
# same bet: no chance comparison (e.g. a 90+ yard alt line vs 62.5).
FAR_LINE = 0.15
# Our chance within this of the books' is the market's own price (game lines
# are market-only): no lean either way.
NO_LEAN = 0.002


class PickError(ValueError):
    pass


def _team_key(sport: str):
    if sport == "cfb":
        from app.services.espn_game_predictor import cfb_team_key
        return cfb_team_key
    return lambda t: normalize_team(t) if t else t


def validate(pick: Dict[str, Any], sport: str = "nfl") -> Dict[str, Any]:
    market = pick.get("market")
    if market not in user_entries.MARKETS:
        raise PickError(f"Unknown market {market!r}")
    if pick.get("side") not in ("More", "Less"):
        raise PickError("side must be More or Less")
    if pick.get("conviction", "bet") not in CONVICTIONS:
        raise PickError("conviction must be bet or lean")
    player, analyst = (pick.get("player") or "").strip(), (pick.get("analyst") or "").strip()
    if not player or not analyst or pick.get("line") is None:
        raise PickError("Each pick needs an analyst, a player (or team / game) and a line")
    team = pick.get("team")
    if market in ("team_win", "team_spread"):
        team = team or player
    return {
        "analyst": analyst, "segment": pick.get("segment"), "player": player,
        "team": (normalize_team(team) if sport == "nfl" else team) if team else None, "game": pick.get("game"), "market": market,
        "side": pick["side"], "line": float(pick["line"]), "line_stated": bool(pick.get("line_stated", True)),
        "price": int(pick["price"]) if pick.get("price") is not None else None,
        "conviction": pick.get("conviction", "bet"), "quote": pick.get("quote"),
    }


def _other(p: Optional[float], push: float = 0.0) -> Optional[float]:
    return None if p is None else round(max(0.0, 1.0 - p - push), 4)


def board_snapshot(pick: Dict[str, Any], board: Dict[str, Any], sport: str = "nfl") -> Optional[Dict[str, Any]]:
    """What our board said about the pick: the line and price we priced
    (the board shows each line on the side it prefers), our chance and the
    books' chance for the pick's side at that line, whether our engine leans
    that way (our chance above the books'; None on a market-only line), and
    `line_value`: the board's line minus the pick's, in the pick's favor
    (positive = the pick got a better number than the board has now). None
    when the board has no such line."""
    market, side = pick["market"], pick["side"]
    key = _team_key(sport)
    row, same, equiv = None, None, None
    if market in ("team_spread", "game_total", "team_win"):
        team = key(pick.get("team") or pick["player"])
        for r in board.get("game_props") or []:
            if team not in (key(r.get("home")), key(r.get("away"))):
                continue
            if market == "team_win" and r.get("market") == "spread":
                row = r  # no moneyline on the board: the game's spread, for context and the kickoff
            elif market == "team_spread" and r.get("market") == "spread":
                mine = key(r["side"]) == team
                # The board's "T +h" is "T margin > -h": More -h on T, or the
                # other side of More h on the opponent.
                row, same, equiv = r, mine == (side == "More"), -r["line"] if mine else r["line"]
            elif market == "game_total" and r.get("market") == "total":
                row, same, equiv = r, (r["side"] == "Over") == (side == "More"), r["line"]
    else:
        name = normalize_name(pick["player"])
        for r in board.get("player_props") or []:
            if r.get("market") == market and normalize_name(r.get("player") or "") == name:
                row, same, equiv = r, (r["side"] in ("Over", "Yes")) == (side == "More"), r.get("line")
                break
    if row is None:
        return None
    push = row.get("p_push") or 0.0
    line = row.get("line")
    if row.get("market") == "spread":
        label = f"{row['side']} {line:+g}"
    else:
        label = f"{row['side']} {line:g}" if line is not None else row["side"]
    value = None
    if equiv is not None and market != "player_anytime_td":
        value = round((equiv - pick["line"]) if side == "More" else (pick["line"] - equiv), 2)
    ours = (row["p_win"] if same else _other(row["p_win"], push)) if same is not None else None
    books = (row.get("market_prob") if same else _other(row.get("market_prob"), push)) if same is not None else None
    far = (value is not None and market.startswith("player_")
           and abs(value) > FAR_LINE * max(abs(pick["line"]), 1.0))
    if far:
        ours = books = None
    lean = None if ours is None or books is None or abs(ours - books) < NO_LEAN else ours > books
    return {
        "board_line": label, "board_price": row.get("price"), "board_game": row.get("game"),
        "kickoff": row.get("kickoff"), "our_prob": ours, "books_prob": books,
        "ev": row.get("ev") if same and not far else None, "units": row.get("units") if same else 0.0,
        "agrees": lean, "line_value": value, "far_line": far,
        "saved_at": board.get("generated_at"),
    }


def _load_board(sport: str, season: int, week: int) -> Optional[Dict[str, Any]]:
    """The saved board (odds_cache "board:nfl" / "board:cfb"); the NFL one
    only when it's for the pick's week (the college board has no week)."""
    from app.models.odds_cache import OddsCache

    with SessionLocal() as db:
        row = db.get(OddsCache, f"board:{sport}")
    if not row:
        return None
    board = json.loads(row.payload)
    if sport == "nfl" and (board.get("season"), board.get("week")) != (season, week):
        return None
    return board


def import_show(data: Dict[str, Any], board: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    """Insert a show's picks (skipping ones already imported), each with a
    snapshot from the saved board of its sport."""
    source = (data.get("source") or "").strip()
    if not source:
        raise PickError("source (the show's name) is required")
    sport = data.get("sport", "nfl")
    if sport not in SPORTS:
        raise PickError("sport must be nfl or cfb")
    aired_on = date.fromisoformat(data["aired_on"])
    season, week = int(data["season"]), int(data["week"])
    picks = [validate(p, sport) for p in data.get("picks") or []]
    board = board if board is not None else _load_board(sport, season, week)
    added = skipped = 0
    with SessionLocal() as db:
        for p in picks:
            exists = db.query(AnalystPick).filter_by(
                source=source, aired_on=aired_on, analyst=p["analyst"], player=p["player"],
                market=p["market"], side=p["side"], line=p["line"]).first()
            if exists:
                skipped += 1
                continue
            snap = board_snapshot(p, board, sport) if board else None
            kickoff = datetime.fromisoformat(snap["kickoff"].replace("Z", "+00:00")) if snap and snap.get("kickoff") else None
            db.add(AnalystPick(source=source, network=data.get("network"), sport=sport, aired_on=aired_on,
                               season=season, week=week, kickoff=kickoff, snapshot=snap, **p))
            added += 1
        db.commit()
    return {"added": added, "skipped": skipped}


def _leg(r: AnalystPick) -> Dict[str, Any]:
    key = _team_key(r.sport) if r.sport == "cfb" else (lambda t: t)
    player = key(r.player) if r.market in ("team_win", "team_spread") else r.player
    return {"player": player, "team": key(r.team) if r.team else None, "market": r.market, "side": r.side,
            "line": r.line, "status": r.status, "actual": r.actual}


async def grade_pending(current_season: int, current_week: Optional[int]) -> int:
    """Grade pending picks whose game is final, or every pick once its week
    is over (no final -> void): NFL from Sleeper stats and ESPN's NFL
    scoreboard, college from ESPN's college scoreboard on the kickoff date
    (a college pick is over 4 days after kickoff). Network failures leave
    picks pending."""
    from app.services.betting_tracking import _espn_cfb_finals, _espn_finals, _sleeper_stats

    graded = 0
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        pending = db.query(AnalystPick).filter(AnalystPick.status == "pending").all()
        groups: Dict[tuple, List[AnalystPick]] = {}
        for r in pending:
            groups.setdefault((r.sport, r.season, r.week), []).append(r)
        for (sport, season, week), rows in groups.items():
            try:
                if sport == "cfb":
                    rows = [r for r in rows if r.kickoff]  # no kickoff: no board match, can't be graded
                    if not rows:
                        continue
                    finals, stats = await _espn_cfb_finals(r.kickoff for r in rows), {}
                    week_over = all(r.kickoff < now - timedelta(days=4) for r in rows)
                else:
                    finals, stats = await _espn_finals(season, week), await _sleeper_stats(season, week)
                    week_over = season < current_season or (current_week is not None and week < current_week)
            except Exception as err:  # noqa: BLE001 - try again next time
                logger.warning("Show picks %s %s wk %s grading skipped: %s", sport, season, week, type(err).__name__)
                continue
            for r, leg in zip(rows, user_entries.grade_legs([_leg(r) for r in rows], stats, finals, week_over)):
                if leg["status"] != "pending":
                    r.status, r.actual, r.graded_at = leg["status"], leg["actual"], now
                    graded += 1
        db.commit()
    return graded


def units_won(status: str, price: Optional[int]) -> float:
    """Profit of a flat 1u bet at the stated price (-110 when none was given)."""
    price = price or -110
    if status == "won":
        return round(price / 100 if price > 0 else 100 / -price, 4)
    return -1.0 if status == "lost" else 0.0


def _record(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    settled = [r for r in rows if r["status"] in ("won", "lost")]
    won = sum(r["status"] == "won" for r in settled)
    units = sum(units_won(r["status"], r["price"]) for r in rows if r["status"] != "pending")
    return {"picks": len(rows), "won": won, "lost": len(settled) - won,
            "push": sum(r["status"] in ("push", "void") for r in rows),
            "pending": sum(r["status"] == "pending" for r in rows),
            "hit_rate": round(won / len(settled), 4) if settled else None,
            "units": round(units, 2), "roi": round(units / len(settled), 4) if settled else None}


def _out(r: AnalystPick) -> Dict[str, Any]:
    return {"id": r.id, "source": r.source, "network": r.network, "sport": r.sport, "analyst": r.analyst,
            "segment": r.segment, "kickoff": r.kickoff.isoformat() if r.kickoff else None, "aired_on": r.aired_on.isoformat(), "season": r.season, "week": r.week, "player": r.player,
            "team": r.team, "game": r.game, "market": r.market, "market_label": user_entries.MARKETS[r.market][0],
            "side": r.side, "line": r.line, "line_stated": r.line_stated, "price": r.price,
            "conviction": r.conviction, "quote": r.quote, "snapshot": r.snapshot, "status": r.status,
            "actual": r.actual}


def summary() -> Dict[str, Any]:
    """Every show with its picks (newest first), its record on bets and on
    leans separately, each host's record, how its bets did when our board
    agreed vs disagreed, and how the market has moved on its stated lines.
    One entry per show per sport: a show that picks NFL and college (Elite
    Sports) gets a separate record on each tab, never a blended one."""
    with SessionLocal() as db:
        rows = [_out(r) for r in db.query(AnalystPick).order_by(AnalystPick.aired_on.desc(), AnalystPick.id).all()]
    shows = []
    for source, sport in dict.fromkeys((r["source"], r["sport"]) for r in rows):
        picks = [r for r in rows if r["source"] == source and r["sport"] == sport]
        bets = [r for r in picks if r["conviction"] == "bet"]
        snap = [r for r in bets if r["snapshot"] and r["snapshot"].get("agrees") is not None]
        moved = [r["snapshot"]["line_value"] for r in picks
                 if r["line_stated"] and r["snapshot"] and r["snapshot"].get("line_value") is not None
                 and not r["snapshot"].get("far_line")]
        shows.append({
            "source": source,
            "network": next((r["network"] for r in picks if r["network"]), None),
            "sports": sorted({r["sport"] for r in picks}),
            "episodes": sorted({r["aired_on"] for r in picks}, reverse=True),
            "record": _record(bets),
            "leans": _record([r for r in picks if r["conviction"] == "lean"]),
            "analysts": [{"analyst": a, **_record([r for r in bets if r["analyst"] == a])}
                         for a in dict.fromkeys(r["analyst"] for r in bets)],
            "vs_board": {"agreed": _record([r for r in snap if r["snapshot"]["agrees"]]),
                         "disagreed": _record([r for r in snap if not r["snapshot"]["agrees"]])},
            "line_moves": {"picks": len(moved), "toward": sum(v > 0 for v in moved),
                           "away": sum(v < 0 for v in moved), "unchanged": sum(v == 0 for v in moved)},
            "picks": picks,
        })
    return {"shows": shows}
