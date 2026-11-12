"""Services that had no tests: consensus ranking, the player pool filter,
per-league position pressure, custom scoring, and the snapshot cache."""
import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks

from app.models.league_scoring import LeagueScoring
from app.models.league_snapshot import LeagueSnapshot
from app.services import snapshot_cache
from app.services.consensus_ranking_service import (
    SLEEPER_UNRANKED_SENTINEL,
    ConsensusRankingService,
    _blend,
    _percentile_map,
    normalize_player_name,
)
from app.services.league_competition import compute_position_pressure
from app.services.league_snapshots import SnapshotBuildError
from app.services.player_pool import is_on_active_roster
from app.services.scoring_calculation_service import ScoringCalculationService


# ---- consensus ranking ------------------------------------------------------

def test_names_match_across_sources():
    assert normalize_player_name("Michael Pittman Jr.") == normalize_player_name("michael pittman")
    assert normalize_player_name("Ja'Marr Chase") == "jamarr chase"
    assert normalize_player_name("Amon-Ra St. Brown") == "amonra st brown"
    assert normalize_player_name(None) == ""


def test_percentiles_put_the_best_at_100_either_direction():
    lower_is_better = _percentile_map([("a", 1), ("b", 2), ("c", 3)], reverse=False)
    assert lower_is_better == {"a": 100.0, "b": 50.0, "c": 0.0}
    higher_is_better = _percentile_map([("a", 10.0), ("b", 90.0)], reverse=True)
    assert higher_is_better == {"a": 0.0, "b": 100.0}


def test_percentile_ties_share_a_value_and_one_player_is_100():
    tied = _percentile_map([("a", 5), ("b", 5), ("c", 9)], reverse=False)
    assert tied["a"] == tied["b"] == 75.0
    assert tied["c"] == 0.0
    assert _percentile_map([("only", 42)], reverse=False) == {"only": 100.0}
    assert _percentile_map([], reverse=True) == {}


def test_blend_averages_only_the_sources_present():
    assert _blend(80.0, None, 40.0) == 60.0
    assert _blend(None, None) == 0.0


def test_rank_players_orders_by_sleeper_rank_and_numbers_them():
    players = [
        {"full_name": "Third", "search_rank": 30},
        {"full_name": "First", "search_rank": 1},
        {"full_name": "Second", "search_rank": 12},
    ]
    ranked = ConsensusRankingService().rank_players(players)
    assert [p["full_name"] for p in ranked] == ["First", "Second", "Third"]
    assert [p["consensus"]["consensus_rank"] for p in ranked] == [1, 2, 3]
    assert ranked[0]["consensus"]["source_count"] == 1
    assert ranked[0]["consensus"]["sources"] == {"sleeper_rank": 1}
    # The input dicts are copied, not changed.
    assert "consensus" not in players[0]


def test_unranked_players_sort_last_rather_than_scoring_zero():
    players = [
        {"full_name": "No Signal", "search_rank": SLEEPER_UNRANKED_SENTINEL},
        {"full_name": "Worst Ranked", "search_rank": 400},
        {"full_name": "Best Ranked", "search_rank": 2},
    ]
    ranked = ConsensusRankingService().rank_players(players)
    assert [p["full_name"] for p in ranked] == ["Best Ranked", "Worst Ranked", "No Signal"]
    assert ranked[-1]["consensus"]["source_count"] == 0


def test_a_second_source_is_matched_by_name_and_blended():
    espn = [
        {"name": "Alpha Back", "percent_owned": 95.0},
        {"name": "Beta Back Jr.", "percent_owned": 20.0},
    ]
    sleeper = [
        {"full_name": "Alpha Back", "search_rank": 50},
        {"full_name": "Beta Back", "search_rank": 5},
        {"full_name": "Someone Else", "search_rank": 500},
    ]
    ranked = ConsensusRankingService().rank_players(espn, other_source_players=sleeper)
    by_name = {p["name"]: p["consensus"] for p in ranked}
    assert by_name["Alpha Back"]["source_count"] == 2
    assert by_name["Beta Back Jr."]["sources"]["sleeper_rank"] == 5
    # ESPN says Alpha (100 vs 0); Sleeper says Beta (100 vs 50): Alpha 75, Beta 50.
    assert by_name["Alpha Back"]["consensus_score"] == 75.0
    assert by_name["Beta Back Jr."]["consensus_score"] == 50.0


# ---- player pool ------------------------------------------------------------

def test_active_roster_needs_a_team_and_an_active_status():
    assert is_on_active_roster({"team": "BUF", "status": "Active"})
    # Sleeper keeps long-retired players "Active" with no team.
    assert not is_on_active_roster({"team": None, "status": "Active"})
    assert not is_on_active_roster({"team": "BUF", "status": "Inactive"})
    assert not is_on_active_roster({})


# ---- position pressure --------------------------------------------------------

def _roster(**counts):
    return [{"position": pos} for pos, n in counts.items() for _ in range(n)]


def test_position_pressure_counts_thin_teams_and_skips_the_user():
    # "Thin" = no more players at a position than the league starts there.
    settings = {"starters": {"QB": 1, "RB": 2, "WR": 2, "TE": 1}}
    deep = _roster(QB=3, RB=8, WR=8, TE=3)
    thin_rb = _roster(QB=3, RB=2, WR=8, TE=3)
    teams = [
        {"team_id": 1, "team_name": "Mine", "roster": thin_rb},
        {"team_id": 2, "team_name": "Thin One", "roster": thin_rb},
        {"team_id": 3, "team_name": "Deep One", "roster": deep},
        {"team_id": 4, "team_name": "Deep Two", "roster": deep},
    ]
    pressure = compute_position_pressure(teams, settings, exclude_team_id="1")
    rb = pressure["RB"]
    assert rb["season"]["total_teams"] == 3
    assert rb["season"]["team_names"] == ["Thin One"]
    assert rb["season"]["ratio"] == 0.33
    assert rb["level"] == "medium"
    assert pressure["WR"]["season"]["teams_in_need"] == 0
    assert pressure["WR"]["level"] == "low"
    # No lineups given: the weekly signal is left empty, not guessed.
    assert rb["this_week"] == {"teams_in_need": 0, "team_names": []}


def test_an_injured_starter_with_no_healthy_cover_is_high_pressure_this_week():
    deep = _roster(QB=3, RB=8, WR=8, TE=3)
    teams = [{"team_id": 2, "team_name": "Hurt", "roster": deep}, {"team_id": 3, "team_name": "Fine", "roster": deep}]
    lineups = [
        {"team_id": 2, "lineup": [
            {"position": "TE", "slot_position": "TE", "injury_status": "OUT"},
            {"position": "WR", "slot_position": "BE", "injury_status": "ACTIVE"},
        ]},
        {"team_id": 3, "lineup": [
            {"position": "TE", "slot_position": "TE", "injury_status": "OUT"},
            {"position": "TE", "slot_position": "BE", "injury_status": "ACTIVE", "eligible_slots": ["TE"]},
        ]},
    ]
    pressure = compute_position_pressure(teams, None, exclude_team_id=None, week_lineups=lineups)
    assert pressure["TE"]["this_week"]["team_names"] == ["Hurt"]
    assert pressure["TE"]["level"] == "high"
    assert pressure["RB"]["this_week"]["teams_in_need"] == 0


# ---- custom league scoring ------------------------------------------------------

def _scoring(**over):
    """A LeagueScoring with the model's column defaults filled in (they only
    apply on insert), then any overrides."""
    cfg = LeagueScoring()
    for col in LeagueScoring.__table__.columns:
        default = col.default.arg if col.default is not None and not callable(col.default.arg) else None
        if getattr(cfg, col.name) is None and default is not None:
            setattr(cfg, col.name, default)
    for k, v in over.items():
        setattr(cfg, k, v)
    return cfg


def test_quarterback_points_use_the_league_settings():
    svc = ScoringCalculationService(db=None)
    stats = {"passing_stats": {"yards": 300, "touchdowns": 2, "interceptions": 1},
             "rushing_stats": {"yards": 20, "touchdowns": 0}}
    standard = svc.calculate_fantasy_points(stats, _scoring(), "QB")
    # 300/25 + 2*4 - 1 + 20/10
    assert standard["total_points"] == pytest.approx(21.0)
    six_point = svc.calculate_fantasy_points(stats, _scoring(passing_td_points=6.0, passing_300_yard_bonus=3.0), "QB")
    assert six_point["total_points"] == pytest.approx(28.0)
    assert six_point["points_breakdown"]["300_yard_bonus"] == 3.0


def test_reception_value_is_the_difference_between_ppr_and_standard():
    svc = ScoringCalculationService(db=None)
    stats = {"receiving_stats": {"yards": 80, "touchdowns": 1, "receptions": 7}, "fumbles_lost": 1}
    ppr = svc.calculate_fantasy_points(stats, _scoring(reception_points=1.0), "WR")["total_points"]
    half = svc.calculate_fantasy_points(stats, _scoring(reception_points=0.5), "WR")["total_points"]
    standard = svc.calculate_fantasy_points(stats, _scoring(reception_points=0.0), "WR")["total_points"]
    # 8 + 6 - 2 = 12 before receptions
    assert (standard, half, ppr) == (pytest.approx(12.0), pytest.approx(15.5), pytest.approx(19.0))


def test_defense_points_allowed_tiers():
    svc = ScoringCalculationService(db=None)
    base = {"sacks": 3, "interceptions": 1}
    shutout = svc.calculate_fantasy_points({"defensive_stats": {**base, "points_allowed": 0}}, _scoring(), "DEF")
    blowout = svc.calculate_fantasy_points({"defensive_stats": {**base, "points_allowed": 38}}, _scoring(), "DEF")
    # 3 sacks + 1 INT (2) = 5, then +10 for a shutout or -4 for 35+
    assert shutout["total_points"] == pytest.approx(15.0)
    assert blowout["total_points"] == pytest.approx(1.0)


# ---- snapshot cache (stale-while-revalidate) --------------------------------------

@pytest.fixture
def swr(test_db_session, monkeypatch):
    """serve_swr against the test DB with a counting fake builder (60s TTL)."""
    test_db_session.query(LeagueSnapshot).delete()
    test_db_session.commit()
    calls = {"n": 0, "fail": False}

    async def builder(user_league):
        if calls["fail"]:
            raise SnapshotBuildError("platform down")
        calls["n"] += 1
        return {"value": calls["n"]}

    monkeypatch.setitem(snapshot_cache._REGISTRY, "test_kind", (builder, 60))
    league = SimpleNamespace(id=9101)

    def serve(force=False):
        tasks = BackgroundTasks()
        result = asyncio.run(snapshot_cache.serve_swr(test_db_session, league, "test_kind", background_tasks=tasks, force=force))
        return result, tasks

    return SimpleNamespace(serve=serve, calls=calls, db=test_db_session, league=league)


def _age(swr, seconds):
    row = snapshot_cache._read(swr.db, swr.league.id, "test_kind")
    row.computed_at = snapshot_cache._now() - timedelta(seconds=seconds)
    swr.db.commit()


def test_cold_load_builds_then_serves_from_cache(swr):
    first, _ = swr.serve()
    assert first["value"] == 1 and first["_cache"]["source"] == "fresh" and first["_cache"]["stale"] is False
    second, tasks = swr.serve()
    assert second["value"] == 1 and second["_cache"]["source"] == "cache"
    assert swr.calls["n"] == 1 and tasks.tasks == []


def test_stale_snapshot_is_served_at_once_and_refreshed_in_the_background(swr):
    swr.serve()
    _age(swr, 600)
    result, tasks = swr.serve()
    assert result["value"] == 1
    assert result["_cache"]["stale"] is True and result["_cache"]["source"] == "cache-refreshing"
    assert result["_cache"]["age_seconds"] >= 600
    assert len(tasks.tasks) == 1
    assert swr.calls["n"] == 1  # nothing rebuilt in the request itself


def test_force_rebuilds_now(swr):
    swr.serve()
    forced, _ = swr.serve(force=True)
    assert forced["value"] == 2 and forced["_cache"]["source"] == "fresh"


def test_a_failed_rebuild_falls_back_to_the_old_snapshot(swr):
    swr.serve()
    swr.calls["fail"] = True
    result, _ = swr.serve(force=True)
    assert result["value"] == 1 and result["_cache"]["stale"] is True


def test_a_failed_cold_load_raises(swr):
    swr.calls["fail"] = True
    with pytest.raises(SnapshotBuildError):
        swr.serve()


def test_unknown_kind_is_rejected(swr):
    with pytest.raises(ValueError):
        asyncio.run(snapshot_cache.serve_swr(swr.db, swr.league, "nope", background_tasks=BackgroundTasks()))
