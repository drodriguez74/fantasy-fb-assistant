"""
Real Team Analysis grading for connected leagues (ESPN/Yahoo/Sleeper).

Pure, deterministic, no AI calls and no DB access -- mirrors
`mock_draft_service.py`'s approach of operating on plain player dicts, since a
real ESPN/Yahoo/Sleeper roster's players aren't guaranteed to have a matching
local `Player` row. Generalizes `mock_draft_service._score_composition`'s
formula to use a connected league's REAL starter requirements (from
`espn_service_enhanced.get_scoring_and_roster_settings` or the Sleeper/Yahoo
equivalents) instead of a fixed standard lineup, via
`DraftAssistantService._effective_position_requirements` (already
FLEX-aware). Strengths/weaknesses reuses
`PostDraftAnalysisService._identify_strengths_weaknesses`'s real,
quality-aware (avg `projected_points`, not just raw counts) per-position
rules, adapted from ORM `Player` attribute access to plain dict access.

This intentionally does NOT call `ai_service` -- per explicit direction, real
computed data/formulas are used wherever they're sufficient, which they are
here (every input is a real number already returned by the platform's own
roster fetch).
"""

from typing import Any, Dict, List, Optional

from app.services.grading import grade_from_score
from app.services.draft_assistant_service import draft_assistant

# Same fallback used elsewhere in this codebase when no real per-league
# roster settings are available (see DraftAssistantService.FALLBACK_ROSTER_REQUIREMENTS).
_FALLBACK_STARTERS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1}


# ESPN's own player.position for a defense is "D/ST", but real per-league
# starter requirements (get_scoring_and_roster_settings) already normalize
# that same slot to "DEF" (see espn_service_enhanced.py's own label_map) --
# without this, a real rostered defense was invisible to the requirement
# check (0/1 "DEF" instead of the real 1/1), silently understating the grade.
_POSITION_ALIASES = {"D/ST": "DEF"}


def _position_counts(players: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for player in players:
        position = (player.get("position") or "UNKNOWN").upper()
        position = _POSITION_ALIASES.get(position, position)
        counts[position] = counts.get(position, 0) + 1
    return counts


def _score_composition(
    position_counts: Dict[str, int], requirements: Dict[str, int]
) -> Dict[str, Any]:
    """Mirrors mock_draft_service._score_composition's exact formula, but
    parameterized by the connected league's real starter requirements
    instead of a hardcoded standard lineup.
    """
    if not requirements:
        requirements = _FALLBACK_STARTERS

    composition_score = 0.0
    position_breakdown: Dict[str, Any] = {}

    for position, required_count in requirements.items():
        if required_count <= 0:
            continue
        actual_count = position_counts.get(position, 0)

        if actual_count >= required_count:
            position_score = min(100, 80 + (actual_count - required_count) * 10)
        else:
            position_score = (actual_count / required_count) * 80

        position_breakdown[position] = {
            "players_drafted": actual_count,
            "recommended_minimum": required_count,
            "depth_score": round(position_score, 1),
            "needs_attention": actual_count < required_count,
            "overstocked": actual_count > required_count + 1,
        }
        composition_score += position_score

    composition_score = composition_score / len(position_breakdown) if position_breakdown else 0.0

    return {
        "composition_score": round(composition_score, 1),
        "position_breakdown": position_breakdown,
    }


def _identify_strengths_weaknesses(players: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Adapted from PostDraftAnalysisService._identify_strengths_weaknesses --
    same real, quality-aware per-position rules (count + avg projected_points),
    ported from ORM Player attribute access to plain dict access so it works
    on any platform's roster dicts without a local DB Player match.
    """
    position_groups: Dict[str, List[Dict[str, Any]]] = {}
    for player in players:
        position = (player.get("position") or "UNKNOWN").upper()
        position = _POSITION_ALIASES.get(position, position)
        position_groups.setdefault(position, []).append(player)

    strengths: List[str] = []
    weaknesses: List[str] = []

    for position, group in position_groups.items():
        projections = [p.get("projected_points") or 0 for p in group]
        avg_projection = sum(projections) / len(projections) if projections else 0.0
        player_count = len(group)

        if position == "QB":
            if player_count >= 2 and avg_projection >= 18:
                strengths.append(f"Strong QB depth with {player_count} quality options")
            elif player_count == 1 and avg_projection < 15:
                weaknesses.append("Weak QB situation - consider backup or upgrade")
            elif player_count == 0:
                weaknesses.append("No QB rostered - critical need")

        elif position == "RB":
            if player_count >= 3 and avg_projection >= 12:
                strengths.append(f"Excellent RB depth with {player_count} backs")
            elif player_count < 2:
                weaknesses.append("Insufficient RB depth - high injury risk")
            elif avg_projection < 8:
                weaknesses.append("RB room lacks upside - consider upgrades")

        elif position == "WR":
            if player_count >= 4 and avg_projection >= 10:
                strengths.append(f"Deep WR corps with {player_count} receivers")
            elif player_count < 3:
                weaknesses.append("Thin at WR - need more depth")
            elif avg_projection < 6:
                weaknesses.append("WR group lacks consistent producers")

        elif position == "TE":
            if player_count >= 1 and avg_projection >= 8:
                strengths.append("Solid TE situation")
            elif avg_projection < 5:
                weaknesses.append("TE position is a concern - consider streaming")
            elif player_count == 0:
                weaknesses.append("No TE rostered")

    skill_players = (
        position_groups.get("RB", []) + position_groups.get("WR", []) + position_groups.get("TE", [])
    )
    if len(skill_players) >= 7:
        strengths.append("Strong overall skill position depth")
    elif len(skill_players) < 5:
        weaknesses.append("Lacks sufficient skill position depth")

    return {"strengths": strengths, "weaknesses": weaknesses}


def grade_roster(
    players: List[Dict[str, Any]], league_settings: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Real, deterministic team-analysis grade for a connected league's roster.

    players: flat list of dicts with at least `position` and `projected_points`
             (every platform's roster formatter already produces this shape).
    league_settings: real {"starters": {...}, ...} from
             get_scoring_and_roster_settings (ESPN) or an equivalent
             Sleeper/Yahoo call; falls back to a standard 1-QB lineup when
             None or empty, same fallback used elsewhere in this codebase.

    Returns {"composition_score": float, "grade": str,
             "position_breakdown": {...}, "strengths": [...], "weaknesses": [...]}.
    """
    position_counts = _position_counts(players)
    raw_starters = dict((league_settings or {}).get("starters") or {}) or _FALLBACK_STARTERS
    requirements = draft_assistant._effective_position_requirements(position_counts, {"starters": raw_starters})

    composition = _score_composition(position_counts, requirements)
    grade = grade_from_score(composition["composition_score"])

    # _identify_strengths_weaknesses's per-position rules lean on avg
    # projected_points, not just counts -- if a platform's roster fetch
    # doesn't supply real per-player projections (true for Yahoo/Sleeper's
    # current roster methods, unlike ESPN which computes this server-side),
    # every avg_projection would silently read as 0 and the *count-only*
    # weakness branches (e.g. "avg_projection < 8") would fire for every
    # position regardless of actual roster quality -- a fabricated-looking
    # signal from missing data, not a real one. Skip it honestly instead.
    has_real_projections = any((p.get("projected_points") or 0) > 0 for p in players)
    sw = _identify_strengths_weaknesses(players) if has_real_projections else {"strengths": [], "weaknesses": []}

    return {
        "composition_score": composition["composition_score"],
        "position_breakdown": composition["position_breakdown"],
        "grade": grade,
        "strengths": sw["strengths"],
        "weaknesses": sw["weaknesses"],
    }
