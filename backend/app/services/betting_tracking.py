"""Track record for the betting board: record every priced line, grade it
against real results, summarize how the recommendations did.

- record_board: called when the board is computed. Freezes each line at
  the price first seen (see BetPick for the upsert rule).
- grade_pending: settles pending picks once their game is final, from free
  sources (no Odds API credits): Sleeper's weekly stats for player props,
  ESPN's public NFL scoreboard for NFL game lines, ESPN's college scoreboard
  (matched by full team name) for college game lines (kind "cfb_game"). A player with no stat line (or
  0 games played) is graded "void", matching how books void props for
  inactive players.
- summarize: record, units, ROI (recommended picks only), splits by
  confidence / market / week, and calibration over every graded line --
  predicted win probability vs what actually happened, with Brier scores
  for the model, the market and the blend. That's what tunes the model.
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.base import SessionLocal
from app.models.bet_pick import BetPick
from app.services import betting_model as bm
from app.services.odds_service import normalize_team
from app.services.weekly_projections import normalize_name

logger = logging.getLogger(__name__)

_SLEEPER_STATS_URL = "https://api.sleeper.app/stats/nfl/{season}/{week}"
_ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
_ESPN_CFB_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard"
GAME_KINDS = ("game", "cfb_game")  # NFL / college game lines (same win/loss math)
# A game is gradeable once it has surely ended and stats have landed.
_GRADE_AFTER = timedelta(hours=5)

_STAT_KEYS = {
    "player_pass_yds": ("pass_yd",),
    "player_rush_yds": ("rush_yd",),
    "player_reception_yds": ("rec_yd",),
    "player_receptions": ("rec",),
    "player_anytime_td": ("rush_td", "rec_td"),
}


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

def _parse_time(value: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
    except ValueError:
        return None


def _row_values(season: int, week: int, r: Dict[str, Any]) -> Dict[str, Any]:
    kind = r["type"]
    return {
        "season": season,
        "week": week,
        "kind": kind,
        "subject": r["player"] if kind == "player_prop" else r["game"],
        "team": r.get("team"),
        "game": r["game"],
        "home": r.get("home"),
        "away": r.get("away"),
        "kickoff": _parse_time(r.get("kickoff")),
        "market": r["market"],
        "side": r["side"],
        "line": r.get("line"),
        "book": r["book"],
        "price": int(r["price"]),
        "units": float(r["units"]),
        "confidence": r["confidence"],
        "recommended": r["units"] > 0,
        "ev": float(r["ev"]),
        "p_win": float(r["p_win"]),
        "p_push": float(r.get("p_push") or 0.0),
        "model_prob": r.get("model_prob"),
        "market_prob": r.get("market_prob"),
        "projection": r.get("projection"),
        "espn_projection": r.get("espn_projection"),
    }


def fill_keys(season: int, week: int) -> set:
    """(kind, subject, market) of lines already tracked as card fills this
    week, so the card keeps the same "Best available" picks as prices move."""
    with SessionLocal() as db:
        rows = db.query(BetPick.kind, BetPick.subject, BetPick.market).filter(
            BetPick.season == season, BetPick.week == week, BetPick.confidence == "fill").all()
    return {tuple(r) for r in rows}


def record_board(season: int, week: int, rows: Iterable[Dict[str, Any]]) -> int:
    """Insert each priced line once. An existing "no bet" row is replaced
    when the line later becomes a recommendation; an existing
    recommendation is never touched. Returns rows written."""
    values = [_row_values(season, week, r) for r in rows]
    if not values:
        return 0
    with SessionLocal() as db:
        stmt = pg_insert(BetPick).values(values)
        upgrade = {c: stmt.excluded[c] for c in values[0] if c not in ("season", "week", "kind", "subject", "market")}
        stmt = stmt.on_conflict_do_update(
            constraint="uq_bet_pick_line",
            set_={**upgrade, "first_seen_at": datetime.now(timezone.utc)},
            # Only a pending "no bet" row can be upgraded, and only to a recommendation.
            where=(BetPick.recommended.is_(False)) & (BetPick.status == "pending") & stmt.excluded.recommended,
        )
        result = db.execute(stmt)
        db.commit()
        return result.rowcount or 0


# ---------------------------------------------------------------------------
# Grading (pure outcome rules)
# ---------------------------------------------------------------------------

def prop_outcome(market: str, side: str, line: Optional[float], actual: float) -> str:
    if market == "player_anytime_td":
        return "won" if actual >= 1 else "lost"
    if line is None:
        return "void"
    if actual == line:
        return "push"
    over_hit = actual > line
    return "won" if over_hit == (side == "Over") else "lost"


def game_outcome(market: str, side: str, line: float, home: str, home_score: float, away_score: float) -> Tuple[str, float]:
    """(outcome, actual): actual is the side's margin for a spread, the
    combined score for a total."""
    if market == "spread":
        margin = (home_score - away_score) if side == home else (away_score - home_score)
        diff = margin + line
        actual = margin
    else:
        total = home_score + away_score
        diff = (total - line) if side == "Over" else (line - total)
        actual = total
    if diff == 0:
        return "push", actual
    return ("won" if diff > 0 else "lost"), actual


def profit(outcome: str, units: float, price: int) -> float:
    if outcome == "won":
        return round(units * (bm.american_to_decimal(price) - 1), 3)
    if outcome == "lost":
        return -units
    return 0.0


# ---------------------------------------------------------------------------
# Grading (data)
# ---------------------------------------------------------------------------

async def _sleeper_stats(season: int, week: int) -> Dict[Tuple[str, str], Dict[str, Any]]:
    params = [("season_type", "regular")] + [("position[]", p) for p in ("QB", "RB", "WR", "TE")]
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(_SLEEPER_STATS_URL.format(season=season, week=week), params=params)
        r.raise_for_status()
        rows = r.json()
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in rows if isinstance(rows, list) else []:
        p = row.get("player") or {}
        name = normalize_name(f"{p.get('first_name', '')} {p.get('last_name', '')}")
        team = normalize_team(row.get("team") or p.get("team"))
        if name and team:
            out[(name, team)] = row.get("stats") or {}
    return out


async def _espn_finals(season: int, week: int) -> Dict[Tuple[str, str], Tuple[float, float]]:
    """{(home, away): (home_score, away_score)} for completed NFL games."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(_ESPN_SCOREBOARD_URL, params={"seasontype": 2, "week": week, "dates": season})
        r.raise_for_status()
        data = r.json()
    return _completed_scores(data, lambda t: normalize_team(t.get("abbreviation")))


def _completed_scores(data: Dict[str, Any], key) -> Dict[Tuple[str, str], Tuple[float, float]]:
    """{(key(home), key(away)): (home_score, away_score)} for completed games
    on an ESPN scoreboard response."""
    finals = {}
    for event in data.get("events") or []:
        comp = (event.get("competitions") or [{}])[0]
        if not ((comp.get("status") or {}).get("type") or {}).get("completed"):
            continue
        teams = {c.get("homeAway"): c for c in comp.get("competitors") or []}
        if "home" not in teams or "away" not in teams:
            continue
        finals[(key(teams["home"]["team"]), key(teams["away"]["team"]))] = (
            float(teams["home"]["score"]), float(teams["away"]["score"]))
    return finals


async def _espn_cfb_finals(kickoffs: Iterable[datetime]) -> Dict[Tuple[str, str], Tuple[float, float]]:
    """College finals keyed by (cfb_team_key(home), cfb_team_key(away)), from
    ESPN's FBS scoreboard on each kickoff's date (and the day before, since a
    late kickoff in UTC is the previous evening in the US)."""
    from app.services.espn_game_predictor import cfb_team_key
    dates = sorted({(k - timedelta(days=d)).strftime("%Y%m%d") for k in kickoffs for d in (0, 1)})
    finals: Dict[Tuple[str, str], Tuple[float, float]] = {}
    async with httpx.AsyncClient(timeout=30.0) as client:
        for day in dates:
            r = await client.get(_ESPN_CFB_SCOREBOARD_URL, params={"dates": day, "groups": 80, "limit": 300})
            r.raise_for_status()
            finals.update(_completed_scores(r.json(), lambda t: cfb_team_key(t.get("displayName"))))
    return finals


async def grade_pending(now: Optional[datetime] = None) -> int:
    """Settle every pending pick whose game has had time to finish.
    Returns how many were graded. Network failures leave picks pending
    for the next call -- never guessed."""
    now = now or datetime.now(timezone.utc)
    with SessionLocal() as db:
        pending = db.query(BetPick).filter(
            BetPick.status == "pending", BetPick.kickoff.isnot(None), BetPick.kickoff < now - _GRADE_AFTER
        ).all()
        by_week: Dict[Tuple[int, int], List[BetPick]] = defaultdict(list)
        for p in pending:
            by_week[(p.season, p.week)].append(p)

        graded = 0
        for (season, week), picks in by_week.items():
            from app.services.espn_game_predictor import cfb_team_key
            college = [p for p in picks if p.kind == "cfb_game"]
            try:
                finals = await _espn_finals(season, week) if len(college) < len(picks) else {}
                stats = await _sleeper_stats(season, week) if any(p.kind == "player_prop" for p in picks) else {}
                cfb_finals = await _espn_cfb_finals(p.kickoff for p in college) if college else {}
            except (httpx.HTTPError, ValueError) as e:
                logger.warning("Grading week %s/%s skipped: %s", season, week, e)
                continue
            for p in picks:
                if p.kind == "cfb_game":
                    score = cfb_finals.get((cfb_team_key(p.home), cfb_team_key(p.away)))
                else:
                    score = finals.get((p.home, p.away))
                if score is None:
                    continue  # not final yet (or postponed): try again later
                home_score, away_score = score
                if p.kind in GAME_KINDS:
                    outcome, actual = game_outcome(p.market, p.side, p.line, p.home, home_score, away_score)
                else:
                    row = stats.get((normalize_name(p.subject), p.team))
                    if row is None or not row.get("gp"):
                        outcome, actual = "void", None
                    else:
                        actual = float(sum(float(row.get(k) or 0.0) for k in _STAT_KEYS[p.market]))
                        outcome = prop_outcome(p.market, p.side, p.line, actual)
                p.status = outcome
                p.actual = actual
                p.profit_units = profit(outcome, p.units, p.price)
                p.graded_at = now
                graded += 1
        db.commit()
    return graded


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def _record(picks: List[BetPick]) -> Dict[str, Any]:
    settled = [p for p in picks if p.status in ("won", "lost", "push")]
    staked = sum(p.units for p in settled)
    won_units = sum(p.profit_units or 0.0 for p in settled)
    decided = [p for p in settled if p.status != "push"]
    return {
        "bets": len(picks),
        "won": sum(p.status == "won" for p in picks),
        "lost": sum(p.status == "lost" for p in picks),
        "push": sum(p.status == "push" for p in picks),
        "void": sum(p.status == "void" for p in picks),
        "pending": sum(p.status == "pending" for p in picks),
        "win_rate": round(sum(p.status == "won" for p in decided) / len(decided), 4) if decided else None,
        "units_staked": round(staked, 2),
        "units_profit": round(won_units, 2),
        "roi": round(won_units / staked, 4) if staked else None,
    }


def _brier(pairs: List[Tuple[float, int]]) -> Optional[float]:
    return round(sum((p - y) ** 2 for p, y in pairs) / len(pairs), 4) if pairs else None


def calibration(picks: List[BetPick]) -> Dict[str, Any]:
    """Predicted win probability vs actual result over every graded,
    decided line (pushes and voids excluded), in 10-point buckets, plus
    Brier scores (lower = better) for blend, model and market."""
    decided = [p for p in picks if p.status in ("won", "lost")]
    buckets: Dict[int, List[BetPick]] = defaultdict(list)
    for p in decided:
        buckets[min(9, int(p.p_win * 10))].append(p)
    rows = [
        {
            "range": f"{b * 10}-{b * 10 + 10}%",
            "n": len(ps),
            "predicted": round(sum(p.p_win for p in ps) / len(ps), 4),
            "actual": round(sum(p.status == "won" for p in ps) / len(ps), 4),
        }
        for b, ps in sorted(buckets.items())
    ]
    outcome = lambda p: 1 if p.status == "won" else 0  # noqa: E731
    return {
        "lines": len(decided),
        "buckets": rows,
        "brier": {
            "blend": _brier([(p.p_win, outcome(p)) for p in decided]),
            "model": _brier([(p.model_prob, outcome(p)) for p in decided if p.model_prob is not None and p.kind == "player_prop"]),
            "market": _brier([(p.market_prob, outcome(p)) for p in decided if p.market_prob is not None]),
        },
    }


def _pick_out(p: BetPick) -> Dict[str, Any]:
    return {
        "id": p.id, "season": p.season, "week": p.week, "kind": p.kind, "subject": p.subject, "game": p.game,
        "market": p.market, "side": p.side, "line": p.line, "book": p.book, "price": p.price,
        "units": p.units, "confidence": p.confidence, "ev": p.ev, "p_win": p.p_win,
        "projection": p.projection, "kickoff": p.kickoff.isoformat() if p.kickoff else None,
        "status": p.status, "actual": p.actual, "profit_units": p.profit_units,
    }


# Which pick kinds each sport's Results view covers.
SPORT_KINDS = {"nfl": ("player_prop", "game"), "cfb": ("cfb_game",)}


def summarize(season: Optional[int] = None, sport: Optional[str] = None) -> Dict[str, Any]:
    """Record and calibration for one sport ("nfl" / "cfb") or all picks.
    Sports are judged separately: college uses a different, less-proven
    model, and mixing them would hide whether either one works."""
    with SessionLocal() as db:
        q = db.query(BetPick)
        if season:
            q = q.filter(BetPick.season == season)
        if sport in SPORT_KINDS:
            q = q.filter(BetPick.kind.in_(SPORT_KINDS[sport]))
        picks = q.all()
    recs = [p for p in picks if p.recommended]

    def split(key):
        groups: Dict[Any, List[BetPick]] = defaultdict(list)
        for p in recs:
            groups[key(p)].append(p)
        return groups

    by_week = split(lambda p: (p.season, p.week))
    return {
        "overall": _record(recs),
        "by_sport": {k: _record(v) for k, v in split(lambda p: "College" if p.kind == "cfb_game" else "NFL").items()},
        "by_confidence": {k: _record(v) for k, v in split(lambda p: p.confidence).items()},
        "by_market": {k: _record(v) for k, v in split(lambda p: p.market).items()},
        "by_week": [{"season": s, "week": w, **_record(v)} for (s, w), v in sorted(by_week.items(), reverse=True)],
        "calibration": calibration(picks),
        "lines_tracked": len(picks),
        "picks": [_pick_out(p) for p in sorted(recs, key=lambda p: (p.season, p.week, p.units), reverse=True)],
    }
