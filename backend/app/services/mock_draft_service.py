"""
Mock Draft Grading

Grades a client-side mock draft (frontend/src/pages/DraftPage.tsx) purely from
the roster data the frontend already has and sends us -- there is no
guaranteed local DB `Player` row for mock-draft players (Sleeper IDs), so
this module never touches the database and is plain, synchronous, and
unit-testable in isolation.

Conventions are deliberately kept in sync with the real connected-league path
in `post_draft_analysis_service.py`:
  - composition scoring uses the same `standard_lineup` counts and the same
    per-position scoring formula as `_analyze_roster_composition`.
  - letter grade thresholds reuse `grading.grade_from_score` (A>=90, B>=80,
    C>=70, D>=60, else F) -- the same thresholds `_grade_from_score` uses.
  - per-pick value reuses the same `round_expectations` table and
    value_percentage/value_category/value_grade thresholds as
    `_calculate_draft_value`.

Where this deliberately differs from the real path: `_calculate_draft_value`
compares a player's real projected fantasy points against an expected-points-
by-round baseline pulled from the DB. Mock-draft players are Sleeper IDs with
no reliable local DB row, so there's no trustworthy points-by-round baseline
for every player. Instead:
  - Primary signal: if the player has a `search_rank` or `adp` (both already
    expressed on a "draft pick" scale -- rank/ADP ~= the pick you'd expect
    them to go), compare that against the *actual* overall pick they were
    taken at. Taken later than their rank/ADP suggested = good value; taken
    earlier = a reach. `search_rank` is preferred when both are present
    since it's the same signal this codebase already sorts positional
    rankings by (see `draft.py::get_positional_rankings`); `adp` is the
    fallback.
  - Secondary signal: if neither `search_rank` nor `adp` is present but
    `projected_points` is, fall back to the exact real-path calculation
    (round_expectations[round] vs projected_points).
  - If none of `search_rank`, `adp`, or `projected_points` are present,
    value for that pick is honestly reported as "Insufficient Data" rather
    than fabricated.
"""

from typing import Any, Dict, List, Optional

from app.services.grading import grade_from_score

# Standard 1-QB lineup requirements, identical to
# PostDraftAnalysisService._analyze_roster_composition's `standard_lineup`.
STANDARD_LINEUP = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1}

# Identical to PostDraftAnalysisService._calculate_draft_value's
# `round_expectations` -- rough expected fantasy points for a player drafted
# in a given round. Used only as the projected_points-based fallback when a
# player has no search_rank/adp to compare against their actual pick.
ROUND_EXPECTATIONS = {
    1: 250, 2: 220, 3: 190, 4: 160, 5: 140, 6: 120,
    7: 100, 8: 85, 9: 75, 10: 65, 11: 55, 12: 50,
}
DEFAULT_ROUND_EXPECTATION = 40


def _value_category_and_grade(value_percentage: float) -> tuple[str, str]:
    """Identical thresholds to `_calculate_draft_value`'s value_category/value_grade."""
    if value_percentage >= 120:
        return "Excellent Value", "A"
    elif value_percentage >= 110:
        return "Good Value", "B"
    elif value_percentage >= 90:
        return "Fair Value", "C"
    elif value_percentage >= 70:
        return "Slight Reach", "D"
    else:
        return "Significant Reach", "F"


def _score_composition(user_roster: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Mirrors `_analyze_roster_composition`'s scoring formula and shape."""
    position_counts: Dict[str, int] = {}
    for player in user_roster:
        position = (player.get("position") or "UNKNOWN").upper()
        position_counts[position] = position_counts.get(position, 0) + 1

    composition_score = 0.0
    position_breakdown: Dict[str, Any] = {}

    for position, standard_count in STANDARD_LINEUP.items():
        actual_count = position_counts.get(position, 0)

        if actual_count >= standard_count:
            position_score = min(100, 80 + (actual_count - standard_count) * 10)
        else:
            position_score = (actual_count / standard_count) * 80

        position_breakdown[position] = {
            "players_drafted": actual_count,
            "recommended_minimum": standard_count,
            "depth_score": round(position_score, 1),
            "needs_attention": actual_count < standard_count,
            "overstocked": actual_count > standard_count + 1,
        }

        composition_score += position_score

    composition_score = composition_score / len(STANDARD_LINEUP)

    return {
        "composition_score": round(composition_score, 1),
        "position_breakdown": position_breakdown,
    }


def _pick_value(player: Dict[str, Any]) -> Dict[str, Any]:
    """Compute one drafted player's pick-value entry.

    Returns a dict always containing player_name/position/round/pick, plus
    either (value_percentage, value_category, value_grade) when we have a
    usable signal, or an honest "Insufficient Data" marker when we don't.
    """
    base = {
        "player_name": player.get("full_name", "Unknown"),
        "position": player.get("position", "UNKNOWN"),
        "round": player.get("round"),
        "pick": player.get("pick"),
    }

    search_rank = player.get("search_rank")
    adp = player.get("adp")
    projected_points = player.get("projected_points")
    overall_pick = player.get("pick")

    actual_rank = search_rank if search_rank is not None else adp

    if actual_rank is not None and overall_pick is not None and actual_rank > 0:
        # Primary signal: rank/ADP vs. the actual overall pick they went at.
        # Picked later than their rank suggested (actual_rank < pick) is
        # good value; picked earlier is a reach.
        value_percentage = (overall_pick / actual_rank) * 100
        value_category, value_grade = _value_category_and_grade(value_percentage)
        return {
            **base,
            "value_percentage": round(value_percentage, 1),
            "value_category": value_category,
            "value_grade": value_grade,
        }

    if projected_points is not None:
        # Fallback: exact real-path logic (round_expectations vs projected points).
        draft_round = player.get("round") or 0
        expected_points = ROUND_EXPECTATIONS.get(draft_round, DEFAULT_ROUND_EXPECTATION)
        value_percentage = (projected_points / expected_points * 100) if expected_points > 0 else 100
        value_category, value_grade = _value_category_and_grade(value_percentage)
        return {
            **base,
            "value_percentage": round(value_percentage, 1),
            "value_category": value_category,
            "value_grade": value_grade,
        }

    # No search_rank, no adp, no projected_points -- don't fabricate a score.
    return {
        **base,
        "value_percentage": None,
        "value_category": "Insufficient Data",
        "value_grade": "N/A",
    }


def _build_final_analysis(
    draft_settings: Dict[str, Any],
    composition: Dict[str, Any],
    value_analysis: List[Dict[str, Any]],
    draft_grade: str,
) -> str:
    """Build a short human-readable summary, e.g.
    'Solid RB depth (3 drafted) but reached on your QB in round 4...'
    """
    sentences: List[str] = []

    team_count = draft_settings.get("team_count")
    scoring_format = draft_settings.get("scoring_format")
    context_bits = []
    if team_count:
        context_bits.append(f"{team_count}-team")
    if scoring_format:
        context_bits.append(str(scoring_format))
    context = " ".join(context_bits)
    intro = f"Overall grade: {draft_grade} for this{(' ' + context) if context else ''} mock draft."
    sentences.append(intro)

    breakdown = composition["position_breakdown"]
    strong_positions = [
        pos for pos, info in breakdown.items()
        if not info["needs_attention"] and info["depth_score"] >= 90
    ]
    weak_positions = [pos for pos, info in breakdown.items() if info["needs_attention"]]

    if strong_positions:
        sentences.append(
            "Solid depth at " + ", ".join(strong_positions) + "."
        )
    if weak_positions:
        sentences.append(
            "Needs attention at " + ", ".join(weak_positions) + " -- below the recommended minimum."
        )

    scored_picks = [v for v in value_analysis if v["value_percentage"] is not None]
    reaches = [v for v in scored_picks if v["value_grade"] in ("D", "F")]
    steals = [v for v in scored_picks if v["value_grade"] in ("A", "B")]

    if reaches:
        worst = sorted(reaches, key=lambda v: v["value_percentage"])[:2]
        reach_desc = ", ".join(
            f"{r['player_name']} ({r['position']}, round {r['round']})" for r in worst
        )
        sentences.append(f"Reached on {reach_desc}.")

    if steals:
        best = sorted(steals, key=lambda v: v["value_percentage"], reverse=True)[:2]
        steal_desc = ", ".join(
            f"{s['player_name']} ({s['position']}, round {s['round']})" for s in best
        )
        sentences.append(f"Great value on {steal_desc}.")

    insufficient_count = len(value_analysis) - len(scored_picks)
    if insufficient_count > 0 and len(value_analysis) > 0:
        fraction = insufficient_count / len(value_analysis)
        if insufficient_count > 2 or fraction > 0.2:
            sentences.append(
                f"Note: {insufficient_count} of {len(value_analysis)} picks had no ranking or "
                "projection data available, so their draft value couldn't be assessed."
            )

    return " ".join(sentences)


def grade_mock_draft(
    draft_settings: Dict[str, Any],
    user_roster: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Grade a completed mock draft roster.

    Pure function: no DB access, safe to unit test directly.

    Returns a dict with composition_score, position_breakdown, value_analysis
    (list of per-pick dicts), draft_grade (letter), and final_analysis (text).
    """
    composition = _score_composition(user_roster)

    value_analysis = [_pick_value(player) for player in user_roster]

    draft_grade = grade_from_score(composition["composition_score"])

    final_analysis = _build_final_analysis(
        draft_settings, composition, value_analysis, draft_grade
    )

    return {
        "composition_score": composition["composition_score"],
        "position_breakdown": composition["position_breakdown"],
        "value_analysis": value_analysis,
        "draft_grade": draft_grade,
        "final_analysis": final_analysis,
    }
