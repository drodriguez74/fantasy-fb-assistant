"""
Tests for LeagueManagementService's ESPN comprehensive-analysis branch.

get_comprehensive_league_analysis previously returned an honest "not
implemented for this platform yet" error for every ESPN league (see
test_league_management_service.py's docstring for the Yahoo-only history).
This mirrors that file's patterns against the new ESPN helpers
(_analyze_espn_roster, _analyze_espn_matchup, _get_espn_league_standings,
_get_espn_waiver_recs, _get_espn_trade_recommendations), monkeypatching
espn_service_enhanced instead of yahoo_service.
"""

from unittest.mock import AsyncMock

import pytest

from app.models.user_league import UserLeague, PlatformType
from app.services import league_management_service as lms_module
from app.services.league_management_service import LeagueManagementService


def make_espn_league(**overrides):
    defaults = dict(
        user_id=1,
        platform=PlatformType.ESPN,
        league_id="123456",
        team_id="1",
        league_name="Test ESPN League",
        season=2024,
        scoring_format="PPR",
        league_size=12,
        espn_swid="{fake-swid}",
        espn_s2="fake-espn-s2",
    )
    defaults.update(overrides)
    return UserLeague(**defaults)


def roster_with_real_rb_shortfall():
    """QB1/RB1/WR2/TE1/K1/DEF1 -- every position meets or exceeds the
    standard-lineup fallback requirement (QB1/RB2/WR2/TE1/K1/DEF1) except
    RB, which is short by one.
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
    yield


class TestEspnComprehensiveAnalysisRouting:
    """get_comprehensive_league_analysis must route ESPN leagues to the
    real ESPN branch, not the honest-error fallback.
    """

    @pytest.mark.asyncio
    async def test_espn_league_no_longer_returns_not_implemented_error(
        self, test_db_session, monkeypatch
    ):
        league = make_espn_league()
        test_db_session.add(league)
        test_db_session.commit()

        roster_players = roster_with_real_rb_shortfall()

        async def fake_get_team_roster(**kwargs):
            return {"players": roster_players, "team_id": 1, "team_name": "My Team", "owner": "Me"}

        async def fake_get_scoring_and_roster_settings(**kwargs):
            return {"error": "not available"}

        async def fake_get_matchups(**kwargs):
            return [{
                "home_team": {"team_id": 1, "team_name": "My Team", "score": 100.0},
                "away_team": {"team_id": 2, "team_name": "Rival", "score": 90.0},
            }]

        async def fake_get_standings(**kwargs):
            return [
                {"team_id": 1, "team_name": "My Team", "wins": 5, "losses": 2, "points_for": 700,
                 "points_against": 600, "win_percentage": 0.71, "points_per_game": 100, "rank": 1},
                {"team_id": 2, "team_name": "Rival", "wins": 3, "losses": 4, "points_for": 600,
                 "points_against": 650, "win_percentage": 0.43, "points_per_game": 85, "rank": 2},
            ]

        async def fake_get_league_teams(**kwargs):
            return [{"team_id": 1, "team_name": "My Team"}, {"team_id": 2, "team_name": "Rival"}]

        async def fake_generate_with_fallback(prompt, prefer_fast_model=True):
            return '{"grade": "B", "summary": "ok", "strengths": [], "concerns": [], "recommendations": []}'

        monkeypatch.setattr(lms_module.espn_service_enhanced, "get_team_roster", fake_get_team_roster)
        monkeypatch.setattr(
            lms_module.espn_service_enhanced,
            "get_scoring_and_roster_settings",
            fake_get_scoring_and_roster_settings,
        )
        monkeypatch.setattr(lms_module.espn_service_enhanced, "get_matchups", fake_get_matchups)
        monkeypatch.setattr(lms_module.espn_service_enhanced, "get_standings", fake_get_standings)
        monkeypatch.setattr(lms_module.espn_service_enhanced, "get_league_teams", fake_get_league_teams)
        monkeypatch.setattr(lms_module.ai_service, "_generate_with_fallback", fake_generate_with_fallback)

        service = LeagueManagementService(test_db_session)
        result = await service.get_comprehensive_league_analysis(user_id=1, league_id=league.id)

        assert "error" not in result
        assert "not implemented" not in str(result).lower()
        assert result["roster_analysis"]["overall_grade"]
        assert result["current_matchup"]["user_team"]["team_name"] == "My Team"
        assert result["standings"]["user_team_rank"] == 1
        assert "recommendations" in result["waiver_recommendations"]
        assert "suggestions" in result["trade_recommendations"]


class TestEspnRosterGrading:
    """Mirrors TestDeterministicOverallGrade for the ESPN roster path."""

    @pytest.mark.asyncio
    async def test_overall_grade_reflects_real_composition(self, test_db_session, monkeypatch):
        league = make_espn_league()
        roster_players = roster_with_real_rb_shortfall()

        async def fake_get_team_roster(**kwargs):
            return {"players": roster_players}

        async def fake_get_scoring_and_roster_settings(**kwargs):
            return {"error": "not available"}

        async def fake_generate_with_fallback(prompt, prefer_fast_model=True):
            return '{"grade": "A", "summary": "great", "strengths": [], "concerns": [], "recommendations": []}'

        monkeypatch.setattr(lms_module.espn_service_enhanced, "get_team_roster", fake_get_team_roster)
        monkeypatch.setattr(
            lms_module.espn_service_enhanced,
            "get_scoring_and_roster_settings",
            fake_get_scoring_and_roster_settings,
        )
        monkeypatch.setattr(lms_module.ai_service, "_generate_with_fallback", fake_generate_with_fallback)

        service = LeagueManagementService(test_db_session)
        result = await service._analyze_espn_roster(league)

        assert "error" not in result
        assert result["overall_grade"] != "A"
        assert result["position_breakdown"]["RB"]["needs_attention"] is True
        assert any("RB" in w for w in result["weaknesses"])

    @pytest.mark.asyncio
    async def test_missing_team_id_returns_honest_error(self, test_db_session):
        league = make_espn_league(team_id=None)
        service = LeagueManagementService(test_db_session)
        result = await service._analyze_espn_roster(league)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_roster_fetch_error_becomes_reconnect_message(self, test_db_session, monkeypatch):
        league = make_espn_league()

        async def fake_get_team_roster(**kwargs):
            return {"error": "Failed to get team roster: bad credentials"}

        monkeypatch.setattr(lms_module.espn_service_enhanced, "get_team_roster", fake_get_team_roster)

        service = LeagueManagementService(test_db_session)
        result = await service._analyze_espn_roster(league)

        assert "error" in result
        assert "reconnect" in result["error"].lower()


class TestEspnRealStartersUsedWhenAvailable:
    """Mirrors TestYahooLeagueSettingsUsedWhenAvailable for ESPN."""

    @pytest.mark.asyncio
    async def test_real_espn_starters_used_when_available(self, test_db_session, monkeypatch):
        league = make_espn_league()
        roster_players = roster_with_real_rb_shortfall()

        async def fake_get_team_roster(**kwargs):
            return {"players": roster_players}

        async def fake_get_scoring_and_roster_settings(**kwargs):
            return {
                "starters": {"QB": 1, "RB": 1, "WR": 2, "TE": 1, "K": 1, "DEF": 1},
                "bench": 6,
                "roster_size": 13,
                "points_per_reception": 1.0,
                "source": "espn",
            }

        async def fake_generate_with_fallback(prompt, prefer_fast_model=True):
            return '{"grade": "B", "summary": "ok", "strengths": [], "concerns": [], "recommendations": []}'

        monkeypatch.setattr(lms_module.espn_service_enhanced, "get_team_roster", fake_get_team_roster)
        monkeypatch.setattr(
            lms_module.espn_service_enhanced,
            "get_scoring_and_roster_settings",
            fake_get_scoring_and_roster_settings,
        )
        monkeypatch.setattr(lms_module.ai_service, "_generate_with_fallback", fake_generate_with_fallback)

        service = LeagueManagementService(test_db_session)
        result = await service._analyze_espn_roster(league)

        assert "error" not in result
        assert result["position_breakdown"]["RB"]["needs_attention"] is False
        assert result["position_breakdown"]["RB"]["recommended_minimum"] == 1


class TestEspnMatchupTeamShapeHandling:
    """ESPN's get_matchups returns {"home_team", "away_team"} instead of
    Yahoo's flat "teams" list -- the user's side can be on either.
    """

    @pytest.mark.asyncio
    async def test_user_team_found_when_away(self, test_db_session, monkeypatch):
        league = make_espn_league(team_id="2")

        async def fake_get_matchups(**kwargs):
            return [{
                "home_team": {"team_id": 1, "team_name": "Rival", "score": 90.0},
                "away_team": {"team_id": 2, "team_name": "My Team", "score": 100.0},
            }]

        async def fake_generate_with_fallback(prompt, prefer_fast_model=True):
            return "some analysis"

        monkeypatch.setattr(lms_module.espn_service_enhanced, "get_matchups", fake_get_matchups)
        monkeypatch.setattr(lms_module.ai_service, "_generate_with_fallback", fake_generate_with_fallback)

        service = LeagueManagementService(test_db_session)
        result = await service._analyze_espn_matchup(league)

        assert "error" not in result
        assert result["user_team"]["team_name"] == "My Team"
        assert result["opponent_team"]["team_name"] == "Rival"
