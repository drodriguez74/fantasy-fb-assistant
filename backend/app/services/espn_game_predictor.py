"""ESPN's matchup predictor: an independent win probability for each NFL
game (ESPN's FPI-based model), from its public site API. No key, no credits.

Used by the betting board as the cross-check on spreads: the win
probability becomes a projected margin (betting_model.margin_from_win_prob).
"""
import asyncio
import logging
import time
from typing import Dict, Optional, Tuple

import httpx

from app.services.odds_service import normalize_team

logger = logging.getLogger(__name__)

_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary"
_TTL_SECONDS = 3 * 3600
_cache: Dict[Tuple[int, int], Tuple[float, Dict[str, float]]] = {}


async def fetch_home_win_probs(season: int, week: int) -> Dict[str, float]:
    """{home team abbreviation: home win probability} for the week's games.
    {} on failure; a game without a prediction is left out."""
    key = (int(season), int(week))
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < _TTL_SECONDS:
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            board = (await client.get(_SCOREBOARD, params={"week": week, "seasontype": 2, "dates": season})).json()
            events = board.get("events") or []

            async def one(event) -> Optional[Tuple[str, float]]:
                comp = (event.get("competitions") or [{}])[0]
                home = next((c for c in comp.get("competitors") or [] if c.get("homeAway") == "home"), None)
                if not home:
                    return None
                summary = (await client.get(_SUMMARY, params={"event": event.get("id")})).json()
                predictor = summary.get("predictor") or {}
                value = (predictor.get("homeTeam") or {}).get("gameProjection")
                abbr = normalize_team((home.get("team") or {}).get("abbreviation"))
                return (abbr, float(value) / 100) if value is not None and abbr else None

            results = await asyncio.gather(*(one(e) for e in events), return_exceptions=True)
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as e:
        logger.warning("ESPN matchup predictor fetch failed: %s", type(e).__name__)
        return {}
    out = {r[0]: r[1] for r in results if isinstance(r, tuple) and 0 < r[1] < 1}
    if out:
        _cache[key] = (time.monotonic(), out)
    return out


_CFB = "https://site.api.espn.com/apis/site/v2/sports/football/college-football"


def cfb_team_key(name: Optional[str]) -> str:
    """Comparable college team name across ESPN and The Odds API
    ("Florida Int'l" vs "Florida International", "St." vs "State")."""
    text = (name or "").lower().replace("&", "and").replace("st.", "state").replace("'", "")
    return " ".join("".join(ch if ch.isalnum() else " " for ch in text).split())


async def fetch_cfb_home_win_probs() -> Dict[str, float]:
    """{cfb_team_key(home team full name): home win probability} for this
    week's FBS games (ESPN's current week). {} on failure."""
    key = (0, 0)  # one current week
    cached = _cfb_cache.get(key)
    if cached and time.monotonic() - cached[0] < _TTL_SECONDS:
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            board = (await client.get(f"{_CFB}/scoreboard", params={"groups": 80, "limit": 300})).json()
            sem = asyncio.Semaphore(8)

            async def one(event) -> Optional[Tuple[str, float]]:
                comp = (event.get("competitions") or [{}])[0]
                home = next((c for c in comp.get("competitors") or [] if c.get("homeAway") == "home"), None)
                if not home:
                    return None
                async with sem:
                    summary = (await client.get(f"{_CFB}/summary", params={"event": event.get("id")})).json()
                value = ((summary.get("predictor") or {}).get("homeTeam") or {}).get("gameProjection")
                name = (home.get("team") or {}).get("displayName")
                return (cfb_team_key(name), float(value) / 100) if value is not None and name else None

            results = await asyncio.gather(*(one(e) for e in board.get("events") or []), return_exceptions=True)
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as e:
        logger.warning("ESPN CFB predictor fetch failed: %s", type(e).__name__)
        return {}
    out = {r[0]: r[1] for r in results if isinstance(r, tuple) and 0 < r[1] < 1}
    if out:
        _cfb_cache[key] = (time.monotonic(), out)
    return out


_cfb_cache: Dict[Tuple[int, int], Tuple[float, Dict[str, float]]] = {}
