"""Unit tests for the shared grading primitives in app/services/grading.py."""

from app.services.grading import (
    grade_from_score,
    value_score_from_picks,
    detect_bye_week_collisions,
    bye_week_score,
    combined_grade,
    value_and_bye_strengths_weaknesses,
    bench_depth_notes,
)


def test_grade_from_score_thresholds():
    assert grade_from_score(95) == "A"
    assert grade_from_score(80) == "B"
    assert grade_from_score(70) == "C"
    assert grade_from_score(60) == "D"
    assert grade_from_score(59.9) == "F"


def test_value_score_from_picks_none_when_no_data():
    assert value_score_from_picks([{"value_percentage": None}]) is None
    assert value_score_from_picks([]) is None


def test_value_score_from_picks_rewards_steals_and_penalizes_reaches():
    steal = value_score_from_picks([{"value_percentage": 198.7}])
    fair = value_score_from_picks([{"value_percentage": 100.0}])
    reach = value_score_from_picks([{"value_percentage": 50.0}])
    assert steal > fair > reach
    assert fair == 75.0


def test_detect_bye_week_collisions_flags_shared_bye():
    players = [
        {"position": "QB", "bye_week": 11},
        {"position": "QB", "bye_week": 11},
    ]
    collisions = detect_bye_week_collisions(players, {"QB": 1})
    assert len(collisions) == 1
    assert collisions[0] == {"position": "QB", "week": 11, "active_count": 0, "required": 1}


def test_detect_bye_week_collisions_clean_when_byes_staggered():
    players = [
        {"position": "QB", "bye_week": 10},
        {"position": "QB", "bye_week": 11},
    ]
    assert detect_bye_week_collisions(players, {"QB": 1}) == []


def test_detect_bye_week_collisions_ignores_missing_bye_week():
    players = [{"position": "K", "bye_week": None}]
    assert detect_bye_week_collisions(players, {"K": 1}) == []


def test_bye_week_score_perfect_when_no_collisions():
    assert bye_week_score([]) == 100.0


def test_bye_week_score_penalizes_full_wipeout_more_than_partial():
    wipeout = bye_week_score([{"position": "QB", "week": 11, "active_count": 0, "required": 1}])
    partial = bye_week_score([{"position": "RB", "week": 11, "active_count": 1, "required": 2}])
    assert wipeout < 100.0
    assert partial < 100.0
    assert wipeout < partial


def test_combined_grade_drops_missing_components_instead_of_penalizing():
    composition_only = combined_grade(composition_score=90.0)
    assert composition_only["overall_score"] == 90.0
    assert composition_only["grade"] == "A"
    assert composition_only["components"] == {"composition": 90.0}


def test_combined_grade_blends_all_three_components():
    result = combined_grade(composition_score=90.0, value_score=90.0, bye_weeks_score=100.0)
    assert result["components"] == {"composition": 90.0, "value": 90.0, "bye_weeks": 100.0}
    assert 90.0 <= result["overall_score"] <= 100.0


def test_strengths_weaknesses_flags_needs_attention_and_overstocked():
    breakdown = {
        "RB": {"players_drafted": 1, "recommended_minimum": 2, "needs_attention": True, "overstocked": False},
        "WR": {"players_drafted": 5, "recommended_minimum": 2, "needs_attention": False, "overstocked": True},
    }
    result = value_and_bye_strengths_weaknesses(breakdown)
    assert any("RB is below your league's required depth (1/2)" in w for w in result["weaknesses"])
    assert any("WR has extra depth" in s for s in result["strengths"])


def test_strengths_weaknesses_surfaces_steals_and_reaches():
    entries = [
        {"player_name": "Seahawks D/ST", "position": "DEF", "pick": 161, "value_percentage": 198.7},
        {"player_name": "Jadarian Price", "position": "RB", "pick": 56, "value_percentage": 76.0},
        {"player_name": "Fair Pick", "position": "WR", "pick": 40, "value_percentage": 100.0},
    ]
    result = value_and_bye_strengths_weaknesses({}, value_entries=entries)
    assert any("Seahawks D/ST" in s and "pick 161" in s for s in result["strengths"])
    assert any("Jadarian Price" in w and "pick 56" in w for w in result["weaknesses"])
    assert not any("Fair Pick" in s for s in result["strengths"] + result["weaknesses"])


def test_strengths_weaknesses_surfaces_bye_collisions():
    collisions = [
        {"position": "QB", "week": 11, "active_count": 0, "required": 1},
        {"position": "RB", "week": 9, "active_count": 1, "required": 2},
    ]
    result = value_and_bye_strengths_weaknesses({}, bye_collisions=collisions)
    assert any("zero active starters" in w and "QB" in w for w in result["weaknesses"])
    assert any("1 of 2 required RBs" in w for w in result["weaknesses"])


def test_strengths_weaknesses_empty_inputs_return_empty_lists():
    assert value_and_bye_strengths_weaknesses({}) == {"strengths": [], "weaknesses": []}


def test_bench_depth_notes_flags_studs_then_cliff_roster():
    # Henry + Etienne as real starters, Price/Mason/Charbonnet as thin
    # committee-tier depth -- the exact shape from the real bug report.
    players = [
        {"position": "RB", "projected_points": 20},
        {"position": "RB", "projected_points": 18},
        {"position": "RB", "projected_points": 6},
        {"position": "RB", "projected_points": 5},
        {"position": "RB", "projected_points": 4},
    ]
    notes = bench_depth_notes(players, {"RB": 2})
    assert len(notes) == 1
    assert "RB depth beyond your top 2 is thin" in notes[0]


def test_bench_depth_notes_does_not_flag_genuinely_deep_position():
    players = [
        {"position": "RB", "projected_points": 20},
        {"position": "RB", "projected_points": 18},
        {"position": "RB", "projected_points": 15},
        {"position": "RB", "projected_points": 13},
    ]
    assert bench_depth_notes(players, {"RB": 2}) == []


def test_bench_depth_notes_skips_position_with_no_bench():
    players = [
        {"position": "QB", "projected_points": 20},
        {"position": "QB", "projected_points": 18},
    ]
    assert bench_depth_notes(players, {"QB": 2}) == []
