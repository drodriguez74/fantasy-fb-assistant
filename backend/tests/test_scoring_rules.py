"""Tests for the canonical, cross-platform scoring-rules extraction and
recalculation logic (app.services.scoring_rules), and its wiring into
sleeper_service, espn_service_enhanced, and draft_assistant_service.

Real-league grounding: REAL_SLEEPER_SCORING_SETTINGS below is the actual
`scoring_settings` dict returned live by Sleeper's public API for league
289646328504385536 (curl https://api.sleeper.app/v1/league/289646328504385536),
captured while writing this feature. It confirms `pass_cmp` and `pass_att`
are real, independent keys Sleeper exposes (both 0.0 for this particular
league -- i.e. standard, not a completion-scoring league) alongside `rec`,
`pass_int`, `rush_yd`, `rec_yd`, etc. No public completion-rewarding Sleeper
league was found to test live non-zero pass_cmp/pass_att values against, so
test_calculate_points_from_stats_completion_scoring below constructs that
case explicitly and exercises the real math against it.
"""
import asyncio

from app.services.scoring_rules import (
    calculate_points_from_stats,
    default_scoring_rules,
    describe_scoring_rules,
    scoring_rules_from_espn,
    scoring_rules_from_sleeper,
)
from app.services.sleeper_service import SleeperService
from app.services.draft_assistant_service import DraftAssistantService


# Captured live from api.sleeper.app/v1/league/289646328504385536 -- see
# module docstring.
REAL_SLEEPER_SCORING_SETTINGS = {
    'sack': 1.0, 'qb_hit': 0.0, 'fgm_40_49': 4.0, 'bonus_rec_yd_100': 0.0,
    'bonus_rush_yd_100': 0.0, 'pass_int': -2.0, 'pts_allow_0': 10.0,
    'bonus_pass_yd_400': 0.0, 'pass_2pt': 2.0, 'blk_kick_ret_yd': 0.0,
    'st_td': 6.0, 'sack_yd': 0.0, 'pr_td': 0.0, 'rec_td': 6.0,
    'tkl_ast': 0.0, 'fgm_30_39': 3.0, 'kr_td': 0.0, 'xpmiss': -1.0,
    'rush_td': 6.0, 'fg_ret_yd': 0.0, 'idp_tkl': 0.0, 'fgm': 0.0,
    'idp_blk': 0.0, 'rec_2pt': 2.0, 'int_ret_yd': 0.0, 'idp_tkl_solo': 0.0,
    'pass_att': 0.0, 'st_fum_rec': 1.0, 'ff': 1.0, 'idp_int': 0.0,
    'fgmiss_30_39': -1.0, 'rec': 1.0, 'idp_safe': 0.0,
    'pts_allow_14_20': 1.0, 'def_2pt': 0.0, 'fgm_0_19': 3.0, 'int': 2.0,
    'def_st_fum_rec': 0.0, 'fum_lost': -2.0, 'pts_allow_1_6': 7.0,
    'kr_yd': 0.0, 'fgmiss_20_29': -1.0, 'rush_att': 0.0,
    'st_tkl_solo': 0.0, 'idp_sack': 0.0, 'fgm_20_29': 3.0,
    'pts_allow_21_27': 0.0, 'bonus_pass_yd_300': 0.0, 'xpm': 1.0,
    'pass_sack': 0.0, 'fgmiss_0_19': -1.0, 'pass_cmp': 0.0,
    'tkl_loss': 0.0, 'rush_2pt': 2.0, 'def_pass_def': 0.0, 'fum_rec': 2.0,
    'idp_pass_def': 0.0, 'bonus_rec_yd_200': 0.0, 'def_st_td': 0.0,
    'tkl': 0.0, 'fgm_50p': 5.0, 'def_td': 6.0, 'idp_fum_rec': 0.0,
    'bonus_rush_yd_200': 0.0, 'safe': 2.0, 'pass_yd': 0.03999999910593033,
    'blk_kick': 2.0, 'pass_td': 6.0, 'tkl_solo': 0.0,
    'rush_yd': 0.10000000149011612, 'pr_yd': 0.0, 'fum': 0.0,
    'pts_allow_28_34': -1.0, 'pts_allow_35p': -4.0,
    'rec_yd': 0.10000000149011612, 'fum_ret_yd': 0.0, 'def_st_ff': 0.0,
    'pts_allow_7_13': 4.0, 'idp_ff': 0.0, 'st_ff': 1.0,
    'idp_tkl_ast': 0.0,
}


class TestScoringRulesFromSleeper:
    def test_extracts_real_league_values(self):
        """Real Sleeper league 289646328504385536 is standard for
        completions/attempts (both 0.0) but has real non-default values
        for pass_int, pass_td, rush_yd, rec_yd, rec, fum_lost -- assert
        every one of those is read correctly, not just `rec`."""
        rules = scoring_rules_from_sleeper(REAL_SLEEPER_SCORING_SETTINGS)

        assert rules["source"] == "sleeper"
        assert rules["passing"]["completion"] == 0.0
        assert rules["passing"]["attempt"] == 0.0
        assert rules["passing"]["interception"] == -2.0
        assert rules["passing"]["td"] == 6.0
        assert abs(rules["passing"]["yard"] - 0.04) < 1e-6
        assert rules["rushing"]["td"] == 6.0
        assert abs(rules["rushing"]["yard"] - 0.1) < 1e-6
        assert rules["receiving"]["reception"] == 1.0  # full PPR
        assert rules["receiving"]["td"] == 6.0
        assert abs(rules["receiving"]["yard"] - 0.1) < 1e-6
        assert rules["fumbles"]["lost"] == -2.0

    def test_missing_pass_inc_key_defaults_to_baseline(self):
        """This real league's response has no `pass_inc` key at all
        (leagues that don't override it omit the key rather than sending
        an explicit 0.0) -- confirm that's handled as the honest Standard
        default (0.0), not a crash or a fabricated non-zero value."""
        assert "pass_inc" not in REAL_SLEEPER_SCORING_SETTINGS
        rules = scoring_rules_from_sleeper(REAL_SLEEPER_SCORING_SETTINGS)
        assert rules["passing"]["incompletion"] == 0.0

    def test_parse_league_settings_attaches_scoring_rules(self):
        """sleeper_service.parse_league_settings (the pre-existing
        extraction entry point) now surfaces the full scoring_rules dict
        alongside the pre-existing points_per_reception, not just PPR."""
        service = SleeperService()
        league_info = {
            "roster_positions": ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF", "BN", "BN"],
            "scoring_settings": REAL_SLEEPER_SCORING_SETTINGS,
        }
        parsed = service.parse_league_settings(league_info)
        assert parsed["points_per_reception"] == 1.0
        assert "scoring_rules" in parsed
        assert parsed["scoring_rules"]["source"] == "sleeper"
        assert parsed["scoring_rules"]["passing"]["interception"] == -2.0


class TestScoringRulesFromEspn:
    def test_extracts_completion_scoring_league(self):
        """Constructed ESPN scoring_format list (statIds grounded in the
        installed espn_api 0.46.0 package's own
        SETTINGS_SCORING_FORMAT_MAP -- see scoring_rules.py's comment)
        representing a real completion-accuracy league: +0.5 per
        completion, -0.5 per incompletion."""
        scoring_format = [
            {"id": 1, "abbr": "PC", "points": 0.5},     # Each Pass Completed
            {"id": 2, "abbr": "INC", "points": -0.5},   # Each Incomplete Pass
            {"id": 0, "abbr": "PA", "points": 0.0},     # Each Pass Attempted
            {"id": 3, "abbr": "PY", "points": 0.04},    # Passing Yards
            {"id": 4, "abbr": "PTD", "points": 4.0},    # TD Pass
            {"id": 20, "abbr": "INTT", "points": -2.0}, # Interceptions Thrown
            {"id": 53, "abbr": "REC", "points": 1.0},   # Each reception
            {"id": 72, "abbr": "FUML", "points": -2.0}, # Total Fumbles Lost
        ]
        rules = scoring_rules_from_espn(scoring_format)

        assert rules["source"] == "espn"
        assert rules["passing"]["completion"] == 0.5
        assert rules["passing"]["incompletion"] == -0.5
        assert rules["passing"]["attempt"] == 0.0
        assert rules["passing"]["td"] == 4.0
        assert rules["passing"]["interception"] == -2.0
        assert rules["receiving"]["reception"] == 1.0
        assert rules["fumbles"]["lost"] == -2.0

    def test_unmapped_stat_ids_are_ignored(self):
        """statIds this app's canonical shape doesn't track (e.g. kicking
        id 83, defense id 99) shouldn't raise or get silently absorbed
        into an unrelated category."""
        scoring_format = [
            {"id": 83, "abbr": "FG", "points": 3.0},
            {"id": 99, "abbr": "SK", "points": 1.0},
        ]
        rules = scoring_rules_from_espn(scoring_format)
        assert rules == default_scoring_rules(source="espn")

    def test_empty_scoring_format_returns_standard_default(self):
        rules = scoring_rules_from_espn([])
        assert rules == default_scoring_rules(source="espn")


class TestCalculatePointsFromStats:
    def test_completion_scoring_before_after_example(self):
        """The brief's motivating example, made concrete: two constructed
        QB season projections --
          - "Efficient Ethan": 380 completions / 570 attempts (66.7%),
            4200 pass yards, 28 pass TD, 8 INT
          - "Gunslinger Gary": 380 completions / 620 attempts (61.3%,
            240 incompletions -- 50 more than Ethan), same yards/TD/INT
        Under Standard scoring (0 pts/completion, 0 pts/incompletion) they
        are IDENTICAL. Under a real completion-accuracy league (+0.5 per
        completion, -0.5 per incompletion), Ethan is worth strictly more
        than Gary for the exact same yards/TDs/INTs -- because he did it
        more efficiently. That's the "before/after" this feature exists
        to make correct.
        """
        ethan = {
            "completions": 380, "incompletions": 190,  # 570 attempts, 66.7%
            "pass_yards": 4200, "pass_tds": 28, "interceptions": 8,
        }
        gary = {
            "completions": 380, "incompletions": 240,  # 620 attempts, 61.3%
            "pass_yards": 4200, "pass_tds": 28, "interceptions": 8,
        }

        standard_rules = default_scoring_rules(source="fallback_standard")
        completion_league_rules = default_scoring_rules(source="sleeper")
        completion_league_rules["passing"]["completion"] = 0.5
        completion_league_rules["passing"]["incompletion"] = -0.5

        # BEFORE (standard scoring): identical value regardless of accuracy.
        ethan_standard = calculate_points_from_stats(ethan, standard_rules)
        gary_standard = calculate_points_from_stats(gary, standard_rules)
        assert ethan_standard == gary_standard

        # AFTER (completion-accuracy league): Ethan is worth more.
        ethan_accuracy = calculate_points_from_stats(ethan, completion_league_rules)
        gary_accuracy = calculate_points_from_stats(gary, completion_league_rules)
        assert ethan_accuracy > gary_accuracy

        # Exact arithmetic, spelled out:
        # base = 4200*0.04 + 28*4 + 8*(-2) = 168 + 112 - 16 = 264
        base = 4200 * 0.04 + 28 * 4 + 8 * -2
        assert abs(ethan_standard - base) < 1e-6
        assert abs(gary_standard - base) < 1e-6
        # Ethan: base + 380*0.5 + 190*-0.5 = 264 + 190 - 95 = 359
        assert abs(ethan_accuracy - (base + 380 * 0.5 + 190 * -0.5)) < 1e-6
        # Gary: base + 380*0.5 + 240*-0.5 = 264 + 190 - 120 = 334
        assert abs(gary_accuracy - (base + 380 * 0.5 + 240 * -0.5)) < 1e-6
        # Ethan beats Gary by exactly the extra 50 incompletions * 0.5
        assert abs((ethan_accuracy - gary_accuracy) - 25.0) < 1e-6

    def test_empty_stats_and_none_rules_are_safe(self):
        assert calculate_points_from_stats({}, None) == 0.0
        assert calculate_points_from_stats({}, default_scoring_rules()) == 0.0


class TestDescribeScoringRules:
    def test_standard_league_has_no_notable_rules(self):
        assert describe_scoring_rules(default_scoring_rules()) == ""

    def test_completion_league_is_described(self):
        rules = default_scoring_rules(source="sleeper")
        rules["passing"]["completion"] = 0.5
        rules["passing"]["incompletion"] = -0.5
        desc = describe_scoring_rules(rules)
        assert "completed pass" in desc
        assert "incomplete pass" in desc
        assert "+0.5" in desc
        assert "-0.5" in desc

    def test_none_rules_returns_empty_string(self):
        assert describe_scoring_rules(None) == ""


class TestCalculatePlayerValuesRecalculation:
    """Integration coverage for draft_assistant_service._calculate_player_values'
    scoring-rules recalculation path -- confirms it fires for a
    non-ESPN record with a raw stat breakdown, and is explicitly skipped
    for an ESPN-tagged record so ESPN's own already-correct
    projected_points is never double counted."""

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_recalculates_for_non_espn_record_with_raw_stats(self):
        service = DraftAssistantService()
        completion_league_rules = default_scoring_rules(source="sleeper")
        completion_league_rules["passing"]["completion"] = 0.5
        completion_league_rules["passing"]["incompletion"] = -0.5

        player = {
            "player_id": "efficient_qb",
            "full_name": "Efficient Ethan",
            "position": "QB",
            "projected_points": 0,  # Sleeper's real available_players carries no score at all
            "ownership": 10,
            "projected_stat_breakdown": {
                "completions": 380, "incompletions": 190,
                "pass_yards": 4200, "pass_tds": 28, "interceptions": 8,
            },
        }
        draft_analysis = {
            "league_settings": {
                "points_per_reception": 0.0,
                "scoring_rules": completion_league_rules,
                "source": "sleeper",
            }
        }

        result = self._run(service._calculate_player_values([player], draft_analysis))
        # value_score = effective_points * (100 - ownership) / 100
        # effective_points should be the full recalculated 359.0 (see
        # test_completion_scoring_before_after_example), not the raw 0.
        expected_effective = 4200 * 0.04 + 28 * 4 + 8 * -2 + 380 * 0.5 + 190 * -0.5
        assert expected_effective == 359.0
        assert result["value_picks"], "expected the recalculated value to clear the value-pick threshold"
        assert abs(result["value_picks"][0]["value_score"] - expected_effective * 0.9) < 1e-6

    def test_does_not_recalculate_espn_tagged_record(self):
        """An ESPN-tagged player record with (hypothetically) a raw stat
        breakdown attached must NOT be recalculated -- ESPN's own
        projected_points already reflects the league's real scoring."""
        service = DraftAssistantService()
        completion_league_rules = default_scoring_rules(source="espn")
        completion_league_rules["passing"]["completion"] = 0.5
        completion_league_rules["passing"]["incompletion"] = -0.5

        player = {
            "player_id": "espn_qb",
            "full_name": "ESPN QB",
            "position": "QB",
            "projected_points": 300.0,  # ESPN's own already-correct season total
            "ownership": 10,
            "platform": "espn",
            # Even if a raw breakdown were present, it must be ignored for ESPN.
            "projected_stat_breakdown": {
                "completions": 380, "incompletions": 190,
                "pass_yards": 4200, "pass_tds": 28, "interceptions": 8,
            },
        }
        draft_analysis = {
            "league_settings": {
                "points_per_reception": 0.0,
                "scoring_rules": completion_league_rules,
                "source": "espn",
            }
        }

        result = self._run(service._calculate_player_values([player], draft_analysis))
        # Must use the untouched projected_points (300.0), not the recalculated figure.
        assert abs(result["value_picks"][0]["value_score"] - 300.0 * 0.9) < 1e-6
