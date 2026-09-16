"""Tests for the Sleeper branch of build_roster_analysis_snapshot.

Sleeper roster analysis previously fell into the honest "not yet
implemented for SLEEPER leagues" catch-all -- these tests cover the real
implementation added to replace that, resolving raw Sleeper roster-id
lists against the real player catalog and grading real composition.
"""
from unittest.mock import AsyncMock

import pytest

from app.models.user_league import UserLeague, PlatformType
from app.services import league_snapshots as snap_module
from app.services.league_snapshots import build_roster_analysis_snapshot, SnapshotBuildError


def make_sleeper_league(**overrides):
    defaults = dict(
        user_id=1,
        platform=PlatformType.SLEEPER,
        league_id="999888",
        team_id="1",
        league_name="Test Sleeper League",
        season=2024,
        scoring_format="PPR",
        league_size=10,
    )
    defaults.update(overrides)
    return UserLeague(**defaults)


SAMPLE_ROSTERS = [
    {
        "roster_id": 1,
        "owner_id": "u1",
        "players": ["100", "101", "102"],
        "starters": ["100", "101"],
        "reserve": [],
    },
    {
        "roster_id": 2,
        "owner_id": "u2",
        "players": ["200"],
        "starters": ["200"],
        "reserve": [],
    },
]

SAMPLE_USERS = [
    {"user_id": "u1", "display_name": "Me", "metadata": {"team_name": "My Sleeper Team"}},
    {"user_id": "u2", "display_name": "Rival"},
]

SAMPLE_PLAYERS = {
    "100": {"full_name": "Sleeper QB", "position": "QB", "team": "KC", "injury_status": ""},
    "101": {"full_name": "Sleeper RB", "position": "RB", "team": "SF", "injury_status": "Questionable"},
    "102": {"full_name": "Sleeper Bench WR", "position": "WR", "team": "MIA", "injury_status": ""},
}

SAMPLE_LEAGUE_INFO = {
    "league_id": "999888",
    "roster_positions": ["QB", "RB", "WR", "WR", "FLEX", "BN", "BN", "BN"],
    "scoring_settings": {"rec": 1.0},
}


@pytest.mark.asyncio
async def test_sleeper_roster_analysis_resolves_real_players(monkeypatch):
    league = make_sleeper_league()

    monkeypatch.setattr(snap_module.sleeper_service, "get_league_info", AsyncMock(return_value=SAMPLE_LEAGUE_INFO))
    monkeypatch.setattr(snap_module.sleeper_service, "get_league_rosters", AsyncMock(return_value=SAMPLE_ROSTERS))
    monkeypatch.setattr(snap_module.sleeper_service, "get_league_users", AsyncMock(return_value=SAMPLE_USERS))
    monkeypatch.setattr(snap_module.sleeper_service, "get_all_players", AsyncMock(return_value=SAMPLE_PLAYERS))

    result = await build_roster_analysis_snapshot(league)

    ra = result["roster_analysis"]
    assert ra["team_name"] == "My Sleeper Team"
    assert ra["total_players"] == 3
    names = {p["name"] for p in ra["players"]}
    assert names == {"Sleeper QB", "Sleeper RB", "Sleeper Bench WR"}

    starters = {p["name"] for p in ra["composition"]["starting_lineup"]}
    bench = {p["name"] for p in ra["composition"]["bench_players"]}
    assert starters == {"Sleeper QB", "Sleeper RB"}
    assert bench == {"Sleeper Bench WR"}

    # Real injury designation surfaced, healthy players excluded.
    assert ra["injury_concerns"] == [
        {"player": "Sleeper RB", "position": "RB", "team": "SF", "status": "Questionable"}
    ]

    # A real grade was computed (not the "not yet computed" placeholder).
    assert ra["overall_grade"]["grade"] != "N/A"
    assert ra["overall_grade"]["score"] is not None


@pytest.mark.asyncio
async def test_sleeper_missing_team_id_returns_honest_ungraded_state(monkeypatch):
    league = make_sleeper_league(team_id=None)
    result = await build_roster_analysis_snapshot(league)
    ra = result["roster_analysis"]
    assert ra["overall_grade"]["grade"] == "N/A"
    assert "not identified" in ra["overall_grade"]["description"]


@pytest.mark.asyncio
async def test_sleeper_unknown_roster_id_raises_snapshot_build_error(monkeypatch):
    league = make_sleeper_league(team_id="999")

    monkeypatch.setattr(snap_module.sleeper_service, "get_league_info", AsyncMock(return_value=SAMPLE_LEAGUE_INFO))
    monkeypatch.setattr(snap_module.sleeper_service, "get_league_rosters", AsyncMock(return_value=SAMPLE_ROSTERS))
    monkeypatch.setattr(snap_module.sleeper_service, "get_league_users", AsyncMock(return_value=SAMPLE_USERS))
    monkeypatch.setattr(snap_module.sleeper_service, "get_all_players", AsyncMock(return_value=SAMPLE_PLAYERS))

    with pytest.raises(SnapshotBuildError):
        await build_roster_analysis_snapshot(league)


@pytest.mark.asyncio
async def test_sleeper_rosters_fetch_error_raises_snapshot_build_error(monkeypatch):
    league = make_sleeper_league()

    monkeypatch.setattr(snap_module.sleeper_service, "get_league_info", AsyncMock(return_value=SAMPLE_LEAGUE_INFO))
    monkeypatch.setattr(
        snap_module.sleeper_service, "get_league_rosters", AsyncMock(return_value=[{"error": "boom"}])
    )
    monkeypatch.setattr(snap_module.sleeper_service, "get_league_users", AsyncMock(return_value=SAMPLE_USERS))
    monkeypatch.setattr(snap_module.sleeper_service, "get_all_players", AsyncMock(return_value=SAMPLE_PLAYERS))

    with pytest.raises(SnapshotBuildError):
        await build_roster_analysis_snapshot(league)


@pytest.mark.asyncio
async def test_sleeper_na_injury_status_is_not_flagged_as_a_concern(monkeypatch):
    """Live-verified against Sleeper's real public player catalog: 'NA' is
    mostly used for inactive/practice-squad players with no real injury --
    it must not surface as an injury concern the way 'Questionable'/'Out' do."""
    league = make_sleeper_league()
    rosters = [
        {"roster_id": 1, "owner_id": "u1", "players": ["100"], "starters": ["100"], "reserve": []},
    ]
    players = {"100": {"full_name": "NA Status Player", "position": "WR", "team": "KC", "injury_status": "NA"}}

    monkeypatch.setattr(snap_module.sleeper_service, "get_league_info", AsyncMock(return_value=SAMPLE_LEAGUE_INFO))
    monkeypatch.setattr(snap_module.sleeper_service, "get_league_rosters", AsyncMock(return_value=rosters))
    monkeypatch.setattr(snap_module.sleeper_service, "get_league_users", AsyncMock(return_value=SAMPLE_USERS))
    monkeypatch.setattr(snap_module.sleeper_service, "get_all_players", AsyncMock(return_value=players))

    result = await build_roster_analysis_snapshot(league)
    ra = result["roster_analysis"]
    assert ra["injury_concerns"] == []
    assert ra["players"][0]["injury_status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_sleeper_unresolvable_player_id_degrades_honestly(monkeypatch):
    """A player id with no match in the global catalog shouldn't crash the
    whole roster analysis -- it should show up as an honest unknown, not be
    silently dropped or fabricated."""
    league = make_sleeper_league()
    rosters = [
        {"roster_id": 1, "owner_id": "u1", "players": ["999"], "starters": [], "reserve": []},
    ]

    monkeypatch.setattr(snap_module.sleeper_service, "get_league_info", AsyncMock(return_value=SAMPLE_LEAGUE_INFO))
    monkeypatch.setattr(snap_module.sleeper_service, "get_league_rosters", AsyncMock(return_value=rosters))
    monkeypatch.setattr(snap_module.sleeper_service, "get_league_users", AsyncMock(return_value=SAMPLE_USERS))
    monkeypatch.setattr(snap_module.sleeper_service, "get_all_players", AsyncMock(return_value={}))

    result = await build_roster_analysis_snapshot(league)
    ra = result["roster_analysis"]
    assert ra["total_players"] == 1
    assert "Unknown Player" in ra["players"][0]["name"]
