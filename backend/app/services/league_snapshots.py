"""Builders for the per-league snapshot cache.

Each builder takes a `UserLeague` and returns the exact response body its
endpoint used to compute inline. They are called both synchronously (cold
load) and from a background task (stale refresh), so they must not depend on
request scope and must raise `SnapshotBuildError` (not HTTPException) for
expected upstream failures -- the endpoint layer maps that to a 400.

See app.services.snapshot_cache for the stale-while-revalidate wrapper and
the kind -> (builder, ttl) registry.
"""
from typing import Any, Dict

import asyncio

from app.models.user_league import UserLeague
from app.services.espn_service_enhanced import espn_service_enhanced
from app.services.yahoo_service import yahoo_service
from app.services.yahoo_tokens import get_valid_yahoo_token
from app.services.sleeper_service import sleeper_service
from app.services.roster_grading import grade_roster
from app.services.this_week_service import build_this_week as _build_this_week
from app.services.league_competition import compute_position_pressure


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


_HEALTHY_STATUSES = {"ACTIVE", "NORMAL", "HEALTHY", ""}


async def _require_yahoo_token(user_league: UserLeague) -> str:
    """Usable Yahoo access token (renewed first if expired -- see
    yahoo_tokens.get_valid_yahoo_token), shared by every Yahoo snapshot
    builder. Raises SnapshotBuildError (mapped to a 400) rather than a raw
    exception when there's nothing usable -- same honest "reconnect"
    message used everywhere else.
    """
    if not user_league.yahoo_access_token:
        raise SnapshotBuildError(
            "Yahoo account not connected for this league. Please reconnect your Yahoo account."
        )
    access_token = await get_valid_yahoo_token(user_league)
    if not access_token:
        raise SnapshotBuildError(
            "Your Yahoo connection has expired. Please reconnect your Yahoo account."
        )
    return access_token


async def _build_sleeper_roster_analysis_snapshot(
    user_league: UserLeague, league_info: Dict[str, Any], ungraded: Dict[str, Any]
) -> Dict[str, Any]:
    """Real Sleeper roster composition + grade.

    Sleeper's roster fetch (`get_league_rosters`) only ever returns raw
    player-id lists (`players`/`starters`/`reserve`) -- no per-player name,
    position, or projection like ESPN's formatted roster. Those are
    resolved here against `get_all_players()` (the same global player
    catalog already used for waiver/trade). There's no real per-player
    season projection available from Sleeper's roster endpoints (unlike
    ESPN's server-computed `projected_total_points`), so `projected_points`
    is honestly left at 0 rather than inventing one -- `grade_roster`
    already degrades gracefully to composition-only grading (no avg-
    projection-based strengths/weaknesses) when that's the case, the same
    honest tradeoff used elsewhere in this codebase for Sleeper data.
    """
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

    raw_league_info, rosters, users, all_players = await asyncio.gather(
        sleeper_service.get_league_info(user_league.league_id),
        sleeper_service.get_league_rosters(user_league.league_id),
        sleeper_service.get_league_users(user_league.league_id),
        sleeper_service.get_all_players(),
    )
    if isinstance(rosters, list) and rosters and isinstance(rosters[0], dict) and "error" in rosters[0]:
        raise SnapshotBuildError(rosters[0]["error"])
    if isinstance(all_players, dict) and "error" in all_players:
        raise SnapshotBuildError(all_players["error"])

    target_roster = next(
        (r for r in rosters if isinstance(r, dict) and str(r.get("roster_id")) == str(user_league.team_id)),
        None,
    )
    if not target_roster:
        raise SnapshotBuildError(f"Roster {user_league.team_id} not found in this Sleeper league")

    users_by_id = {u.get("user_id"): u for u in users if isinstance(u, dict)}
    owner = users_by_id.get(target_roster.get("owner_id"), {})
    team_name = (
        (owner.get("metadata") or {}).get("team_name")
        or owner.get("display_name")
        or f"Team {target_roster.get('roster_id')}"
    )

    starter_ids = set(target_roster.get("starters") or [])
    reserve_ids = set(target_roster.get("reserve") or [])
    player_ids = [pid for pid in (target_roster.get("players") or []) if isinstance(pid, str)]

    def _resolve(pid: str) -> Dict[str, Any]:
        data = all_players.get(pid) if isinstance(all_players, dict) else None
        lineup_slot = "IR" if pid in reserve_ids else ("STARTER" if pid in starter_ids else "BE")
        if not isinstance(data, dict):
            return {
                "name": f"Unknown Player ({pid})",
                "position": "UNKNOWN",
                "team": None,
                "lineup_slot": lineup_slot,
                "projected_points": 0.0,
                "injury_status": "ACTIVE",
            }
        name = (
            data.get("full_name")
            or f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
            or "Unknown Player"
        )
        # Sleeper's real injury_status is "NA" for the large majority of
        # its "NA"-tagged players (verified live against Sleeper's public
        # player catalog: mostly inactive/practice-squad players with no
        # real team, not a real injury designation) -- treating it as an
        # injury concern would flag players with nothing wrong with them.
        # None (no status on file at all) is Sleeper's actual healthy
        # default and was already handled; "NA" needs the same treatment.
        raw_status = data.get("injury_status")
        injury_status = "ACTIVE" if raw_status in (None, "NA") else raw_status
        return {
            "name": name,
            "position": data.get("position") or "UNKNOWN",
            "team": data.get("team"),
            "lineup_slot": lineup_slot,
            "projected_points": 0.0,
            "injury_status": injury_status,
        }

    players = [_resolve(pid) for pid in player_ids]
    starting_lineup = [p for p in players if p["lineup_slot"] not in ("BE", "IR")]
    bench_players = [p for p in players if p["lineup_slot"] in ("BE", "IR")]

    injury_concerns = [
        {"player": p["name"], "position": p["position"], "team": p["team"], "status": p["injury_status"]}
        for p in players
        if (p["injury_status"] or "").upper() not in _HEALTHY_STATUSES
    ]

    league_settings = None
    if isinstance(raw_league_info, dict) and "error" not in raw_league_info:
        parsed = sleeper_service.parse_league_settings(raw_league_info)
        if "error" not in parsed:
            league_settings = parsed

    grading = grade_roster(players, league_settings)

    return {
        "league_info": league_info,
        "roster_analysis": {
            "team_name": team_name,
            "owner": owner.get("display_name", "Unknown Owner"),
            "roster_size": len(players),
            "total_players": len(players),
            "composition": {
                "starting_lineup": starting_lineup,
                "bench_players": bench_players,
                "composition_score": grading["composition_score"],
            },
            "overall_grade": {
                "grade": grading["grade"],
                "score": grading["composition_score"],
                "description": "Composition grade based on this league's real roster-slot requirements. No real per-player projection is available from Sleeper's roster data, so this reflects real roster construction only, not player quality.",
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


# Yahoo's own real roster-slot codes for a starter vs. bench vs. IR player
# (selected_position, confirmed live against a real 14-player roster --
# "QB"/"RB"/"WR"/"TE"/"W/R/T"/"K"/"DEF" for starters, "BN" for bench,
# "IR" for injured reserve) -- map to the BE/IR vocabulary grade_roster
# and the ESPN/Sleeper builders above already use.
_YAHOO_BENCH_SLOTS = {"BN"}
_YAHOO_IR_SLOTS = {"IR", "IR+"}


async def _build_yahoo_roster_analysis_snapshot(
    user_league: UserLeague, league_info: Dict[str, Any], ungraded: Dict[str, Any]
) -> Dict[str, Any]:
    """Real Yahoo roster composition + grade.

    Mirrors the Sleeper builder above: Yahoo's own `get_team_roster` (see
    yahoo_service.py) already returns real per-player name/position/team/
    selected_position/status, but no real per-player weekly or season
    projection (unlike ESPN's server-computed `projected_total_points`) --
    `projected_points` is honestly left at 0.0 rather than inventing one,
    same tradeoff already accepted for Sleeper. `grade_roster` degrades
    gracefully to composition-only grading in that case.
    """
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
                        "description": "Your team is not identified for this league yet. Please reconnect your Yahoo account to auto-detect it, or set it via PUT /leagues/{league_id}/settings.",
                    },
                },
            },
        }

    access_token = await _require_yahoo_token(user_league)
    team_key = yahoo_service.build_team_key(user_league.league_key, user_league.team_id)
    if not team_key:
        raise SnapshotBuildError("Team ID not configured for this Yahoo league.")

    roster_data = await yahoo_service.get_team_roster(access_token, team_key)
    if "error" in roster_data:
        raise SnapshotBuildError(roster_data["error"])

    raw_players = roster_data.get("players", [])

    def _lineup_slot(p: Dict[str, Any]) -> str:
        slot = (p.get("selected_position") or "").upper()
        if slot in _YAHOO_IR_SLOTS:
            return "IR"
        if slot in _YAHOO_BENCH_SLOTS:
            return "BE"
        return slot or "BE"

    # Yahoo's real injury status abbreviations (O/Q/D/IR/PUP/...) come back
    # as None for a healthy player -- normalize to the same "ACTIVE"
    # sentinel the ESPN/Sleeper builders use so _HEALTHY_STATUSES matches.
    players = [
        {
            "name": p.get("name") or "Unknown Player",
            "position": p.get("position") or "UNKNOWN",
            "team": p.get("team"),
            "lineup_slot": _lineup_slot(p),
            "projected_points": 0.0,
            "injury_status": p.get("status") or "ACTIVE",
        }
        for p in raw_players
    ]
    starting_lineup = [p for p in players if p["lineup_slot"] not in ("BE", "IR")]
    bench_players = [p for p in players if p["lineup_slot"] in ("BE", "IR")]

    injury_concerns = [
        {"player": p["name"], "position": p["position"], "team": p["team"], "status": p["injury_status"]}
        for p in players
        if (p["injury_status"] or "").upper() not in _HEALTHY_STATUSES
    ]

    league_settings = None
    if user_league.league_key:
        yahoo_settings = await yahoo_service.get_league_settings(access_token, user_league.league_key)
        if "error" not in yahoo_settings and yahoo_settings.get("starters"):
            league_settings = {"starters": yahoo_settings["starters"]}

    grading = grade_roster(players, league_settings)

    # Real team display info -- get_team_roster's own team lookup already
    # has name/manager for exactly this team (it fetched the roster via
    # this team's own team_key), so reuse it rather than a second call.
    team_name = None
    owner = None
    teams = await yahoo_service.get_league_teams(access_token, user_league.league_key)
    if isinstance(teams, list) and teams and not (isinstance(teams[0], dict) and "error" in teams[0]):
        my_team = next((t for t in teams if str(t.get("team_id")) == str(user_league.team_id)), None)
        if my_team:
            team_name = my_team.get("name")
            owner = my_team.get("manager")

    return {
        "league_info": league_info,
        "roster_analysis": {
            "team_name": team_name,
            "owner": owner,
            "roster_size": len(players),
            "total_players": len(players),
            "composition": {
                "starting_lineup": starting_lineup,
                "bench_players": bench_players,
                "composition_score": grading["composition_score"],
            },
            "overall_grade": {
                "grade": grading["grade"],
                "score": grading["composition_score"],
                "description": "Composition grade based on this league's real roster-slot requirements. No real per-player projection is available from Yahoo's roster data, so this reflects real roster construction only, not player quality.",
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

    if league_info["platform"] == "SLEEPER":
        return await _build_sleeper_roster_analysis_snapshot(user_league, league_info, ungraded)

    if league_info["platform"] == "YAHOO":
        return await _build_yahoo_roster_analysis_snapshot(user_league, league_info, ungraded)

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
        access_token = await _require_yahoo_token(user_league)
        teams = await yahoo_service.get_league_teams(
            access_token, user_league.league_key
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


async def build_position_pressure_snapshot(user_league: UserLeague) -> Dict[str, Any]:
    """How thin the OTHER teams in this league are at each skill position,
    from their own real rosters -- see league_competition.py. Used to tell
    a waiver recommendation apart from a genuinely contested one."""
    league_info = _league_info(user_league)

    if league_info["platform"] != "ESPN":
        return {
            "league_info": league_info,
            "supported": False,
            "detail": f"Waiver competition isn't available for {league_info['platform']} leagues yet.",
        }

    teams, settings, week_lineups = await asyncio.gather(
        espn_service_enhanced.get_league_teams(
            league_id=user_league.league_id,
            season=user_league.season,
            swid=user_league.espn_swid,
            espn_s2=user_league.espn_s2,
        ),
        espn_service_enhanced.get_scoring_and_roster_settings(
            league_id=user_league.league_id,
            season=user_league.season,
            swid=user_league.espn_swid,
            espn_s2=user_league.espn_s2,
        ),
        espn_service_enhanced.get_league_week_lineups(
            league_id=user_league.league_id,
            season=user_league.season,
            swid=user_league.espn_swid,
            espn_s2=user_league.espn_s2,
        ),
    )
    if teams and isinstance(teams, list) and "error" in teams[0]:
        raise SnapshotBuildError(teams[0]["error"])
    if "error" in settings:
        settings = None
    # This week's acute-need signal is a bonus, not load-bearing -- a
    # transient failure fetching it (e.g. box scores not posted yet in
    # week 1) degrades to season-depth-only rather than failing the whole
    # snapshot.
    week_lineups_list = week_lineups.get("teams") if isinstance(week_lineups, dict) and "error" not in week_lineups else None

    pressure = compute_position_pressure(
        teams, settings, exclude_team_id=user_league.team_id, week_lineups=week_lineups_list
    )

    return {
        "league_info": league_info,
        "supported": True,
        "position_pressure": pressure,
        "other_teams_considered": max(0, len(teams) - (1 if user_league.team_id else 0)),
    }


async def _build_yahoo_bye_week_radar_snapshot(
    user_league: UserLeague, league_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Yahoo's real Bye Week Radar -- mirrors the ESPN builder below.
    Yahoo's own `bye_weeks.week` per-player field (yahoo_service.
    get_team_roster) needs no week-clamping workaround the way ESPN's
    box_scores-based path did -- it isn't derived from a per-week call
    at all."""
    if not user_league.team_id:
        return {
            "league_info": league_info,
            "supported": False,
            "detail": "Your team isn't identified for this league yet. Please reconnect your Yahoo account to auto-detect it, or set it via PUT /leagues/{league_id}/settings.",
        }

    access_token = await _require_yahoo_token(user_league)
    team_key = yahoo_service.build_team_key(user_league.league_key, user_league.team_id)
    if not team_key:
        return {
            "league_info": league_info,
            "supported": False,
            "detail": "Your team isn't identified for this league yet. Set it via PUT /leagues/{league_id}/settings.",
        }

    radar = await yahoo_service.get_bye_week_radar(access_token, user_league.league_key, team_key)
    if "error" in radar:
        raise SnapshotBuildError(radar["error"])

    return {
        "league_info": league_info,
        "supported": True,
        "team_name": radar["team_name"],
        "current_week": radar["current_week"],
        "upcoming_byes": radar["upcoming_byes"],
    }


async def build_bye_week_radar_snapshot(user_league: UserLeague) -> Dict[str, Any]:
    """Real upcoming bye weeks for this team's roster.

    See espn_service_enhanced.get_bye_week_radar's docstring for why this
    doesn't use box_scores/on_bye_week: that path is confirmed wrong for
    any week beyond the current one (League.box_scores silently clamps a
    future `week` back to the current week rather than fetching it). This
    builder instead crosses ESPN's real per-team bye-week schedule against
    the roster directly, with no such clamping."""
    league_info = _league_info(user_league)

    if league_info["platform"] == "YAHOO":
        return await _build_yahoo_bye_week_radar_snapshot(user_league, league_info)

    if league_info["platform"] != "ESPN":
        return {
            "league_info": league_info,
            "supported": False,
            "detail": f"Bye week radar isn't available for {league_info['platform']} leagues yet.",
        }
    if not user_league.team_id:
        return {
            "league_info": league_info,
            "supported": False,
            "detail": "Your team isn't identified for this league yet. Set it via PUT /leagues/{league_id}/settings.",
        }

    radar = await espn_service_enhanced.get_bye_week_radar(
        league_id=user_league.league_id,
        team_id=user_league.team_id,
        season=user_league.season,
        swid=user_league.espn_swid,
        espn_s2=user_league.espn_s2,
    )
    if "error" in radar:
        raise SnapshotBuildError(radar["error"])

    return {
        "league_info": league_info,
        "supported": True,
        "team_name": radar["team_name"],
        "current_week": radar["current_week"],
        "upcoming_byes": radar["upcoming_byes"],
    }


async def _build_yahoo_matchup_history_snapshot(
    user_league: UserLeague, league_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Yahoo's real "Matchups" screen -- mirrors the ESPN builder below,
    sourced from yahoo_service.get_team_matchup_history (real per-week
    scoreboard data, same platform limitation as This Week: real team
    totals, no real per-player breakdown needed here anyway)."""
    if not user_league.team_id:
        return {
            "league_info": league_info,
            "supported": False,
            "detail": "Your team isn't identified for this league yet. Please reconnect your Yahoo account to auto-detect it, or set it via PUT /leagues/{league_id}/settings.",
        }

    access_token = await _require_yahoo_token(user_league)
    team_key = yahoo_service.build_team_key(user_league.league_key, user_league.team_id)
    if not team_key:
        return {
            "league_info": league_info,
            "supported": False,
            "detail": "Your team isn't identified for this league yet. Set it via PUT /leagues/{league_id}/settings.",
        }

    yahoo_league_info = await yahoo_service.get_league_info(access_token, user_league.league_key)
    through_week = yahoo_league_info.get("current_week") if "error" not in yahoo_league_info else None
    try:
        through_week = int(through_week) if through_week is not None else None
    except (TypeError, ValueError):
        through_week = None
    if through_week is None:
        raise SnapshotBuildError("This league's current week isn't available yet.")

    history = await yahoo_service.get_team_matchup_history(
        access_token, user_league.league_key, team_key, through_week
    )
    if "error" in history:
        raise SnapshotBuildError(history["error"])

    wins = sum(1 for m in history["matchups"] if m["result"] == "win")
    losses = sum(1 for m in history["matchups"] if m["result"] == "loss")
    ties = sum(1 for m in history["matchups"] if m["result"] == "tie")

    return {
        "league_info": league_info,
        "supported": True,
        "through_week": history["through_week"],
        "matchups": history["matchups"],
        "record": {"wins": wins, "losses": losses, "ties": ties},
    }


async def build_matchup_history_snapshot(user_league: UserLeague) -> Dict[str, Any]:
    """The real "Matchups" screen: this team's actual result every week of
    the season so far, not just the current week (that's This Week's job).
    See espn_service_enhanced.get_team_matchup_history."""
    league_info = _league_info(user_league)

    if league_info["platform"] == "YAHOO":
        return await _build_yahoo_matchup_history_snapshot(user_league, league_info)

    if league_info["platform"] != "ESPN":
        return {
            "league_info": league_info,
            "supported": False,
            "detail": f"Matchup history isn't available for {league_info['platform']} leagues yet.",
        }
    if not user_league.team_id:
        return {
            "league_info": league_info,
            "supported": False,
            "detail": "Your team isn't identified for this league yet. Set it via PUT /leagues/{league_id}/settings.",
        }

    history = await espn_service_enhanced.get_team_matchup_history(
        league_id=user_league.league_id,
        team_id=user_league.team_id,
        season=user_league.season,
        swid=user_league.espn_swid,
        espn_s2=user_league.espn_s2,
    )
    if "error" in history:
        raise SnapshotBuildError(history["error"])

    wins = sum(1 for m in history["matchups"] if m["result"] == "win")
    losses = sum(1 for m in history["matchups"] if m["result"] == "loss")
    ties = sum(1 for m in history["matchups"] if m["result"] == "tie")

    return {
        "league_info": league_info,
        "supported": True,
        "through_week": history["through_week"],
        "matchups": history["matchups"],
        "record": {"wins": wins, "losses": losses, "ties": ties},
    }
