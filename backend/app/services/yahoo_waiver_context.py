"""Per-player waiver enrichment for Yahoo leagues -- the Yahoo counterpart
to the `espn_enrichment` / `team_bye_map` pair both waiver paths already
build for ESPN (see waiver_wire.py::_fetch_connected_roster_and_settings).

- Ownership %: Yahoo's own `percent_owned` on each free agent.
- Season projection: Sleeper's full-season projection scored with the
  league's real Yahoo rules (Yahoo publishes none per player -- see
  weekly_projections.py). None when a free agent has no projection.
- This-week byes: every NFL team with a player rostered anywhere in the
  league, from each rostered player's real Yahoo `bye_week`. Teams nobody
  in the league rosters aren't covered -- same honest limit as ESPN's map.
"""
import asyncio
from typing import Any, Dict, List, Optional, Tuple

from app.services.weekly_projections import attach_projections, fetch_season_projections
from app.services.yahoo_service import yahoo_service


async def build_yahoo_waiver_context(
    access_token: str,
    league_key: str,
    season: int,
    free_agents: List[Dict[str, Any]],
    league_settings: Optional[Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Dict[str, Any]]], Optional[Dict[str, bool]]]:
    """Returns (enrichment keyed by lower-cased name, team_bye_map keyed by
    upper-case NFL team). Either is None when its source couldn't be loaded;
    never raises."""
    rosters, projection_rows, league_info = await asyncio.gather(
        yahoo_service.get_league_rosters(access_token, league_key),
        fetch_season_projections(season),
        yahoo_service.get_league_info(access_token, league_key),
        return_exceptions=True,
    )

    enrichment: Optional[Dict[str, Dict[str, Any]]] = None
    if free_agents:
        pool = [
            {
                "name": p.get("name"),
                "team": p.get("team"),
                "position": p.get("position"),
                "projected_points": None,
                "ownership_percentage": p.get("ownership_percentage"),
            }
            for p in free_agents if p.get("name")
        ]
        if isinstance(projection_rows, list) and projection_rows:
            settings = league_settings or {}
            attach_projections(pool, projection_rows, settings.get("scoring_rules"), settings.get("stat_values"))
        enrichment = {
            p["name"].lower(): {
                "ownership_percentage": p["ownership_percentage"],
                "season_projected_points": (
                    round(p["projected_points"], 1) if p.get("projected_points") is not None else None
                ),
                # ESPN-only field (drives ESPN headshots); no Yahoo equivalent.
                "espn_player_id": None,
                "team": (p.get("team") or "").upper() or None,
            }
            for p in pool
        }

    team_bye_map: Optional[Dict[str, bool]] = None
    try:
        current_week = int(league_info.get("current_week")) if isinstance(league_info, dict) and "error" not in league_info else None
    except (TypeError, ValueError):
        current_week = None
    if current_week is not None and isinstance(rosters, list) and rosters and "error" not in rosters[0]:
        team_bye_map = {}
        for team in rosters:
            for p in team.get("players", []):
                abbr = (p.get("team") or "").upper()
                if abbr and abbr not in team_bye_map and p.get("bye_week"):
                    team_bye_map[abbr] = p["bye_week"] == current_week

    return enrichment, team_bye_map
