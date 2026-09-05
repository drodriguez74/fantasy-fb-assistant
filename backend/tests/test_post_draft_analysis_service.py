"""
Unit tests for PostDraftAnalysisService covering three real bugs found by
comparing our app's post-draft roster grade against an external expert
analysis of the same real roster:

  1. `_analyze_roster_composition` / `_calculate_roster_grade` hardcoded a
     standard-lineup (QB1/RB2/WR2/TE1/K1/DEF1) instead of using the real
     per-league `starters` from `league_settings`.
  2. `_calculate_draft_value` never used a player's real ADP (`Player.adp`)
     vs. their actual draft pick -- it only compared projected_points
     against a static points-by-round table.
  3. No bye-week collision detection anywhere, and the overall roster grade
     used an ad-hoc avg_value_score - balance_penalty formula instead of the
     shared `grading.combined_grade` primitive.
"""

import pytest

from app.models.player import Player, Position
from app.services.post_draft_analysis_service import PostDraftAnalysisService


def make_player(db, name, position, team, projected_points=None, adp=None, bye_week=None):
    player = Player(
        name=name,
        team=team,
        position=Position[position],
        projected_points=projected_points,
        adp=adp,
        bye_week=bye_week,
    )
    db.add(player)
    db.commit()
    db.refresh(player)
    return player


def roster_entry(player, round_=None, pick=None):
    return {
        "player_id": player.id,
        "player_name": player.name,
        "round": round_,
        "pick": pick,
    }


class TestRealLeagueStarterRequirements:
    """Bug 1: composition/grade must use real per-league starters, not a
    hardcoded standard lineup.
    """

    @pytest.mark.asyncio
    async def test_two_qb_league_penalizes_single_qb_roster(self, test_db_session):
        service = PostDraftAnalysisService(test_db_session)

        qb1 = make_player(test_db_session, "QB One", "QB", "AAA", projected_points=20)
        rb1 = make_player(test_db_session, "RB One", "RB", "BBB", projected_points=15)
        rb2 = make_player(test_db_session, "RB Two", "RB", "CCC", projected_points=14)
        wr1 = make_player(test_db_session, "WR One", "WR", "DDD", projected_points=13)
        wr2 = make_player(test_db_session, "WR Two", "WR", "EEE", projected_points=12)
        te1 = make_player(test_db_session, "TE One", "TE", "FFF", projected_points=9)
        k1 = make_player(test_db_session, "K One", "K", "GGG", projected_points=8)
        def1 = make_player(test_db_session, "DEF One", "DEF", "HHH", projected_points=7)

        roster = [
            roster_entry(qb1, 1, 1),
            roster_entry(rb1, 2, 13),
            roster_entry(rb2, 3, 25),
            roster_entry(wr1, 4, 37),
            roster_entry(wr2, 5, 49),
            roster_entry(te1, 6, 61),
            roster_entry(k1, 12, 133),
            roster_entry(def1, 13, 145),
        ]

        # Standard lineup (1 QB required): fully satisfied, no QB penalty.
        standard_result = await service.analyze_roster_comprehensive(roster, {})
        standard_composition = standard_result["roster_analysis"]["composition"]
        assert standard_composition["position_breakdown"]["QB"]["needs_attention"] is False

        # 2-QB league: the exact same roster is now short at QB.
        two_qb_settings = {"starters": {"QB": 2, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1}}
        two_qb_result = await service.analyze_roster_comprehensive(roster, two_qb_settings)
        two_qb_composition = two_qb_result["roster_analysis"]["composition"]
        assert two_qb_composition["position_breakdown"]["QB"]["needs_attention"] is True
        assert two_qb_composition["position_breakdown"]["QB"]["recommended_minimum"] == 2

        # The 2-QB league's composition score must be strictly worse than the
        # standard-lineup grading of the identical roster.
        assert two_qb_composition["composition_score"] < standard_composition["composition_score"]

        # Overall grade's balance_penalty must also reflect the real
        # requirement, not the hardcoded default.
        two_qb_grade = two_qb_result["roster_analysis"]["overall_grade"]
        standard_grade = standard_result["roster_analysis"]["overall_grade"]
        assert two_qb_grade["balance_penalty"] > standard_grade["balance_penalty"]


class TestRealAdpDraftValue:
    """Bug 2: draft value must use real ADP vs. actual pick as the primary
    signal, not projected_points-vs-round-expectations.
    """

    @pytest.mark.asyncio
    async def test_steal_by_adp_outranks_reach_by_adp_despite_points_saying_otherwise(
        self, test_db_session
    ):
        service = PostDraftAnalysisService(test_db_session)

        # Steal: real ADP says this player "should" go around pick 100, but
        # they fell to pick 200 -- a big steal by ADP. Give them LOW
        # projected_points relative to their (early) draft_round so the old
        # round-expectations-vs-points formula would call this a reach.
        steal = make_player(
            test_db_session, "Steal Guy", "WR", "AAA", projected_points=60, adp=100.0
        )
        # Reach: real ADP says this player "should" go around pick 200, but
        # they were taken at pick 20 -- a big reach by ADP. Give them HIGH
        # projected_points relative to their (late) draft_round so the old
        # formula would call this great value.
        reach = make_player(
            test_db_session, "Reach Guy", "WR", "BBB", projected_points=200, adp=200.0
        )

        roster = [
            roster_entry(steal, round_=1, pick=200),  # picked WAY later than ADP -> steal
            roster_entry(reach, round_=1, pick=20),    # picked WAY earlier than ADP -> reach
        ]

        result = await service.analyze_roster_comprehensive(roster, {})
        evaluations = {
            e["player_info"]["name"]: e["value_analysis"]
            for e in result["roster_analysis"]["player_evaluations"]
        }

        steal_value = evaluations["Steal Guy"]
        reach_value = evaluations["Reach Guy"]

        # ADP was actually used as the signal.
        assert steal_value["value_source"] == "adp"
        assert reach_value["value_source"] == "adp"

        # Real-ADP-based grading: the steal must score higher than the reach,
        # even though projected_points-vs-round-expectations would say the
        # opposite (reach has vastly higher projected_points).
        assert steal_value["value_percentage"] > 100
        assert reach_value["value_percentage"] < 100
        assert steal_value["value_percentage"] > reach_value["value_percentage"]


class TestByeWeekCollisions:
    """Bug 3: bye-week collisions must be detected, and the overall grade
    must penalize a roster whose same-position players share a bye week
    relative to an otherwise-identical roster with staggered byes.
    """

    def _two_qb_roster(self, db, byes):
        # Standard (fallback) lineup only requires 1 starting QB, but this
        # roster carries 2 QBs -- rostering a backup is exactly the scenario
        # where a *shared* bye week between them is a real, distinct risk
        # (0 active QBs that week) vs. staggered byes (always >= 1 active).
        qb1 = make_player(db, "QB One", "QB", "AAA", projected_points=20, bye_week=byes[0])
        qb2 = make_player(db, "QB Two", "QB", "BBB", projected_points=18, bye_week=byes[1])
        rb1 = make_player(db, "RB One", "RB", "CCC", projected_points=15, bye_week=5)
        rb2 = make_player(db, "RB Two", "RB", "DDD", projected_points=14, bye_week=6)
        wr1 = make_player(db, "WR One", "WR", "EEE", projected_points=13, bye_week=7)
        wr2 = make_player(db, "WR Two", "WR", "FFF", projected_points=12, bye_week=8)
        te1 = make_player(db, "TE One", "TE", "GGG", projected_points=9, bye_week=9)
        k1 = make_player(db, "K One", "K", "HHH", projected_points=8, bye_week=10)
        def1 = make_player(db, "DEF One", "DEF", "III", projected_points=7, bye_week=11)
        players = [qb1, qb2, rb1, rb2, wr1, wr2, te1, k1, def1]
        return [roster_entry(p, i + 1, (i + 1) * 12) for i, p in enumerate(players)]

    @pytest.mark.asyncio
    async def test_shared_bye_week_scores_lower_than_staggered_byes(self, test_db_session):
        # Standard (fallback) lineup: only 1 QB is a required starter, but
        # each roster below carries 2 QBs -- a shared bye between them drops
        # active starters to 0 that week, which staggered byes never do.
        league_settings = {}

        service_a = PostDraftAnalysisService(test_db_session)
        colliding_roster = self._two_qb_roster(test_db_session, byes=(9, 9))
        colliding_result = await service_a.analyze_roster_comprehensive(colliding_roster, league_settings)

        service_b = PostDraftAnalysisService(test_db_session)
        staggered_roster = self._two_qb_roster(test_db_session, byes=(4, 12))
        staggered_result = await service_b.analyze_roster_comprehensive(staggered_roster, league_settings)

        colliding_composition = colliding_result["roster_analysis"]["composition"]
        staggered_composition = staggered_result["roster_analysis"]["composition"]

        # Single-player positions (TE/K/DEF here) always "collide" with their
        # own bye week regardless of staggering, since active drops to 0 on
        # that player's bye -- restrict the comparison to QB, the position
        # that actually differs between the two rosters (shared vs.
        # staggered byes across two required starters).
        colliding_qb_collisions = [
            c for c in colliding_composition["bye_week_collisions"] if c["position"] == "QB"
        ]
        staggered_qb_collisions = [
            c for c in staggered_composition["bye_week_collisions"] if c["position"] == "QB"
        ]
        assert len(colliding_qb_collisions) > 0
        assert len(staggered_qb_collisions) == 0

        colliding_grade = colliding_result["roster_analysis"]["overall_grade"]
        staggered_grade = staggered_result["roster_analysis"]["overall_grade"]

        assert colliding_grade["components"]["bye_weeks"] < staggered_grade["components"]["bye_weeks"]
        assert colliding_grade["score"] < staggered_grade["score"]


class TestImprovementRecommendationsUseRealSignals:
    """`_generate_improvement_recommendations` bugs fixed:

      1. It used to decide "immediate_needs" by substring-matching free-text
         weakness sentences (`'RB' in weakness`), which misfires on newer
         sentence types that mention a position code without meaning "you
         need to draft/add another player at this position" -- a bench-depth
         -cliff note (`grading.bench_depth_notes`) or a bye-week-collision
         note (`grading.value_and_bye_strengths_weaknesses`). It now reads
         the real `composition_analysis["position_breakdown"][pos]
         ["needs_attention"]` boolean instead.
      2. It used to fabricate a generic `target_criteria` string with no real
         player name. It now calls
         `waiver_service.get_live_trending_recommendations(position=...)`
         (mocked below) and surfaces real candidate player names, filtering
         out anyone already on the roster.
    """

    @staticmethod
    def _standard_full_roster(db, extra_rb=0):
        """A roster that fully satisfies the standard fallback lineup
        (QB1/RB2/WR2/TE1/K1/DEF1) by default, so nothing hits
        `needs_attention`, plus a way to add extra deep RBs (with a
        deliberately weak backup tier) to trigger `bench_depth_notes`
        without going below the real required RB count.
        """
        qb1 = make_player(db, "QB One", "QB", "AAA", projected_points=20)
        rb1 = make_player(db, "RB One", "RB", "BBB", projected_points=20)
        rb2 = make_player(db, "RB Two", "RB", "CCC", projected_points=18)
        wr1 = make_player(db, "WR One", "WR", "DDD", projected_points=13)
        wr2 = make_player(db, "WR Two", "WR", "EEE", projected_points=12)
        te1 = make_player(db, "TE One", "TE", "FFF", projected_points=9)
        k1 = make_player(db, "K One", "K", "GGG", projected_points=8)
        def1 = make_player(db, "DEF One", "DEF", "HHH", projected_points=7)
        players = [qb1, rb1, rb2, wr1, wr2, te1, k1, def1]

        for i in range(extra_rb):
            # Deep, weak backups -- well below thin_ratio/thin_floor of the
            # RB1/RB2 starter tier -- to trigger bench_depth_notes without
            # changing RB's needs_attention (still >= the required 2).
            players.append(
                make_player(db, f"RB Deep {i}", "RB", "ZZZ", projected_points=1.0)
            )

        return [roster_entry(p, i + 1, (i + 1) * 12) for i, p in enumerate(players)]

    @pytest.mark.asyncio
    async def test_real_quantity_need_produces_immediate_need_with_real_player(
        self, test_db_session
    ):
        service = PostDraftAnalysisService(test_db_session)

        # Only 1 RB against the standard lineup's real requirement of 2 --
        # a genuine structural shortfall.
        qb1 = make_player(test_db_session, "QB One", "QB", "AAA", projected_points=20)
        rb1 = make_player(test_db_session, "RB One", "RB", "BBB", projected_points=15)
        wr1 = make_player(test_db_session, "WR One", "WR", "DDD", projected_points=13)
        wr2 = make_player(test_db_session, "WR Two", "WR", "EEE", projected_points=12)
        te1 = make_player(test_db_session, "TE One", "TE", "FFF", projected_points=9)
        k1 = make_player(test_db_session, "K One", "K", "GGG", projected_points=8)
        def1 = make_player(test_db_session, "DEF One", "DEF", "HHH", projected_points=7)
        roster = [
            roster_entry(qb1, 1, 1),
            roster_entry(rb1, 2, 13),
            roster_entry(wr1, 4, 37),
            roster_entry(wr2, 5, 49),
            roster_entry(te1, 6, 61),
            roster_entry(k1, 12, 133),
            roster_entry(def1, 13, 145),
        ]

        async def fake_trending(position=None, priority=None, limit=20):
            assert position == "RB"
            return [
                {
                    "player_name": "Real Waiver RB",
                    "position": "RB",
                    "team": "KC",
                    "confidence_score": 0.87,
                    "reason": "Trending add: 12,345 adds across Sleeper fantasy leagues in the last 24 hours.",
                }
            ]

        service.waiver_service.get_live_trending_recommendations = fake_trending

        result = await service.analyze_roster_comprehensive(roster, {})
        immediate_needs = result["improvement_recommendations"]["immediate_needs"]

        rb_needs = [n for n in immediate_needs if n["position"] == "RB"]
        assert len(rb_needs) == 1
        assert rb_needs[0]["priority"] == "High"
        assert "target_criteria" not in rb_needs[0]
        targets = rb_needs[0]["targets"]
        assert len(targets) == 1
        assert targets[0]["player_name"] == "Real Waiver RB"

    @pytest.mark.asyncio
    async def test_bench_depth_weakness_does_not_trigger_false_immediate_need(
        self, test_db_session
    ):
        """Regression test: a bench-depth-cliff sentence for RB (headcount
        fully satisfies the real requirement, but backups are much weaker
        than starters) must NOT produce an `immediate_needs` "add an RB"
        recommendation.
        """
        service = PostDraftAnalysisService(test_db_session)

        roster = self._standard_full_roster(test_db_session, extra_rb=2)

        async def fake_trending(position=None, priority=None, limit=20):
            # Should never be called for RB since RB doesn't need_attention.
            raise AssertionError(f"waiver lookup should not run for {position}")

        service.waiver_service.get_live_trending_recommendations = fake_trending

        result = await service.analyze_roster_comprehensive(roster, {})
        composition = result["roster_analysis"]["composition"]
        assert composition["position_breakdown"]["RB"]["needs_attention"] is False

        improvement = result["improvement_recommendations"]
        rb_immediate_needs = [
            n for n in improvement["immediate_needs"] if n["position"] == "RB"
        ]
        assert rb_immediate_needs == []

        # The bench-depth signal should still surface, just not as an
        # "add a player" immediate need.
        weaknesses = result["roster_analysis"]["strengths_weaknesses"]["weaknesses"]
        assert any("depth beyond your top" in w for w in weaknesses)
        assert any("depth beyond your top" in c for c in improvement["depth_concerns"])

    @pytest.mark.asyncio
    async def test_bye_week_collision_weakness_does_not_trigger_false_immediate_need(
        self, test_db_session
    ):
        """Regression test: a bye-week-collision sentence mentioning QB must
        not trigger an "add a QB" immediate need when QB's real headcount
        already satisfies the league's requirement.
        """
        service = PostDraftAnalysisService(test_db_session)

        # 2 QBs sharing a bye week -- satisfies the (fallback) 1-QB
        # requirement by headcount, so needs_attention is False, but still
        # produces a bye-week-collision weakness sentence mentioning QB.
        qb1 = make_player(test_db_session, "QB One", "QB", "AAA", projected_points=20, bye_week=9)
        qb2 = make_player(test_db_session, "QB Two", "QB", "BBB", projected_points=18, bye_week=9)
        rb1 = make_player(test_db_session, "RB One", "RB", "CCC", projected_points=15, bye_week=5)
        rb2 = make_player(test_db_session, "RB Two", "RB", "DDD", projected_points=14, bye_week=6)
        wr1 = make_player(test_db_session, "WR One", "WR", "EEE", projected_points=13, bye_week=7)
        wr2 = make_player(test_db_session, "WR Two", "WR", "FFF", projected_points=12, bye_week=8)
        te1 = make_player(test_db_session, "TE One", "TE", "GGG", projected_points=9, bye_week=10)
        k1 = make_player(test_db_session, "K One", "K", "HHH", projected_points=8, bye_week=11)
        def1 = make_player(test_db_session, "DEF One", "DEF", "III", projected_points=7, bye_week=12)
        players = [qb1, qb2, rb1, rb2, wr1, wr2, te1, k1, def1]
        roster = [roster_entry(p, i + 1, (i + 1) * 12) for i, p in enumerate(players)]

        async def fake_trending(position=None, priority=None, limit=20):
            raise AssertionError(f"waiver lookup should not run for {position}")

        service.waiver_service.get_live_trending_recommendations = fake_trending

        result = await service.analyze_roster_comprehensive(roster, {})
        composition = result["roster_analysis"]["composition"]
        assert composition["position_breakdown"]["QB"]["needs_attention"] is False

        improvement = result["improvement_recommendations"]
        qb_immediate_needs = [
            n for n in improvement["immediate_needs"] if n["position"] == "QB"
        ]
        assert qb_immediate_needs == []
        assert any(
            "on bye" in c and "QB" in c for c in improvement["bye_week_concerns"]
        )

    @pytest.mark.asyncio
    async def test_already_rostered_candidate_is_excluded(self, test_db_session):
        """A live trending candidate that happens to already be on the
        user's own roster (e.g. duplicate row, or already picked up
        elsewhere) must be filtered out rather than recommended again.
        """
        service = PostDraftAnalysisService(test_db_session)

        qb1 = make_player(test_db_session, "QB One", "QB", "AAA", projected_points=20)
        rb1 = make_player(test_db_session, "RB One", "RB", "BBB", projected_points=15)
        wr1 = make_player(test_db_session, "WR One", "WR", "DDD", projected_points=13)
        wr2 = make_player(test_db_session, "WR Two", "WR", "EEE", projected_points=12)
        te1 = make_player(test_db_session, "TE One", "TE", "FFF", projected_points=9)
        k1 = make_player(test_db_session, "K One", "K", "GGG", projected_points=8)
        def1 = make_player(test_db_session, "DEF One", "DEF", "HHH", projected_points=7)
        roster = [
            roster_entry(qb1, 1, 1),
            roster_entry(rb1, 2, 13),
            roster_entry(wr1, 4, 37),
            roster_entry(wr2, 5, 49),
            roster_entry(te1, 6, 61),
            roster_entry(k1, 12, 133),
            roster_entry(def1, 13, 145),
        ]

        async def fake_trending(position=None, priority=None, limit=20):
            return [
                # Already on the roster -- must be excluded.
                {
                    "player_name": "RB One",
                    "position": "RB",
                    "team": "BBB",
                    "confidence_score": 0.95,
                    "reason": "Trending add.",
                },
                {
                    "player_name": "Fresh Waiver RB",
                    "position": "RB",
                    "team": "SF",
                    "confidence_score": 0.5,
                    "reason": "Trending add.",
                },
            ]

        service.waiver_service.get_live_trending_recommendations = fake_trending

        result = await service.analyze_roster_comprehensive(roster, {})
        rb_needs = [
            n for n in result["improvement_recommendations"]["immediate_needs"]
            if n["position"] == "RB"
        ]
        assert len(rb_needs) == 1
        target_names = [t["player_name"] for t in rb_needs[0]["targets"]]
        assert "RB One" not in target_names
        assert "Fresh Waiver RB" in target_names
