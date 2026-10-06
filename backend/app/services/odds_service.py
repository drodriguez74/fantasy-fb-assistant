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
import logging
import statistics
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_ODDS_URL = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"
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


async def get_implied_totals() -> Dict[str, Dict[str, Any]]:
    """This week's implied totals keyed by ESPN team abbreviation (use
    normalize_team on the lookup key). {} without a key or on failure."""
    if not settings.ODDS_API_KEY:
        return {}
    cached = _cache.get("games")
    if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
        games = cached[1]
    else:
        params = {
            "apiKey": settings.ODDS_API_KEY,
            "bookmakers": ",".join(BOOKMAKERS),
            "markets": "spreads,totals",
            "oddsFormat": "american",
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(_ODDS_URL, params=params)
                response.raise_for_status()
                games = response.json()
            logger.info("Odds API: %s credits remaining", response.headers.get("x-requests-remaining"))
        except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as e:
            # Never log the URL: it carries the API key.
            logger.warning("Odds API fetch failed: %s", type(e).__name__)
            return {}
        if not isinstance(games, list):
            return {}
        _cache["games"] = (time.monotonic(), games)
    return implied_totals(games, datetime.now(timezone.utc))
