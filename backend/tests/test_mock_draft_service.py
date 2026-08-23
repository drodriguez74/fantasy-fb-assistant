"""
Unit tests for the pure mock-draft grading function
(app/services/mock_draft_service.py). No DB, no HTTP -- just the math.
"""

from app.services.grading import grade_from_score
from app.services.mock_draft_service import grade_mock_draft


def make_player(sleeper_id, full_name, position, team, round_, pick,
                 search_rank=None, adp=None, projected_points=None):
    return {
        "sleeper_id": sleeper_id,
        "full_name": full_name,
        "position": position,
        "team": team,
        "round": round_,
        "pick": pick,
        "search_rank": search_rank,
        "adp": adp,
        "projected_points": projected_points,
    }


def test_grade_from_score_thresholds():
    assert grade_from_score(95) == "A"
    assert grade_from_score(90) == "A"
    assert grade_from_score(89.9) == "B"
    assert grade_from_score(80) == "B"
    assert grade_from_score(70) == "C"
    assert grade_from_score(60) == "D"
    assert grade_from_score(59.9) == "F"
    assert grade_from_score(0) == "F"


def test_good_roster_gets_high_composition_score_and_grade():
    # Surplus at every position (including K/DEF) -> depth_score == 90 at
    # every position -> composition_score == 90 -> grade A.
    roster = [
        make_player("1", "QB One", "QB", "AAA", 1, 1, search_rank=1),
        make_player("2", "QB Two", "QB", "BBB", 8, 90, search_rank=95),
        make_player("3", "RB One", "RB", "CCC", 2, 13, search_rank=14),
        make_player("4", "RB Two", "RB", "DDD", 3, 25, search_rank=30),
        make_player("5", "RB Three", "RB", "EEE", 9, 100, search_rank=110),
        make_player("6", "WR One", "WR", "FFF", 4, 37, search_rank=40),
        make_player("7", "WR Two", "WR", "GGG", 5, 49, search_rank=55),
        make_player("8", "WR Three", "WR", "HHH", 10, 115, search_rank=130),
        make_player("9", "TE One", "TE", "III", 6, 61, search_rank=65),
        make_player("10", "TE Two", "TE", "JJJ", 11, 125, search_rank=140),
        make_player("11", "K One", "K", "KKK", 12, 133, search_rank=150),
        make_player("12", "K Two", "K", "LLL", 13, 145, search_rank=160),
        make_player("13", "DEF One", "DEF", "MMM", 14, 157, search_rank=170),
        make_player("14", "DEF Two", "DEF", "NNN", 15, 169, search_rank=180),
    ]

    result = grade_mock_draft(
        {"scoring_format": "PPR", "team_count": 12, "draft_position": 1, "total_rounds": 15},
        roster,
    )

    assert result["composition_score"] == 90.0
    assert result["draft_grade"] == "A"
    assert result["position_breakdown"]["QB"]["players_drafted"] == 2
    assert result["position_breakdown"]["QB"]["needs_attention"] is False
    assert len(result["value_analysis"]) == len(roster)
    assert "A" in result["final_analysis"] or "grade" in result["final_analysis"].lower()


def test_bad_roster_missing_key_positions_gets_low_grade():
    # No QB, no TE, no K, no DEF, and only 1 RB / 1 WR drafted.
    roster = [
        make_player("1", "RB One", "RB", "AAA", 1, 1, search_rank=1),
        make_player("2", "WR One", "WR", "BBB", 2, 13, search_rank=14),
    ]

    result = grade_mock_draft(
        {"scoring_format": "PPR", "team_count": 12, "draft_position": 1, "total_rounds": 15},
        roster,
    )

    # QB: 0/1 * 80 = 0; RB: 1/2 * 80 = 40; WR: 1/2 * 80 = 40;
    # TE: 0; K: 0; DEF: 0 -> avg = 80/6 = 13.33
    assert result["composition_score"] < 20
    assert result["draft_grade"] == "F"
    assert result["position_breakdown"]["QB"]["needs_attention"] is True
    assert result["position_breakdown"]["TE"]["players_drafted"] == 0


def test_pick_value_uses_search_rank_over_adp_when_both_present():
    # Picked at overall pick 100 with search_rank 50 (better than the pick
    # implies) -> good value, despite a much worse adp being present too.
    roster = [
        make_player("1", "Sleeper Star", "WR", "AAA", 9, 100, search_rank=50, adp=200.0),
    ]
    result = grade_mock_draft({"scoring_format": "PPR", "team_count": 10, "draft_position": 1, "total_rounds": 15}, roster)
    entry = result["value_analysis"][0]
    assert entry["value_grade"] in ("A", "B")
    assert entry["value_category"] in ("Excellent Value", "Good Value")


def test_pick_value_flags_a_reach():
    # Taken at pick 5 but ranked only 50th -> a clear reach.
    roster = [
        make_player("1", "Reach Guy", "RB", "AAA", 1, 5, search_rank=50),
    ]
    result = grade_mock_draft({"scoring_format": "PPR", "team_count": 10, "draft_position": 5, "total_rounds": 15}, roster)
    entry = result["value_analysis"][0]
    assert entry["value_grade"] == "F"
    assert entry["value_category"] == "Significant Reach"


def test_pick_value_falls_back_to_projected_points_when_no_rank_or_adp():
    # No search_rank/adp, but projected_points is present -> use the
    # round_expectations fallback rather than flat insufficient-data.
    roster = [
        make_player("1", "Proj Only", "RB", "AAA", 1, 3, projected_points=300),
    ]
    result = grade_mock_draft({"scoring_format": "PPR", "team_count": 10, "draft_position": 3, "total_rounds": 15}, roster)
    entry = result["value_analysis"][0]
    assert entry["value_category"] != "Insufficient Data"
    assert entry["value_grade"] == "A"  # 300 / 250 (round 1 expectation) = 120% -> Excellent


def test_pick_value_is_honestly_insufficient_when_no_signal_at_all():
    roster = [
        make_player("1", "No Data Guy", "TE", "AAA", 12, 140),
    ]
    result = grade_mock_draft({"scoring_format": "PPR", "team_count": 10, "draft_position": 10, "total_rounds": 15}, roster)
    entry = result["value_analysis"][0]
    assert entry["value_category"] == "Insufficient Data"
    assert entry["value_grade"] == "N/A"
    assert entry["value_percentage"] is None
