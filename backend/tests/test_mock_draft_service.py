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
    # The search_ranks above are all somewhat worse than the pick they went
    # at (e.g. rank 95 taken at pick 90), so the value component pulls the
    # blended grade below the composition-only "A" this roster would have
    # gotten before value was folded into the grade -- draft_grade now
    # reflects composition + value, not composition alone.
    assert result["components"]["composition"] == 90.0
    assert "value" in result["components"]
    assert result["draft_grade"] == "B"
    assert result["position_breakdown"]["QB"]["players_drafted"] == 2
    assert result["position_breakdown"]["QB"]["needs_attention"] is False
    assert len(result["value_analysis"]) == len(roster)
    assert "B" in result["final_analysis"] or "grade" in result["final_analysis"].lower()


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


def _identical_composition_roster(search_ranks_by_slot):
    """Build a full, identically-shaped 14-player roster (2 QB, 3 RB, 3 WR,
    2 TE, 2 K, 2 DEF -- same composition_score every time) whose actual picks
    are fixed, varying only each pick's search_rank so composition is held
    constant and only the value signal differs.
    """
    slots = [
        ("QB", "AAA", 1, 1), ("QB", "BBB", 8, 90),
        ("RB", "CCC", 2, 13), ("RB", "DDD", 3, 25), ("RB", "EEE", 9, 100),
        ("WR", "FFF", 4, 37), ("WR", "GGG", 5, 49), ("WR", "HHH", 10, 115),
        ("TE", "III", 6, 61), ("TE", "JJJ", 11, 125),
        ("K", "KKK", 12, 133), ("K", "LLL", 13, 145),
        ("DEF", "MMM", 14, 157), ("DEF", "NNN", 15, 169),
    ]
    roster = []
    for i, (position, team, round_, pick) in enumerate(slots):
        roster.append(
            make_player(
                str(i), f"{position} {team}", position, team, round_, pick,
                search_rank=search_ranks_by_slot[i],
            )
        )
    return roster


def test_draft_full_of_steals_grades_higher_than_identical_composition_full_of_reaches():
    # Same composition (same positions/rounds/picks) in both rosters -- a
    # smaller search_rank than the actual pick number means the player was
    # better-ranked than where they went, i.e. good value; a larger
    # search_rank than the pick means a reach.
    picks = [1, 90, 13, 25, 100, 37, 49, 115, 61, 125, 133, 145, 157, 169]
    steal_ranks = [max(1, p // 2) for p in picks]
    reach_ranks = [p * 2 for p in picks]

    steals_result = grade_mock_draft(
        {"scoring_format": "PPR", "team_count": 12, "draft_position": 1, "total_rounds": 15},
        _identical_composition_roster(steal_ranks),
    )
    reaches_result = grade_mock_draft(
        {"scoring_format": "PPR", "team_count": 12, "draft_position": 1, "total_rounds": 15},
        _identical_composition_roster(reach_ranks),
    )

    assert steals_result["composition_score"] == reaches_result["composition_score"]
    assert steals_result["overall_score"] > reaches_result["overall_score"]
    assert steals_result["components"]["value"] > reaches_result["components"]["value"]


def test_shared_bye_week_at_a_starting_position_grades_lower_than_staggered_byes():
    def roster_with_qb_byes(bye_a, bye_b):
        roster = [
            make_player("1", "QB One", "QB", "AAA", 1, 1, search_rank=1),
            make_player("2", "QB Two", "QB", "BBB", 8, 90, search_rank=95),
            make_player("3", "RB One", "RB", "CCC", 2, 13, search_rank=14),
            make_player("4", "RB Two", "RB", "DDD", 3, 25, search_rank=30),
            make_player("5", "WR One", "WR", "FFF", 4, 37, search_rank=40),
            make_player("6", "WR Two", "WR", "GGG", 5, 49, search_rank=55),
            make_player("7", "TE One", "TE", "III", 6, 61, search_rank=65),
            make_player("8", "K One", "K", "KKK", 12, 133, search_rank=150),
            make_player("9", "DEF One", "DEF", "MMM", 14, 157, search_rank=170),
        ]
        roster[0]["bye_week"] = bye_a
        roster[1]["bye_week"] = bye_b
        return roster

    settings = {"scoring_format": "PPR", "team_count": 12, "draft_position": 1, "total_rounds": 15}
    collision_result = grade_mock_draft(settings, roster_with_qb_byes(11, 11))
    staggered_result = grade_mock_draft(settings, roster_with_qb_byes(10, 11))

    # Both rosters have identical composition and identical value inputs --
    # only the bye-week staggering differs.
    assert collision_result["composition_score"] == staggered_result["composition_score"]
    assert len(collision_result["bye_week_collisions"]) == 1
    assert collision_result["bye_week_collisions"][0]["position"] == "QB"
    assert len(staggered_result["bye_week_collisions"]) == 0
    assert collision_result["overall_score"] < staggered_result["overall_score"]
    assert "Week 11" in collision_result["final_analysis"]


def test_no_rank_adp_or_bye_data_still_grades_sanely_off_composition_alone():
    # Full, well-composed roster but with zero search_rank/adp/projected_points
    # and zero bye_week anywhere -- value and bye-weeks components should
    # both be dropped (None), not penalized, and the grade should reduce to
    # composition alone with no crash.
    roster = [
        make_player("1", "QB One", "QB", "AAA", 1, 1),
        make_player("2", "QB Two", "QB", "BBB", 8, 90),
        make_player("3", "RB One", "RB", "CCC", 2, 13),
        make_player("4", "RB Two", "RB", "DDD", 3, 25),
        make_player("5", "RB Three", "RB", "EEE", 9, 100),
        make_player("6", "WR One", "WR", "FFF", 4, 37),
        make_player("7", "WR Two", "WR", "GGG", 5, 49),
        make_player("8", "WR Three", "WR", "HHH", 10, 115),
        make_player("9", "TE One", "TE", "III", 6, 61),
        make_player("10", "TE Two", "TE", "JJJ", 11, 125),
        make_player("11", "K One", "K", "KKK", 12, 133),
        make_player("12", "K Two", "K", "LLL", 13, 145),
        make_player("13", "DEF One", "DEF", "MMM", 14, 157),
        make_player("14", "DEF Two", "DEF", "NNN", 15, 169),
    ]

    result = grade_mock_draft(
        {"scoring_format": "PPR", "team_count": 12, "draft_position": 1, "total_rounds": 15},
        roster,
    )

    assert result["composition_score"] == 90.0
    assert result["bye_week_collisions"] == []
    assert result["components"] == {"composition": 90.0}
    assert result["overall_score"] == 90.0
    assert result["draft_grade"] == "A"
