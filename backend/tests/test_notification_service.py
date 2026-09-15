"""
Tests for app.services.notification_service, focused on the weekly digest
(generate_weekly_digest_for_user / _iso_week_key) -- the real, genuinely
schedule-driven exception in this module. notify_trending_adds is exercised
indirectly elsewhere (waiver_wire endpoint tests).
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.models.notification import Notification
from app.models.user import User
from app.models.user_league import PlatformType, UserLeague
from app.services.notification_service import (
    _iso_week_key,
    generate_weekly_digest_for_user,
)


def make_user(db, email=None):
    # Unique per call -- the test DB session isn't rolled back between
    # tests in this suite (see conftest.py), so a fixed email would collide
    # across test functions in this same file. Explicit high id: several
    # OTHER test files hardcode `user_id=1` on UserLeague rows without ever
    # inserting a matching User row (sqlite has no FK enforcement by
    # default) -- if a plain autoincrement happened to also land on 1 here,
    # get_user_leagues(1) would legitimately (and confusingly) pick up
    # those unrelated leagues too, since the shared test DB isn't isolated
    # per file.
    email = email or f"digest-{uuid.uuid4().hex[:8]}@test.com"
    user = User(
        id=90000 + uuid.uuid4().int % 9000,
        email=email,
        username=email.split("@")[0],
        hashed_password="x",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def make_espn_league(db, user, team_id="1", league_id="999", name="Test League"):
    league = UserLeague(
        user_id=user.id,
        platform=PlatformType.ESPN,
        league_id=league_id,
        team_id=team_id,
        league_name=name,
        season=2024,
    )
    db.add(league)
    db.commit()
    db.refresh(league)
    return league


class TestIsoWeekKey:
    def test_stable_within_the_same_iso_week(self):
        monday = datetime(2026, 9, 14, 8, 0, tzinfo=timezone.utc)
        sunday = datetime(2026, 9, 20, 23, 0, tzinfo=timezone.utc)
        assert _iso_week_key(monday) == _iso_week_key(sunday)

    def test_differs_across_a_week_boundary(self):
        this_week = datetime(2026, 9, 20, 23, 0, tzinfo=timezone.utc)
        next_week = datetime(2026, 9, 21, 1, 0, tzinfo=timezone.utc)
        assert _iso_week_key(this_week) != _iso_week_key(next_week)


class TestGenerateWeeklyDigestForUser:
    @pytest.mark.asyncio
    async def test_no_connected_leagues_creates_nothing(self, test_db_session):
        user = make_user(test_db_session)
        created = await generate_weekly_digest_for_user(test_db_session, user)
        assert created == []

    @pytest.mark.asyncio
    async def test_real_waiver_target_and_bye_produce_one_notification(self, test_db_session):
        user = make_user(test_db_session)
        league = make_espn_league(test_db_session, user)

        fake_recs = [
            {
                "player_name": "Trending Guy",
                "position": "RB",
                "team": "SEA",
                "priority": "urgent",
                "add_count_24h": 12345,
            }
        ]
        fake_radar = {
            "upcoming_byes": [
                {"player_name": "Bye Guy", "weeks_until_bye": 0},
            ]
        }

        with patch(
            "app.services.waiver_wire_service.WaiverWireService.get_live_trending_recommendations",
            new=AsyncMock(return_value=fake_recs),
        ), patch(
            "app.services.espn_service_enhanced.espn_service_enhanced.get_bye_week_radar",
            new=AsyncMock(return_value=fake_radar),
        ):
            created = await generate_weekly_digest_for_user(test_db_session, user)

        assert len(created) == 1
        notification = created[0]
        assert notification.type == "weekly_digest"
        assert league.league_name in notification.title
        assert "Trending Guy" in notification.body
        assert "Bye Guy" in notification.body
        assert notification.dedupe_key.startswith(f"weekly_digest:{league.id}:")

    @pytest.mark.asyncio
    async def test_no_real_content_skips_the_league_entirely(self, test_db_session):
        user = make_user(test_db_session)
        make_espn_league(test_db_session, user)

        with patch(
            "app.services.waiver_wire_service.WaiverWireService.get_live_trending_recommendations",
            new=AsyncMock(return_value=[]),
        ), patch(
            "app.services.espn_service_enhanced.espn_service_enhanced.get_bye_week_radar",
            new=AsyncMock(return_value={"upcoming_byes": []}),
        ):
            created = await generate_weekly_digest_for_user(test_db_session, user)

        assert created == []

    @pytest.mark.asyncio
    async def test_already_sent_this_week_is_a_no_op(self, test_db_session):
        user = make_user(test_db_session)
        league = make_espn_league(test_db_session, user)

        week_key = _iso_week_key(datetime.now(timezone.utc))
        existing = Notification(
            user_id=user.id,
            type="weekly_digest",
            title="Already sent",
            body="Already sent",
            dedupe_key=f"weekly_digest:{league.id}:{week_key}",
            is_read=False,
        )
        test_db_session.add(existing)
        test_db_session.commit()

        fake_recs = [
            {
                "player_name": "Trending Guy",
                "position": "RB",
                "team": "SEA",
                "priority": "urgent",
                "add_count_24h": 999,
            }
        ]
        with patch(
            "app.services.waiver_wire_service.WaiverWireService.get_live_trending_recommendations",
            new=AsyncMock(return_value=fake_recs),
        ), patch(
            "app.services.espn_service_enhanced.espn_service_enhanced.get_bye_week_radar",
            new=AsyncMock(return_value={"upcoming_byes": []}),
        ):
            created = await generate_weekly_digest_for_user(test_db_session, user)

        assert created == []

    @pytest.mark.asyncio
    async def test_one_league_failing_does_not_block_another(self, test_db_session):
        user = make_user(test_db_session)
        make_espn_league(test_db_session, user, team_id="1", league_id="111", name="Broken League")
        make_espn_league(test_db_session, user, team_id="2", league_id="222", name="Working League")

        fake_recs = [
            {
                "player_name": "Trending Guy",
                "position": "RB",
                "team": "SEA",
                "priority": "urgent",
                "add_count_24h": 999,
            }
        ]

        call_count = {"n": 0}

        async def flaky_radar(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("ESPN session expired")
            return {"upcoming_byes": []}

        with patch(
            "app.services.waiver_wire_service.WaiverWireService.get_live_trending_recommendations",
            new=AsyncMock(return_value=fake_recs),
        ), patch(
            "app.services.espn_service_enhanced.espn_service_enhanced.get_bye_week_radar",
            side_effect=flaky_radar,
        ):
            created = await generate_weekly_digest_for_user(test_db_session, user)

        # Both leagues still get a digest from the real waiver-target data
        # alone -- the bye-radar failure on one league doesn't stop it, and
        # doesn't propagate to the other league either.
        assert len(created) == 2
