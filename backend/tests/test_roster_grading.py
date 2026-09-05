"""Unit tests for app/services/roster_grading.py's grade_roster, focused on
the bye-week collision wiring added on top of the pre-existing composition
grading (see app/services/grading.py for the shared primitives)."""

from app.services.grading import combined_grade
from app.services.roster_grading import grade_roster

# Deliberately implausible names -- grade_roster best-effort backfills
# `bye_week` from the local Player table by name when a player dict doesn't
# already carry one, and this suite needs full control over which players
# do/don't have bye_week data. Names that can't possibly match a real row
# keep that enrichment a no-op so these tests aren't at the mercy of
# whatever happens to be in the connected DB.
_UNMATCHABLE_NAME = "Zzyzx Qqxv Fixture Nonplayer"


def _full_roster(qb_byes):
    """A roster shaped to exactly satisfy the fallback starter requirements
    (QB 1, RB 2, WR 2, TE 1, K 1, DEF 1) with two rostered QBs, so any grade
    delta between two calls comes only from the QBs' bye weeks.
    """
    players = [
        {"name": f"{_UNMATCHABLE_NAME} QB{i}", "position": "QB", "projected_points": 20.0, "bye_week": bye}
        for i, bye in enumerate(qb_byes)
    ]
    # RB/WR/TE/K/DEF deliberately carry no bye_week here -- exactly 2 RBs
    # and 2 WRs against a required count of 2 means *any* single bye week
    # assigned to one of them would itself create a shortfall collision
    # (active 1 < required 2), which would confound a test that's only
    # trying to isolate the QB bye-week signal.
    players += [
        {"name": f"{_UNMATCHABLE_NAME} RB{i}", "position": "RB", "projected_points": 12.0}
        for i in range(2)
    ]
    players += [
        {"name": f"{_UNMATCHABLE_NAME} WR{i}", "position": "WR", "projected_points": 10.0}
        for i in range(2)
    ]
    players.append({"name": f"{_UNMATCHABLE_NAME} TE", "position": "TE", "projected_points": 8.0})
    players.append({"name": f"{_UNMATCHABLE_NAME} K", "position": "K", "projected_points": 7.0})
    players.append({"name": f"{_UNMATCHABLE_NAME} DEF", "position": "DEF", "projected_points": 9.0})
    return players


def test_grade_roster_penalizes_colliding_qb_byes_vs_staggered():
    colliding = grade_roster(_full_roster(qb_byes=[11, 11]))
    staggered = grade_roster(_full_roster(qb_byes=[10, 11]))

    # Composition is identical between the two rosters -- only the QB bye
    # weeks differ -- so composition_score must be unaffected.
    assert colliding["composition_score"] == staggered["composition_score"]

    assert colliding["bye_week_collisions"] == [
        {"position": "QB", "week": 11, "active_count": 0, "required": 1}
    ]
    assert staggered["bye_week_collisions"] == []

    assert colliding["components"]["bye_weeks"] < staggered["components"]["bye_weeks"]
    assert colliding["overall_score"] < staggered["overall_score"]
    # Letter grades are coarse (10-point buckets), so a lower overall_score
    # doesn't always cross a letter boundary -- but it must never rank
    # *better* than the staggered roster's.
    from app.services.grading import grade_from_score

    assert grade_from_score(colliding["overall_score"]) == colliding["grade"]
    assert grade_from_score(staggered["overall_score"]) == staggered["grade"]


def test_grade_roster_handles_missing_bye_week_data_without_crashing_or_penalizing():
    players = [
        {"name": f"{_UNMATCHABLE_NAME} QB1", "position": "QB", "projected_points": 20.0},
        {"name": f"{_UNMATCHABLE_NAME} QB2", "position": "QB", "projected_points": 18.0},
        {"name": f"{_UNMATCHABLE_NAME} RB1", "position": "RB", "projected_points": 12.0},
        {"name": f"{_UNMATCHABLE_NAME} RB2", "position": "RB", "projected_points": 11.0},
        {"name": f"{_UNMATCHABLE_NAME} WR1", "position": "WR", "projected_points": 10.0},
        {"name": f"{_UNMATCHABLE_NAME} WR2", "position": "WR", "projected_points": 9.0},
        {"name": f"{_UNMATCHABLE_NAME} TE", "position": "TE", "projected_points": 8.0},
        {"name": f"{_UNMATCHABLE_NAME} K", "position": "K", "projected_points": 7.0},
        {"name": f"{_UNMATCHABLE_NAME} DEF", "position": "DEF", "projected_points": 9.0},
    ]

    result = grade_roster(players)

    assert result["bye_week_collisions"] == []
    # No bye_week data anywhere means "no detectable collision risk" (100),
    # not a penalty for missing data -- combined_grade with the same inputs
    # should reproduce the exact overall_score/grade grade_roster returned.
    expected = combined_grade(
        composition_score=result["composition_score"], value_score=None, bye_weeks_score=100.0
    )
    assert result["overall_score"] == expected["overall_score"]
    assert result["grade"] == expected["grade"]
    assert result["components"] == expected["components"]


def test_grade_roster_normalizes_dst_alias_for_bye_week_check():
    # ESPN's own defense position label is "D/ST", not "DEF" -- the
    # bye-week check must use the same alias normalization
    # _position_counts already applies for composition, or a real rostered
    # defense's bye week would silently never be checked at all.
    players = _full_roster(qb_byes=[10, 11])
    for player in players:
        if player["position"] == "DEF":
            player["position"] = "D/ST"

    result = grade_roster(players)
    assert result["composition_score"] > 0
    assert "DEF" in result["position_breakdown"]


def test_grade_roster_preserves_backward_compatible_keys():
    result = grade_roster(_full_roster(qb_byes=[10, 11]))
    # Existing callers (see app/api/v1/endpoints/leagues.py) read these
    # keys directly -- they must keep existing meanings, not be renamed.
    for key in ("composition_score", "position_breakdown", "grade", "strengths", "weaknesses"):
        assert key in result
    # New keys added alongside, not replacing, the old ones.
    for key in ("overall_score", "components", "bye_week_collisions"):
        assert key in result
