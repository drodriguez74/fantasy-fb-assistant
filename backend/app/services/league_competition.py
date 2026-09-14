"""Real per-league waiver competition signal.

Sleeper's trending-add feed (used to rank waiver recommendations) tells you
demand across every Sleeper league on earth -- not whether anyone in THIS
specific league actually needs the position. This module answers that
second question using data this app already has for free once a league is
connected: every other team's own real roster.

A team is "thin" at a position when what it has rostered there doesn't
clear its own effective starter requirement with any bench cushion --
computed with the exact same FLEX-aware `effective_position_requirements`
helper roster_grading.py uses to grade the connected user's own roster, just
applied to every other team in the league instead. The result is a real,
per-league "how many of the other N teams are pressed at this position"
ratio -- not a guess at who specifically wants which specific player (ESPN's
API has no visibility into other teams' pending waiver claims at all, so
that's not knowable), but a legitimate, honest proxy: a position several
other rosters are thin at is one where a claim is more likely to be
contested, regardless of who wins it.
"""
from typing import Any, Dict, List

from app.services.roster_requirements import effective_position_requirements

# Kicker/DEF benches are routinely 0 by design (most leagues stream them) --
# "thin" has no real meaning there, so this signal only covers positions
# where bench depth is an actual roster-construction choice.
COMPETITION_POSITIONS = ("QB", "RB", "WR", "TE")


def compute_position_pressure(
    teams: List[Dict[str, Any]],
    league_settings: Dict[str, Any] | None,
    exclude_team_id: str | None,
) -> Dict[str, Dict[str, Any]]:
    pressure: Dict[str, Dict[str, Any]] = {
        pos: {"teams_in_need": 0, "total_teams": 0} for pos in COMPETITION_POSITIONS
    }

    for team in teams:
        if exclude_team_id is not None and str(team.get("team_id")) == str(exclude_team_id):
            continue
        roster = team.get("roster") or []
        counts: Dict[str, int] = {}
        for p in roster:
            pos = (p.get("position") or "").upper()
            counts[pos] = counts.get(pos, 0) + 1

        requirements = effective_position_requirements(counts, league_settings or {})

        for pos in COMPETITION_POSITIONS:
            need = requirements.get(pos, 0)
            have = counts.get(pos, 0)
            pressure[pos]["total_teams"] += 1
            # No bench cushion above what they need to start = thin.
            if have <= need:
                pressure[pos]["teams_in_need"] += 1

    for pos, d in pressure.items():
        total = d["total_teams"] or 1
        ratio = d["teams_in_need"] / total
        d["ratio"] = round(ratio, 2)
        d["level"] = "high" if ratio >= 0.4 else ("low" if ratio < 0.15 else "medium")

    return pressure
