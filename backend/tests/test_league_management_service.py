"""
Tests for LeagueManagementService's Yahoo roster-grading path.

Covers two real bugs found by comparing our app's roster grade against an
external expert analysis of the same real roster:

  1. League settings (league_size, scoring_format) were captured into
     analysis["league_info"] but never threaded into the AI grading prompts
     -- _analyze_position_group's prompt now includes real league context.
  2. The overall roster grade was pure LLM opinion (an average of
     AI-assigned per-position letter grades) with no deterministic,
     data-driven scoring anywhere in this file -- _analyze_yahoo_roster now
     uses roster_grading.grade_roster (the same real, deterministic
     composition-vs-requirements grader used elsewhere in the codebase) as
     the source of truth for the overall grade, independent of whatever the
     AI says.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.models.user_league import UserLeague, PlatformType
from app.services import league_management_service as lms_module
from app.services.league_management_service import LeagueManagementService


def make_yahoo_league(**overrides):
    defaults = dict(
        user_id=1,
        platform=PlatformType.YAHOO,
        league_id="1",
        league_key=None,  # skip get_league_settings by default -> fallback lineup
        team_id="team_1",
        league_name="Test League",
        season="2024",
        scoring_format="PPR",
        league_size=12,
        yahoo_access_token="fresh-token",
        yahoo_token_expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    defaults.update(overrides)
    return UserLeague(**defaults)


def roster_with_real_rb_shortfall():
    """QB1/RB1/WR2/TE1/K1/DEF1 -- every position meets or exceeds the
    standard-lineup fallback requirement (QB1/RB2/WR2/TE1/K1/DEF1) except
    RB, which is short by one. A real, deterministic grader should reflect
    that shortfall regardless of what an AI mock says about any position.
    """
    return [
        {"name": "QB One", "position": "QB", "projected_points": 20},
        {"name": "RB One", "position": "RB", "projected_points": 15},
        {"name": "WR One", "position": "WR", "projected_points": 14},
        {"name": "WR Two", "position": "WR", "projected_points": 12},
        {"name": "TE One", "position": "TE", "projected_points": 9},
        {"name": "K One", "position": "K", "projected_points": 8},
        {"name": "DEF One", "position": "DEF", "projected_points": 7},
    ]


@pytest.fixture(autouse=True)
def _no_db_player_matches(monkeypatch, test_db_session):
    """_analyze_position_group and _check_roster_injuries both query the
    real Player table by name for enhanced data; with an empty test DB
    these naturally return None/no matches, which is fine for these tests.
    """
    yield


class TestDeterministicOverallGrade:
    """Bug 2: overall_grade must come from real roster composition, not
    from averaging whatever letter grade the (mocked) AI assigned to each
    position group.
    """

    @pytest.mark.asyncio
    async def test_overall_grade_reflects_real_composition_not_ai_opinion(
        self, test_db_session, monkeypatch
    ):
        league = make_yahoo_league()

        roster_players = roster_with_real_rb_shortfall()

        async def fake_get_team_roster(access_token, team_id):
            return {"players": roster_players}

        # The AI mock claims every position group is an "A" -- if the old
        # bug (pure average of AI-assigned letter grades) were still
        # present, overall_grade would come back "A" too. The real,
        # deterministic grader must not be fooled by this.
        async def fake_generate_with_fallback(prompt, prefer_fast_model=True):
            return '{"grade": "A", "summary": "great", "strengths": [], "concerns": [], "recommendations": []}'

        monkeypatch.setattr(
            lms_module.yahoo_service, "get_team_roster", fake_get_team_roster
        )
        monkeypatch.setattr(
            lms_module.ai_service, "_generate_with_fallback", fake_generate_with_fallback
        )

        service = LeagueManagementService(test_db_session)
        result = await service._analyze_yahoo_roster(league)

        assert "error" not in result
        # RB is short (1 rostered vs. 2 required by the standard fallback
        # lineup) -- the real grader must not report a perfect "A" despite
        # every mocked AI position analysis claiming "A".
        assert result["overall_grade"] != "A"
        assert "composition_score" in result
        assert result["position_breakdown"]["RB"]["needs_attention"] is True

        # Weakness classification should be driven by the real breakdown,
        # not the (all-"A") AI grades -- RB should show up as a weakness.
        assert any("RB" in w for w in result["weaknesses"])
        # And no position should be misclassified as a strength purely
        # because the AI said "A" everywhere.
        for s in result["strengths"]:
            assert not s.startswith("RB:")

    @pytest.mark.asyncio
    async def test_calculate_overall_roster_grade_removed(self):
        """The old pure-LLM-average grade calculator is dead code once the
        real deterministic grader is wired in -- it should be removed
        rather than left unused.
        """
        assert not hasattr(LeagueManagementService, "_calculate_overall_roster_grade")


class TestLeagueContextReachesPrompt:
    """Bug 1: real league_size/scoring_format must actually reach the AI
    prompt text, not just sit unused in analysis["league_info"].
    """

    @pytest.mark.asyncio
    async def test_league_size_and_scoring_format_in_prompt(self, test_db_session, monkeypatch):
        captured_prompts = []

        async def fake_generate_with_fallback(prompt, prefer_fast_model=True):
            captured_prompts.append(prompt)
            return '{"grade": "B", "summary": "ok", "strengths": [], "concerns": [], "recommendations": []}'

        monkeypatch.setattr(
            lms_module.ai_service, "_generate_with_fallback", fake_generate_with_fallback
        )

        service = LeagueManagementService(test_db_session)
        players = [{"name": "QB One", "position": "QB", "projected_points": 20}]
        await service._analyze_position_group(
            "QB", players, league_size=12, scoring_format="PPR"
        )

        assert len(captured_prompts) == 1
        prompt = captured_prompts[0]
        assert "12" in prompt
        assert "PPR" in prompt

    @pytest.mark.asyncio
    async def test_analyze_yahoo_roster_threads_league_context_into_prompts(
        self, test_db_session, monkeypatch
    ):
        league = make_yahoo_league(league_size=10, scoring_format="Half-PPR")
        roster_players = roster_with_real_rb_shortfall()

        async def fake_get_team_roster(access_token, team_id):
            return {"players": roster_players}

        captured_prompts = []

        async def fake_generate_with_fallback(prompt, prefer_fast_model=True):
            captured_prompts.append(prompt)
            return '{"grade": "B", "summary": "ok", "strengths": [], "concerns": [], "recommendations": []}'

        monkeypatch.setattr(
            lms_module.yahoo_service, "get_team_roster", fake_get_team_roster
        )
        monkeypatch.setattr(
            lms_module.ai_service, "_generate_with_fallback", fake_generate_with_fallback
        )

        service = LeagueManagementService(test_db_session)
        result = await service._analyze_yahoo_roster(league)

        assert "error" not in result
        assert captured_prompts, "expected at least one AI prompt to be generated"
        for prompt in captured_prompts:
            assert "10" in prompt
            assert "Half-PPR" in prompt


class TestYahooLeagueSettingsUsedWhenAvailable:
    """When Yahoo does expose real per-league starter settings
    (get_league_settings), they should be used instead of the generic
    standard-lineup fallback.
    """

    @pytest.mark.asyncio
    async def test_real_yahoo_starters_used_when_available(self, test_db_session, monkeypatch):
        # A league that only requires 1 RB starter (vs. the standard
        # fallback of 2) -- with real settings honored, the same
        # RB-shortfall roster used above should no longer show RB as
        # needing attention.
        league = make_yahoo_league(league_key="423.l.999")
        roster_players = roster_with_real_rb_shortfall()

        async def fake_get_team_roster(access_token, team_id):
            return {"players": roster_players}

        async def fake_get_league_settings(access_token, league_key):
            return {
                "starters": {"QB": 1, "RB": 1, "WR": 2, "TE": 1, "K": 1, "DEF": 1},
                "bench": 6,
                "roster_size": 13,
                "points_per_reception": 1.0,
                "source": "yahoo",
            }

        async def fake_generate_with_fallback(prompt, prefer_fast_model=True):
            return '{"grade": "B", "summary": "ok", "strengths": [], "concerns": [], "recommendations": []}'

        monkeypatch.setattr(
            lms_module.yahoo_service, "get_team_roster", fake_get_team_roster
        )
        monkeypatch.setattr(
            lms_module.yahoo_service, "get_league_settings", fake_get_league_settings
        )
        monkeypatch.setattr(
            lms_module.ai_service, "_generate_with_fallback", fake_generate_with_fallback
        )

        service = LeagueManagementService(test_db_session)
        result = await service._analyze_yahoo_roster(league)

        assert "error" not in result
        assert result["position_breakdown"]["RB"]["needs_attention"] is False
        assert result["position_breakdown"]["RB"]["recommended_minimum"] == 1


class TestWaiverPriorityMapping:
    """_WAIVER_PRIORITY_SCORES must cover all 5 real Priority tiers the live
    waiver engine emits (urgent/high/medium/low/watch -- see
    WaiverWireService._priority_from_rank), not just 3. It used to omit
    "urgent" and "watch", so both silently fell through to the dict's
    `.get(..., 1)` default -- meaning the single best candidate in the
    entire trending pool (urgent, top 10%) rendered the exact same
    "Priority: 1/3" on the League Detail waiver card as the single worst
    (watch, bottom 15%), while "high" candidates ranked below it showed
    3/3. Confirmed live: half the visible list showed 1/3, half showed
    3/3, with the ordering backwards relative to real rank.
    """

    def test_urgent_and_watch_are_not_conflated(self):
        service = LeagueManagementService.__new__(LeagueManagementService)
        candidates = [
            {"player_name": "Urgent Guy", "position": "RB", "priority": "urgent"},
            {"player_name": "High Guy", "position": "RB", "priority": "high"},
            {"player_name": "Medium Guy", "position": "RB", "priority": "medium"},
            {"player_name": "Low Guy", "position": "RB", "priority": "low"},
            {"player_name": "Watch Guy", "position": "RB", "priority": "watch"},
        ]

        adapted = service._live_waiver_candidates_to_league_view(candidates)
        priorities = {a["player"]["name"]: a["priority"] for a in adapted}

        # urgent must rank at least as high as high (both real buy signals),
        # never collapse to the same tier as low/watch.
        assert priorities["Urgent Guy"] >= priorities["High Guy"]
        assert priorities["Urgent Guy"] > priorities["Low Guy"]
        assert priorities["Urgent Guy"] > priorities["Watch Guy"]
        # watch (weakest real signal) must not outrank medium/high.
        assert priorities["Watch Guy"] <= priorities["Medium Guy"]
