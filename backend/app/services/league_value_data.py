"""Platform adapters for league_value_model: turn one connected league into
real rosters, free agents, starter slots and projections in one uniform
shape.

Player shape: {id, name, position, team, season, week, injury_status, slot,
ownership, trending_adds}. `season` is projected season points, `week` this
week's projection (0 on a bye).

- ESPN: every roster in one get_league_teams call; ESPN's own season
  projection and this-week projection (`stats[week].projected_points`);
  300 free agents with ESPN ownership.
- Yahoo: every roster in one get_league_rosters call; projections from
  Sleeper's feed scored with the league's real Yahoo rules (Yahoo has none
  per player -- see weekly_projections.py); 300 free agents with Yahoo
  ownership.

Sleeper's 24h trending-add counts ride along as `trending_adds` -- a demand
signal ("other managers are grabbing him"), never the ranking itself. Names
come from the Sleeper projection rows already fetched, so no 5MB player
catalog download.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

from app.models.user_league import UserLeague
from app.services.espn_service_enhanced import espn_service_enhanced
from app.services.sleeper_service import sleeper_service
from app.services.weekly_projections import (
    attach_projections,
    fetch_rest_of_season_projections,
    fetch_season_projections,
    fetch_weekly_projections,
    normalize_name,
    season_window,
)
from app.services.yahoo_service import yahoo_service
from app.services.yahoo_tokens import get_valid_yahoo_token

logger = logging.getLogger(__name__)


class LeagueDataError(Exception):
    """Expected, user-facing failure (not connected, token expired, ...)."""


def _status(value: Any) -> str:
    return value.upper() if isinstance(value, str) else ""


async def _trending_by_name(season: int) -> Dict[str, int]:
    trending, rows = await asyncio.gather(
        sleeper_service.get_trending_players("add", 24, 200),
        fetch_season_projections(season),
        return_exceptions=True,
    )
    if not isinstance(trending, list) or not isinstance(rows, list):
        return {}
    name_by_id = {
        str(r.get("player_id")): normalize_name(
            f"{(r.get('player') or {}).get('first_name', '')} {(r.get('player') or {}).get('last_name', '')}"
        )
        for r in rows if r.get("player_id")
    }
    out: Dict[str, int] = {}
    for t in trending:
        if not isinstance(t, dict):
            continue
        name = name_by_id.get(str(t.get("player_id")))
        if name:
            out[name] = int(t.get("count") or 0)
    return out


async def load_league_value_data(league: UserLeague) -> Dict[str, Any]:
    platform = league.platform.value.upper()
    if not league.team_id:
        raise LeagueDataError("Your team isn't identified for this league yet. Set it from league settings.")
    if platform == "ESPN":
        data = await _load_espn(league)
    elif platform == "YAHOO":
        data = await _load_yahoo(league)
    else:
        raise LeagueDataError(f"Waiver and trade analysis isn't available for {platform} leagues yet.")

    trending = await _trending_by_name(league.season)
    for p in data["free_agents"]:
        p["trending_adds"] = trending.get(normalize_name(p["name"]), 0)
    data["my_team_id"] = str(league.team_id)
    return data


# ---------------------------------------------------------------------------
# ESPN
# ---------------------------------------------------------------------------

def _espn_player(p: Dict[str, Any], week: Optional[int]) -> Dict[str, Any]:
    stats = p.get("stats") or {}
    # espn_api keys per-week stats by int (json dumps show them as strings).
    week_stats = (stats.get(week) or stats.get(str(week))) if week is not None else None
    week_proj = (week_stats or {}).get("projected_points")
    return {
        "id": f"espn:{p.get('player_id')}",
        "name": p.get("name"),
        "position": p.get("position"),
        "team": p.get("team"),
        "season": float(p.get("projected_points") or 0.0),
        # No entry for this week = no game (bye) or no projection: 0.
        "week": float(week_proj or 0.0),
        "injury_status": _status(p.get("injury_status")),
        "slot": (p.get("lineup_slot") or "").upper() or None,
        "ownership": p.get("percent_owned"),
        "espn_player_id": p.get("player_id"),
    }


async def _load_espn(league: UserLeague) -> Dict[str, Any]:
    kw = dict(league_id=league.league_id, season=league.season, swid=league.espn_swid, espn_s2=league.espn_s2)
    teams, free_agents, settings, info = await asyncio.gather(
        espn_service_enhanced.get_league_teams(**kw),
        espn_service_enhanced.get_available_players(size=300, **kw),
        espn_service_enhanced.get_scoring_and_roster_settings(**kw),
        espn_service_enhanced.get_league_info(**kw),
    )
    if not teams or (isinstance(teams, list) and "error" in teams[0]):
        raise LeagueDataError("Your ESPN connection is missing or has expired. Please reconnect your ESPN account.")
    if "error" in settings or not settings.get("starters"):
        raise LeagueDataError("This league's roster settings couldn't be loaded.")
    week = info.get("current_week") if isinstance(info, dict) and "error" not in info else None
    trade_deadline = info.get("trade_deadline") if isinstance(info, dict) and "error" not in info else None

    fa_list = free_agents if isinstance(free_agents, list) and not (free_agents and "error" in free_agents[0]) else []
    return {
        "platform": "ESPN",
        "current_week": week,
        "trade_deadline": trade_deadline,
        "starters": settings["starters"],
        "projection_source": "ESPN rest-of-season projections",
        "teams": [
            {
                "team_id": str(t.get("team_id")),
                "team_name": t.get("team_name"),
                "players": [_espn_player(p, week) for p in t.get("roster", [])],
            }
            for t in teams
        ],
        "free_agents": [_espn_player(p, week) for p in fa_list],
    }


# ---------------------------------------------------------------------------
# Yahoo
# ---------------------------------------------------------------------------

async def _load_yahoo(league: UserLeague) -> Dict[str, Any]:
    token = await get_valid_yahoo_token(league)
    if not token:
        raise LeagueDataError("Your Yahoo connection is missing or has expired. Please reconnect your Yahoo account.")

    # Yahoo's default free-agent ordering left every defense out of the
    # first 300 (confirmed live), so K and DEF get their own pages.
    rosters, free_agents, fa_def, fa_k, settings, info = await asyncio.gather(
        yahoo_service.get_league_rosters(token, league.league_key),
        yahoo_service.get_available_players(token, league.league_key, count=300),
        yahoo_service.get_available_players(token, league.league_key, position="DEF", count=25),
        yahoo_service.get_available_players(token, league.league_key, position="K", count=25),
        yahoo_service.get_league_settings(token, league.league_key),
        yahoo_service.get_league_info(token, league.league_key),
    )
    if not rosters or "error" in rosters[0]:
        raise LeagueDataError(rosters[0]["error"] if rosters else "Couldn't load this league's rosters.")
    if "error" in settings or not settings.get("starters"):
        raise LeagueDataError("This league's roster settings couldn't be loaded.")
    week, end_week = season_window(info)

    # Rest-of-season, like ESPN's own `projected_total_points` -- see
    # fetch_rest_of_season_projections for why not Sleeper's season feed.
    season_rows, week_rows = await asyncio.gather(
        fetch_rest_of_season_projections(league.season, week, end_week),
        fetch_weekly_projections(league.season, week) if week else asyncio.sleep(0, result=[]),
    )
    if not season_rows:
        raise LeagueDataError("Player projections couldn't be loaded right now. Try again shortly.")

    rules, stat_values = settings.get("scoring_rules"), settings.get("stat_values")

    def build(raw: List[Dict[str, Any]], slot_key: Optional[str]) -> List[Dict[str, Any]]:
        players = [
            {
                "id": f"yahoo:{p.get('player_key') or p.get('name')}",
                "name": p.get("name"),
                "position": p.get("position"),
                "team": (p.get("team") or "").upper() or None,
                "injury_status": _status(p.get("status")),
                "slot": (p.get(slot_key) or "").upper() or None if slot_key else None,
                "ownership": p.get("ownership_percentage"),
                "bye_week": p.get("bye_week"),
                "projected_points": None,
            }
            for p in raw if p.get("name")
        ]
        attach_projections(players, season_rows, rules, stat_values)
        for p in players:
            p["season"] = float(p.pop("projected_points") or 0.0)
            p["projected_points"] = None
        if week_rows:
            attach_projections(players, week_rows, rules, stat_values)
        for p in players:
            on_bye = week is not None and p.get("bye_week") == week
            p["week"] = 0.0 if on_bye else float(p.pop("projected_points") or 0.0)
            p.pop("projected_points", None)
        return players

    fa_list: List[Dict[str, Any]] = []
    seen = set()
    for batch in (free_agents, fa_def, fa_k):
        if not isinstance(batch, list) or (batch and "error" in batch[0]):
            continue
        for p in batch:
            if p.get("player_key") not in seen:
                seen.add(p.get("player_key"))
                fa_list.append(p)
    return {
        "platform": "YAHOO",
        "current_week": week,
        "trade_deadline": settings.get("trade_end_date"),
        "starters": settings["starters"],
        "projection_source": "Sleeper rest-of-season projections scored with your league's rules",
        "teams": [
            {"team_id": str(t.get("team_id")), "team_name": t.get("team_name"), "players": build(t.get("players", []), "selected_position")}
            for t in rosters
        ],
        "free_agents": build(fa_list, None),
    }
