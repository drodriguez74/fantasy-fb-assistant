"""
Unit tests for WaiverWireService covering two real gaps found by review:

  1. `get_live_trending_recommendations` (the live, Sleeper-trending-backed
     endpoint that actually powers GET /waiver-wire/recommendations) had
     zero personalization: no roster-need awareness, no bye-week check, and
     it only ever echoed the league's real scoring format back rather than
     using it. This adds real roster-need weighting (via
     DraftAssistantService._effective_position_requirements, the same
     FLEX-aware helper roster_grading.py/post_draft_analysis_service.py
     already use) and real bye-week flagging.

  2. `_evaluate_player_for_waiver` (backing `generate_weekly_recommendations`
     / `get_personalized_waiver_targets`) hardcoded `recent_performances =
     []`, so `_calculate_performance_score`, `_calculate_opportunity_score`,
     and `_calculate_trend_score` always silently collapsed to a flat 0.5
     default instead of computing anything real. This restores the real DB
     query and makes those three sub-scores return None ("insufficient
     data") instead of a fabricated 0.5 when there's genuinely nothing to
     compute from, following the same drop-and-renormalize pattern
     `grading.combined_grade` uses.
"""

from unittest.mock import AsyncMock

import pytest

from app.models.player import Player, Position
from app.models.historical_performance import PlayerHistoricalPerformance
from app.services.waiver_wire_service import WaiverWireService


def make_player(db, name, position, team, sleeper_id=None, bye_week=None,
                 ownership_percentage=10.0):
    player = Player(
        name=name,
        team=team,
        position=Position[position],
        sleeper_id=sleeper_id,
        bye_week=bye_week,
        ownership_percentage=ownership_percentage,
    )
    db.add(player)
    db.commit()
    db.refresh(player)
    return player


def make_historical_performance(db, player, season, week, fantasy_points_ppr):
    perf = PlayerHistoricalPerformance(
        player_id=player.id,
        season=season,
        week=week,
        fantasy_points_ppr=fantasy_points_ppr,
    )
    db.add(perf)
    db.commit()
    return perf


def sleeper_player_data(position="RB", team="BUF", full_name="Test Runner"):
    return {
        "full_name": full_name,
        "position": position,
        "team": team,
        "status": "Active",
    }


def patch_sleeper(service, trending, all_players):
    """Replace the two Sleeper calls get_live_trending_recommendations makes
    with fixed, deterministic data instead of hitting the network.
    """
    service.sleeper_service.get_trending_players = AsyncMock(return_value=trending)
    service.sleeper_service.get_all_players = AsyncMock(return_value=all_players)


class TestRosterNeedWeighting:
    """A roster genuinely needing RB should have RB candidates boosted vs.
    an identical candidate list scored against a roster overstocked at RB.
    """

    @pytest.mark.asyncio
    async def test_rb_boosted_when_roster_needs_rb(self, test_db_session):
        service = WaiverWireService(test_db_session)

        trending = [{"player_id": "1001", "count": 500}]
        all_players = {"1001": sleeper_player_data(position="RB")}
        patch_sleeper(service, trending, all_players)

        # Standard league (2 RB starters required), roster has 0 RBs.
        needy_roster = [
            {"position": "QB"}, {"position": "WR"}, {"position": "WR"},
            {"position": "TE"}, {"position": "K"}, {"position": "DEF"},
        ]
        league_settings = {"starters": {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1}}

        needy_recs = await service.get_live_trending_recommendations(
            user_roster=needy_roster, league_settings=league_settings
        )
        assert len(needy_recs) == 1
        assert needy_recs[0]["roster_need"] == "needs_attention"

        # Overstocked league: roster already has 5 RBs against a 2-RB requirement.
        overstocked_roster = [{"position": "RB"} for _ in range(5)]
        overstocked_recs = await service.get_live_trending_recommendations(
            user_roster=overstocked_roster, league_settings=league_settings
        )
        assert overstocked_recs[0]["roster_need"] == "overstocked"

        assert needy_recs[0]["confidence_score"] > overstocked_recs[0]["confidence_score"]

    @pytest.mark.asyncio
    async def test_unweighted_when_roster_and_settings_not_supplied(self, test_db_session):
        """Backward compatibility: existing callers that pass neither
        user_roster nor league_settings must not break, and must not have
        their confidence scores altered by roster-need logic.
        """
        service = WaiverWireService(test_db_session)

        trending = [{"player_id": "1001", "count": 500}, {"player_id": "1002", "count": 100}]
        all_players = {
            "1001": sleeper_player_data(position="RB", full_name="Runner One"),
            "1002": sleeper_player_data(position="WR", full_name="Catcher Two"),
        }
        patch_sleeper(service, trending, all_players)

        recs = await service.get_live_trending_recommendations()
        assert len(recs) == 2
        for rec in recs:
            assert rec["roster_need"] is None
            assert rec["confidence_score"] == round(rec["add_count_24h"] / 500, 3)


class TestByeWeekAwareness:
    """A candidate whose bye_week matches the current NFL week must be
    flagged/deprioritized vs. an identical candidate with a different bye.
    """

    @pytest.mark.asyncio
    async def test_bye_week_match_flags_and_deprioritizes(self, test_db_session):
        service = WaiverWireService(test_db_session)

        # test_db_session has no NFLGame rows, so get_current_week() falls
        # back to week 1 (matchup_analysis_service's documented no-data
        # fallback) -- confirmed real, deterministic behavior, not a guess.
        current_week = service.matchup_service.get_current_week()

        on_bye = make_player(
            test_db_session, "On Bye Guy", "RB", "BUF",
            sleeper_id="2001", bye_week=current_week,
        )
        not_on_bye = make_player(
            test_db_session, "Playing Guy", "RB", "MIA",
            sleeper_id="2002", bye_week=current_week + 5,
        )

        trending = [
            {"player_id": "2001", "count": 500},
            {"player_id": "2002", "count": 500},
        ]
        all_players = {
            "2001": sleeper_player_data(position="RB", team="BUF", full_name="On Bye Guy"),
            "2002": sleeper_player_data(position="RB", team="MIA", full_name="Playing Guy"),
        }
        patch_sleeper(service, trending, all_players)

        recs = await service.get_live_trending_recommendations()
        by_name = {r["player_name"]: r for r in recs}

        assert by_name["On Bye Guy"]["bye_week_flag"] is True
        assert by_name["Playing Guy"]["bye_week_flag"] is False
        assert by_name["On Bye Guy"]["confidence_score"] < by_name["Playing Guy"]["confidence_score"]


class TestEvaluatePlayerForWaiverDataConfidence:
    """_evaluate_player_for_waiver must produce a real, non-default score
    when real PlayerHistoricalPerformance rows exist, and an honest
    "insufficient data" signal (not a fabricated 0.5) when none exist.
    """

    @pytest.mark.asyncio
    async def test_real_history_produces_computed_confidence(self, test_db_session):
        service = WaiverWireService(test_db_session)
        player = make_player(test_db_session, "History Haver", "RB", "BUF", ownership_percentage=20.0)

        # 4 weeks of real, varied performance so performance/opportunity/
        # trend scores are all computable from real data.
        for week, pts in [(1, 8.0), (2, 12.0), (3, 15.0), (4, 18.0)]:
            make_historical_performance(test_db_session, player, season=2024, week=week, fantasy_points_ppr=pts)

        result = await service._evaluate_player_for_waiver(player, week=5, season=2024)

        assert result is not None
        assert result["data_confidence"] == "computed"
        assert result["component_scores"]["performance"] is not None
        assert result["component_scores"]["trend"] is not None
        # A real upward trend (8 -> 18 pts) should score above the old
        # fabricated flat 0.5 default.
        assert result["component_scores"]["trend"] > 0.5

    @pytest.mark.asyncio
    async def test_no_history_yields_insufficient_data_not_fabricated_default(self, test_db_session):
        service = WaiverWireService(test_db_session)
        player = make_player(test_db_session, "No History Guy", "RB", "MIA", ownership_percentage=20.0)
        # No target_share/snap_count_percentage set either, so opportunity
        # score also has nothing real to compute from.

        result = await service._evaluate_player_for_waiver(player, week=5, season=2024)

        assert result is not None
        assert result["data_confidence"] == "insufficient"
        assert result["component_scores"]["performance"] is None
        assert result["component_scores"]["opportunity"] is None
        assert result["component_scores"]["trend"] is None
        # Matchup/ownership are always real (don't depend on history), so
        # they should still be present, numeric components.
        assert isinstance(result["component_scores"]["matchup"], float)
        assert isinstance(result["component_scores"]["ownership"], float)

    @pytest.mark.asyncio
    async def test_sub_score_functions_return_none_not_flat_default(self, test_db_session):
        service = WaiverWireService(test_db_session)

        assert service._calculate_performance_score([]) is None
        assert service._calculate_trend_score([]) is None

        player = make_player(test_db_session, "Blank Slate", "WR", "NYJ")
        assert service._calculate_opportunity_score(player, []) is None
