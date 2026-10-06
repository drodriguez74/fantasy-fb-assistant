"""Vegas game lines -> implied team totals, from The Odds API
(the-odds-api.com, `ODDS_API_KEY`).

A team's implied total is the points the betting market expects it to
score: (game total - its spread) / 2. A favored team at -7 in a 45-point
game is implied for 26, its opponent for 19. It's the sharpest public
read on scoring environment -- the core signal for streaming a defense
(face a low implied total) or a kicker (play for a high one).

One request returns spreads + totals for every upcoming NFL game across
DraftKings, FanDuel and Hard Rock Bet for 2 credits. The line used is the
median across those books. Results are cached for 6 hours (~8 credits a
day), so the free tier's 500 credits/month covers it. Without a key, or on
any failure, callers get {} and simply show no odds -- never a guess.
"""
import asyncio
import json
import logging
import statistics
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

BOOKMAKERS = ("draftkings", "fanduel", "hardrockbet")
SOURCE = "Vegas consensus (DraftKings, FanDuel, Hard Rock Bet)"
_CACHE_TTL_SECONDS = 6 * 3600
_cache: Dict[str, Any] = {}

# The Odds API's full team names -> the abbreviations ESPN uses.
TEAM_ABBR: Dict[str, str] = {
    "Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF", "Carolina Panthers": "CAR", "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE", "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN", "Detroit Lions": "DET", "Green Bay Packers": "GB",
    "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC", "Las Vegas Raiders": "LV", "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LAR", "Miami Dolphins": "MIA", "Minnesota Vikings": "MIN",
    "New England Patriots": "NE", "New Orleans Saints": "NO", "New York Giants": "NYG",
    "New York Jets": "NYJ", "Philadelphia Eagles": "PHI", "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF", "Seattle Seahawks": "SEA", "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN", "Washington Commanders": "WSH",
}

# Other platforms' spellings of the same teams (Yahoo, Sleeper, older feeds).
_ALIASES = {"WAS": "WSH", "JAC": "JAX", "LA": "LAR", "STL": "LAR", "OAK": "LV", "SD": "LAC"}


def normalize_team(abbr: Optional[str]) -> Optional[str]:
    if not abbr:
        return None
    a = abbr.strip().upper()
    return _ALIASES.get(a, a)


def week_cutoff(now: datetime) -> datetime:
    """End of the current NFL week: the next Tuesday 10:00 UTC (after
    Monday night's game ends). A game before this is this week's game."""
    days = (1 - now.weekday()) % 7  # Tuesday == 1
    cutoff = (now + timedelta(days=days)).replace(hour=10, minute=0, second=0, microsecond=0)
    return cutoff if cutoff > now else cutoff + timedelta(days=7)


def implied_totals(games: List[Dict[str, Any]], now: datetime) -> Dict[str, Dict[str, Any]]:
    """{team abbr: {implied_total, opponent, opponent_implied_total, spread,
    game_total, home, kickoff}} for every team playing before week_cutoff.
    Teams on bye are absent. Pure -- takes the API's JSON."""
    cutoff = week_cutoff(now)
    out: Dict[str, Dict[str, Any]] = {}
    for g in games:
        try:
            kickoff = datetime.fromisoformat(g["commence_time"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if kickoff >= cutoff:
            continue
        home, away = g.get("home_team"), g.get("away_team")
        totals: List[float] = []
        home_spreads: List[float] = []
        for book in g.get("bookmakers") or []:
            for market in book.get("markets") or []:
                for o in market.get("outcomes") or []:
                    if o.get("point") is None:
                        continue
                    if market.get("key") == "totals" and o.get("name") == "Over":
                        totals.append(float(o["point"]))
                    elif market.get("key") == "spreads" and o.get("name") == home:
                        home_spreads.append(float(o["point"]))
        if not totals or not home_spreads or home not in TEAM_ABBR or away not in TEAM_ABBR:
            continue
        total = statistics.median(totals)
        spread = statistics.median(home_spreads)  # negative = home favored
        home_pts = round((total - spread) / 2, 1)
        away_pts = round(total - home_pts, 1)
        h, a = TEAM_ABBR[home], TEAM_ABBR[away]
        common = {"game_total": total, "kickoff": kickoff.isoformat()}
        out[h] = {"implied_total": home_pts, "opponent": a, "opponent_implied_total": away_pts,
                  "spread": spread, "home": True, **common}
        out[a] = {"implied_total": away_pts, "opponent": h, "opponent_implied_total": home_pts,
                  "spread": -spread, "home": False, **common}
    return out


# Player prop markets fetched per game (each market costs 1 credit per game).
PROP_MARKETS = ("player_pass_yds", "player_rush_yds", "player_reception_yds", "player_receptions", "player_anytime_td")
# PrizePicks lines come back with the props for comparison (pick'em, not odds).
PROP_BOOKMAKERS = BOOKMAKERS + ("prizepicks",)
_PROPS_TTL_SECONDS = 24 * 3600  # a full slate is ~70 credits; once a day at most
# Never spend the last credits on props: game lines (implied totals) need
# them too. Prop fetches stop once the account is at or below this.
CREDIT_RESERVE = 60

_credits: Dict[str, Optional[int]] = {"remaining": None}


# ---------------------------------------------------------------------------
# Cache: memory, then the odds_cache table (survives restarts -- Render's
# free tier sleeps when idle, and refetching a slate of props costs ~70
# credits), then the API.
# ---------------------------------------------------------------------------

def _db_read(key: str) -> Optional[Tuple[datetime, Any]]:
    from app.db.base import SessionLocal
    from app.models.odds_cache import OddsCache
    try:
        with SessionLocal() as db:
            row = db.get(OddsCache, key)
            if row is None:
                return None
            fetched = row.fetched_at if row.fetched_at.tzinfo else row.fetched_at.replace(tzinfo=timezone.utc)
            return fetched, json.loads(row.payload)
    except Exception as e:  # noqa: BLE001 - the cache is an optimization, never fatal
        logger.warning("odds_cache read failed for %s: %s", key, type(e).__name__)
        return None


def _db_write(key: str, data: Any) -> None:
    from app.db.base import SessionLocal
    from app.models.odds_cache import OddsCache
    try:
        with SessionLocal() as db:
            row = db.get(OddsCache, key) or OddsCache(key=key)
            row.payload = json.dumps(data)
            row.fetched_at = datetime.now(timezone.utc)
            db.add(row)
            db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("odds_cache write failed for %s: %s", key, type(e).__name__)


async def _cache_get(key: str, ttl_seconds: float) -> Optional[Any]:
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < ttl_seconds:
        return cached[1]
    stored = await asyncio.to_thread(_db_read, key)
    if stored:
        age = (datetime.now(timezone.utc) - stored[0]).total_seconds()
        if age < ttl_seconds:
            _cache[key] = (time.monotonic() - age, stored[1])
            return stored[1]
    return None


async def _cache_put(key: str, data: Any) -> None:
    _cache[key] = (time.monotonic(), data)
    await asyncio.to_thread(_db_write, key, data)


async def credits_remaining_async() -> Optional[int]:
    """Credits left as of the last API response, from memory or the
    persisted value (None before the first call ever)."""
    if _credits["remaining"] is None:
        stored = await asyncio.to_thread(_db_read, "credits")
        if stored and isinstance(stored[1], int):
            _credits["remaining"] = stored[1]
    return _credits["remaining"]


def credits_remaining() -> Optional[int]:
    """Credits left as of the last API response seen by this process."""
    return _credits["remaining"]


async def _get(path: str, params: Dict[str, Any]) -> Optional[Any]:
    url = f"https://api.the-odds-api.com/v4/sports/americanfootball_nfl{path}"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, params={"apiKey": settings.ODDS_API_KEY, **params})
            response.raise_for_status()
            data = response.json()
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as e:
        # Never log the URL: it carries the API key.
        logger.warning("Odds API %s failed: %s", path, type(e).__name__)
        return None
    remaining = response.headers.get("x-requests-remaining")
    if remaining is not None:
        try:
            _credits["remaining"] = int(float(remaining))
            await asyncio.to_thread(_db_write, "credits", _credits["remaining"])
        except ValueError:
            pass
    logger.info("Odds API %s: %s credits remaining", path, remaining)
    return data


async def get_game_lines() -> List[Dict[str, Any]]:
    """Every upcoming game's spreads + totals across BOOKMAKERS (raw API
    shape), cached 6h. [] without a key or on failure."""
    if not settings.ODDS_API_KEY:
        return []
    cached = await _cache_get("games", _CACHE_TTL_SECONDS)
    if cached is not None:
        return cached
    games = await _get("/odds", {"bookmakers": ",".join(BOOKMAKERS), "markets": "spreads,totals", "oddsFormat": "american"})
    if not isinstance(games, list):
        return []
    await _cache_put("games", games)
    return games


def this_week(games: List[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
    cutoff = week_cutoff(now)
    out = []
    for g in games:
        try:
            kickoff = datetime.fromisoformat(g["commence_time"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if now - timedelta(hours=4) <= kickoff < cutoff:
            out.append(g)
    return out


async def get_event_props(event_id: str) -> Optional[Dict[str, Any]]:
    """One game's player props (PROP_MARKETS across PROP_BOOKMAKERS), cached
    12h per game. None when unavailable or when spending would dip below
    CREDIT_RESERVE -- the caller reports that rather than guessing."""
    if not settings.ODDS_API_KEY:
        return None
    key = f"props:{event_id}"
    cached = await _cache_get(key, _PROPS_TTL_SECONDS)
    if cached is not None:
        return cached
    remaining = await credits_remaining_async()
    if remaining is not None and remaining - len(PROP_MARKETS) < CREDIT_RESERVE:
        logger.warning("Odds API: skipping props for %s, %s credits left (reserve %s)", event_id, remaining, CREDIT_RESERVE)
        return None
    data = await _get(f"/events/{event_id}/odds", {
        "bookmakers": ",".join(PROP_BOOKMAKERS),
        "markets": ",".join(PROP_MARKETS),
        "oddsFormat": "american",
    })
    if not isinstance(data, dict):
        return None
    await _cache_put(key, data)
    return data


async def get_implied_totals() -> Dict[str, Dict[str, Any]]:
    """This week's implied totals keyed by ESPN team abbreviation (use
    normalize_team on the lookup key). {} without a key or on failure."""
    games = await get_game_lines()
    return implied_totals(games, datetime.now(timezone.utc)) if games else {}
