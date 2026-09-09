"""Builders for the per-league snapshot cache.

Each builder takes a `UserLeague` and returns the exact response body its
endpoint used to compute inline. They are called both synchronously (cold
load) and from a background task (stale refresh), so they must not depend on
request scope and must raise `SnapshotBuildError` (not HTTPException) for
expected upstream failures -- the endpoint layer maps that to a 400.

See app.services.snapshot_cache for the stale-while-revalidate wrapper and
the kind -> (builder, ttl) registry.
"""
from datetime import datetime
from typing import Any, Dict

from app.models.user_league import UserLeague
from app.services.espn_service_enhanced import espn_service_enhanced
from app.services.yahoo_service import yahoo_service
from app.services.sleeper_service import sleeper_service
from app.services.roster_grading import grade_roster
from app.services.this_week_service import build_this_week as _build_this_week


class SnapshotBuildError(Exception):
    """An expected upstream failure (bad creds, platform error, no team set).
    The endpoint turns this into a 400; the background refresher logs it and
    keeps the previous snapshot."""


def _league_info(user_league: UserLeague) -> Dict[str, Any]:
    return {
        "id": user_league.id,
        "name": user_league.league_name,
        "platform": user_league.platform.value.upper(),
        "season": user_league.season,
        "scoring_format": user_league.scoring_format,
        "league_size": user_league.league_size,
    }


async def build_this_week_snapshot(user_league: UserLeague) -> Dict[str, Any]:
    # this_week_service already returns honest non-ESPN / no-team payloads
    # rather than raising, so nothing to translate here.
    return await _build_this_week(user_league)


async def build_roster_analysis_snapshot(user_league: UserLeague) -> Dict[str, Any]:
    league_info = _league_info(user_league)

    ungraded = {
        "composition": {"starting_lineup": [], "bench_players": [], "composition_score": None},
        "overall_grade": {
            "grade": "N/A",
            "score": None,
            "description": "Roster grading is not yet computed.",
        },
        "strengths_weaknesses": {"strengths": [], "weaknesses": []},
    }

    if league_info["platform"] != "ESPN":
        return {
            "league_info": league_info,
            "roster_analysis": {
                "team_name": None,
                "owner": None,
                "total_players": 0,
                **{
                    **ungraded,
                    "overall_grade": {
                        **ungraded["overall_grade"],
                        "description": f"Roster analysis is not yet implemented for {league_info['platform']} leagues.",
                    },
                },
            },
        }

    if not user_league.team_id:
        return {
            "league_info": league_info,
            "roster_analysis": {
                "team_name": None,
                "owner": None,
                "total_players": 0,
                **{
                    **ungraded,
                    "overall_grade": {
                        **ungraded["overall_grade"],
                        "description": "Your team is not identified for this league yet. Set your team via PUT /leagues/{league_id}/settings to see your real roster.",
                    },
                },
            },
        }

    roster_data = await espn_service_enhanced.get_team_roster(
        league_id=user_league.league_id,
        team_id=user_league.team_id,
        season=user_league.season,
        swid=user_league.espn_swid,
        espn_s2=user_league.espn_s2,
    )
    if "error" in roster_data:
        raise SnapshotBuildError(roster_data["error"])

    players = roster_data.get("players", [])
    starting_lineup = [p for p in players if p.get("lineup_slot") not in ("BE", "IR")]
    bench_players = [p for p in players if p.get("lineup_slot") in ("BE", "IR")]

    _HEALTHY = {"ACTIVE", "NORMAL", "HEALTHY", ""}
    injury_concerns = [
        {
            "player": p.get("name"),
            "position": p.get("position"),
            "team": p.get("team"),
            "status": p.get("injury_status"),
        }
        for p in players
        if (p.get("injury_status") or "").upper() not in _HEALTHY
    ]

    league_settings = await espn_service_enhanced.get_scoring_and_roster_settings(
        league_id=user_league.league_id,
        season=user_league.season,
        swid=user_league.espn_swid,
        espn_s2=user_league.espn_s2,
    )
    if "error" in league_settings:
        league_settings = None
    grading = grade_roster(players, league_settings)

    return {
        "league_info": league_info,
        "roster_analysis": {
            "team_name": roster_data.get("team_name"),
            "owner": roster_data.get("owner"),
            "roster_size": roster_data.get("roster_size", len(players)),
            "total_players": len(players),
            "composition": {
                "starting_lineup": starting_lineup,
                "bench_players": bench_players,
                "composition_score": grading["composition_score"],
            },
            "overall_grade": {
                "grade": grading["grade"],
                "score": grading["composition_score"],
                "description": "Composition grade based on this league's real roster-slot requirements.",
                "player_count": len(players),
            },
            "strengths_weaknesses": {
                "strengths": grading["strengths"],
                "weaknesses": grading["weaknesses"],
            },
            "injury_concerns": injury_concerns,
            "players": players,
        },
    }


async def build_standings_snapshot(user_league: UserLeague) -> Dict[str, Any]:
    platform = user_league.platform.value.upper()
    base = {"league_name": user_league.league_name, "season": user_league.season}

    if platform == "ESPN":
        standings = await espn_service_enhanced.get_standings(
            league_id=user_league.league_id,
            season=user_league.season,
            swid=user_league.espn_swid,
            espn_s2=user_league.espn_s2,
        )
        if standings and isinstance(standings, list) and "error" in standings[0]:
            raise SnapshotBuildError(standings[0]["error"])
        return {**base, "teams": standings}

    if platform == "YAHOO":
        if not user_league.yahoo_access_token:
            raise SnapshotBuildError(
                "Yahoo account not connected for this league. Please reconnect your Yahoo account."
            )
        if (
            user_league.yahoo_token_expires_at
            and user_league.yahoo_token_expires_at < datetime.utcnow()
        ):
            raise SnapshotBuildError(
                "Your Yahoo connection has expired. Please reconnect your Yahoo account."
            )
        teams = await yahoo_service.get_league_teams(
            user_league.yahoo_access_token, user_league.league_key
        )
        if teams and isinstance(teams, list) and "error" in teams[0]:
            raise SnapshotBuildError(teams[0]["error"])
        teams.sort(key=lambda t: (-int(t.get("wins", 0) or 0), -float(t.get("points_for", 0) or 0)))
        for i, team in enumerate(teams):
            team["rank"] = i + 1
        return {**base, "teams": teams}

    if platform == "SLEEPER":
        teams = await sleeper_service.get_league_teams(user_league.league_id)
        if teams and isinstance(teams, list) and "error" in teams[0]:
            raise SnapshotBuildError(teams[0]["error"])
        teams.sort(key=lambda t: -int(t.get("wins", 0) or 0))
        for i, team in enumerate(teams):
            team["rank"] = i + 1
        return {**base, "teams": teams}

    raise SnapshotBuildError(f"Standings are not yet implemented for {platform} leagues.")
