"""Tests for the deterministic lineup optimizer behind the This Week screen."""
from app.services.this_week_service import optimize_lineup, _slot_accepts


def _p(name, slot, pos, proj, **kw):
    base = {
        "name": name,
        "slot_position": slot,
        "position": pos,
        "projected_points": proj,
        "eligible_slots": kw.get("eligible_slots", [pos]),
        "game_played": kw.get("game_played", 0),
        "on_bye": kw.get("on_bye", False),
        "team": kw.get("team", "XX"),
    }
    return base


def test_suggests_higher_projected_bench_player_into_flex():
    lineup = [
        _p("Starter WR", "RB/WR/TE", "WR", 9.0, eligible_slots=["WR", "RB/WR/TE"]),
        _p("Bench WR", "BE", "WR", 15.4, eligible_slots=["WR", "RB/WR/TE"]),
        _p("QB", "QB", "QB", 21.0),
    ]
    result = optimize_lineup(lineup)
    assert result["points_gained"] == 6.4
    assert len(result["swaps"]) == 1
    swap = result["swaps"][0]
    assert swap["bench_out"]["name"] == "Starter WR"
    assert swap["start_in"]["name"] == "Bench WR"
    assert result["optimized_projected"] > result["current_projected"]


def test_no_swap_when_bench_is_worse():
    lineup = [
        _p("Starter RB", "RB", "RB", 14.0),
        _p("Bench RB", "BE", "RB", 6.2),
    ]
    result = optimize_lineup(lineup)
    assert result["swaps"] == []
    assert result["points_gained"] == 0.0
    assert result["current_projected"] == 14.0


def test_ignores_bench_player_on_bye_or_already_played():
    lineup = [
        _p("Starter WR", "WR", "WR", 8.0),
        _p("Bye WR", "BE", "WR", 20.0, on_bye=True),
        _p("Done WR", "BE", "WR", 20.0, game_played=100),
    ]
    assert optimize_lineup(lineup)["swaps"] == []


def test_slot_eligibility_rules():
    rb = _p("rb", "BE", "RB", 5)
    assert _slot_accepts("RB/WR/TE", rb) is True
    assert _slot_accepts("QB", rb) is False
    assert _slot_accepts("RB", rb) is True
