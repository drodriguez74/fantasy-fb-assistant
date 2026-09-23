"""Real per-league waiver competition signal.

Sleeper's trending-add feed (used to rank waiver recommendations) tells you
demand across every Sleeper league on earth -- not whether anyone in THIS
specific league actually needs the position. This module answers that
second question using data this app already has for free once a league is
connected: every other team's own real roster and current-week lineup.

Two real, complementary signals, both computed from actual rosters (never
fabricated):

  - SEASON depth: does a team's roster at this position clear its own
    effective starter requirement with any bench cushion? Reuses the same
    FLEX-aware `effective_position_requirements` helper roster_grading.py
    uses to grade the connected user's own roster -- applied here to every
    OTHER team instead.
  - THIS WEEK'S acute need: is a team's actual starter at this position
    hurt/on bye right now, with no healthy bench player eligible to cover
    that exact slot? This is the sharper, more actionable signal -- a team
    that's thin all season might not act this week, but a team staring at
    an empty lineup slot Sunday almost certainly will.

Neither is "Team X is bidding on Player Y" -- neither ESPN's nor Yahoo's API
has visibility into other teams' pending waiver claims, so that specific fact isn't
knowable. Both ARE real, named, per-team facts ("Dart Vader's starting RB
is on bye and their bench has no healthy RB") that add up to a legitimate,
non-fabricated educated guess about who's likely to be competing for a
given position.
"""
from typing import Any, Dict, List, Optional

from app.services.roster_requirements import effective_position_requirements
from app.services.this_week_service import HEALTHY_STATUSES, IR_SLOTS, _is_starter, _slot_accepts

# Kicker/DEF benches are routinely 0 by design (most leagues stream them) --
# "thin" has no real meaning there, so this signal only covers positions
# where bench depth is an actual roster-construction choice.
COMPETITION_POSITIONS = ("QB", "RB", "WR", "TE")


def _is_compromised(player: Dict[str, Any]) -> bool:
    if player.get("on_bye"):
        return True
    return (player.get("injury_status") or "").upper() not in HEALTHY_STATUSES


def _team_season_need(roster: List[Dict[str, Any]], league_settings: Dict[str, Any] | None) -> Dict[str, bool]:
    counts: Dict[str, int] = {}
    for p in roster:
        pos = (p.get("position") or "").upper()
        counts[pos] = counts.get(pos, 0) + 1
    requirements = effective_position_requirements(counts, league_settings or {})
    return {pos: counts.get(pos, 0) <= requirements.get(pos, 0) for pos in COMPETITION_POSITIONS}


def _team_weekly_need(lineup: List[Dict[str, Any]]) -> Dict[str, bool]:
    starters = [p for p in lineup if _is_starter(p)]
    bench = [p for p in lineup if not _is_starter(p) and (p.get("slot_position") or "").upper() not in IR_SLOTS]

    need: Dict[str, bool] = {pos: False for pos in COMPETITION_POSITIONS}
    for starter in starters:
        pos = (starter.get("position") or "").upper()
        if pos not in COMPETITION_POSITIONS or not _is_compromised(starter):
            continue
        slot = starter.get("slot_position")
        has_healthy_cover = any(
            _slot_accepts(slot, bench_player) and not _is_compromised(bench_player)
            for bench_player in bench
        )
        if not has_healthy_cover:
            need[pos] = True
    return need


def compute_position_pressure(
    teams: List[Dict[str, Any]],
    league_settings: Dict[str, Any] | None,
    exclude_team_id: Optional[str],
    week_lineups: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """`teams` is get_league_teams()'s output (each carries `roster`).
    `week_lineups` is get_league_week_lineups()'s `teams` list (each
    carries `lineup`), optional -- when omitted, only the season signal is
    computed and `this_week` is left empty rather than guessed at."""
    lineups_by_team_id = (
        {str(t.get("team_id")): t.get("lineup", []) for t in week_lineups} if week_lineups else {}
    )

    pressure: Dict[str, Dict[str, Any]] = {
        pos: {
            "season": {"teams_in_need": 0, "total_teams": 0, "team_names": []},
            "this_week": {"teams_in_need": 0, "team_names": []},
        }
        for pos in COMPETITION_POSITIONS
    }

    for team in teams:
        team_id = str(team.get("team_id"))
        if exclude_team_id is not None and team_id == str(exclude_team_id):
            continue
        team_name = team.get("team_name") or "A team"

        season_need = _team_season_need(team.get("roster") or [], league_settings)
        weekly_need = _team_weekly_need(lineups_by_team_id.get(team_id, [])) if lineups_by_team_id else {}

        for pos in COMPETITION_POSITIONS:
            pressure[pos]["season"]["total_teams"] += 1
            if season_need.get(pos):
                pressure[pos]["season"]["teams_in_need"] += 1
                pressure[pos]["season"]["team_names"].append(team_name)
            if weekly_need.get(pos):
                pressure[pos]["this_week"]["teams_in_need"] += 1
                pressure[pos]["this_week"]["team_names"].append(team_name)

    for pos, d in pressure.items():
        season = d["season"]
        total = season["total_teams"] or 1
        season["ratio"] = round(season["teams_in_need"] / total, 2)

        acute = d["this_week"]["teams_in_need"] > 0
        if acute or season["ratio"] >= 0.4:
            level = "high"
        elif season["ratio"] < 0.15:
            level = "low"
        else:
            level = "medium"
        d["level"] = level

    return pressure
