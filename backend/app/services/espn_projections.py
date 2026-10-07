"""ESPN's weekly projected stat lines, as a second opinion for the betting
board (betting_service).

ESPN's public fantasy feed (no league or login needed) carries a per-stat
projection for every player each week. Compared against the books' lines on
the week-5 2026 slate it was about as close as Sleeper's (16.5% vs 15.3%
median error after each source's offset is removed), so it isn't used as the
primary source -- but where the two disagree on which side of a line a
player lands, the "edge" is usually one source's noise, so the board
requires ESPN to agree before sizing a bet.

Rows are returned keyed by normalized name with Sleeper's stat keys, so
betting_service's market -> stat mapping works unchanged.
"""
import json
import logging
import time
from typing import Any, Dict, Tuple

import httpx

from app.services.weekly_projections import normalize_name

logger = logging.getLogger(__name__)

_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leaguedefaults/3"
_TTL_SECONDS = 3 * 3600
# ESPN stat id -> Sleeper stat key.
ESPN_STAT_KEYS = {"3": "pass_yd", "24": "rush_yd", "25": "rush_td", "42": "rec_yd", "43": "rec_td", "53": "rec"}
_SLOTS = [0, 2, 4, 6]  # QB, RB, WR, TE

_cache: Dict[Tuple[int, int], Tuple[float, Dict[str, Dict[str, float]]]] = {}


async def fetch_espn_weekly_projections(season: int, week: int) -> Dict[str, Dict[str, float]]:
    """{normalized player name: {sleeper stat key: projected value}} for the
    week. {} on any failure -- the board then runs without the cross-check."""
    key = (int(season), int(week))
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < _TTL_SECONDS:
        return cached[1]
    flt = {"players": {
        "filterStatsForSourceIds": {"value": [1]},           # projections
        "filterStatsForSplitTypeIds": {"value": [1]},        # single week
        "filterStatsForCurrentSeasonScoringPeriodId": {"value": [int(week)]},
        "filterSlotIds": {"value": _SLOTS},
        "sortPercOwned": {"sortAsc": False, "sortPriority": 1},
        "limit": 1500,
    }}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                _URL.format(season=int(season)),
                params={"view": "kona_player_info", "scoringPeriodId": int(week)},
                headers={"X-Fantasy-Filter": json.dumps(flt)},
            )
            response.raise_for_status()
            players = response.json().get("players") or []
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as e:
        logger.warning("ESPN projections fetch failed: %s", type(e).__name__)
        return {}
    out: Dict[str, Dict[str, float]] = {}
    for entry in players:
        player = entry.get("player") or {}
        for stat in player.get("stats") or []:
            if stat.get("statSourceId") == 1 and stat.get("scoringPeriodId") == int(week):
                raw: Dict[str, Any] = stat.get("stats") or {}
                out[normalize_name(player.get("fullName") or "")] = {
                    sleeper_key: float(raw[espn_id]) for espn_id, sleeper_key in ESPN_STAT_KEYS.items() if espn_id in raw
                }
    if out:
        _cache[key] = (time.monotonic(), out)
    return out
