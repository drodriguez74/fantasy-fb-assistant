"""Tests for the deterministic lineup optimizer behind the This Week screen."""
from app.services.this_week_service import optimize_lineup, start_sit_confidence, _slot_accepts


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
        "injury_status": kw.get("injury_status", "ACTIVE"),
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


def test_swap_confidence_downgraded_by_replacement_injury_status():
    lineup = [
        _p("Starter WR", "WR", "WR", 9.0),
        _p("Questionable Bench WR", "BE", "WR", 20.0, injury_status="QUESTIONABLE"),
    ]
    result = optimize_lineup(lineup)
    assert len(result["swaps"]) == 1
    # Big point gap, but the replacement is a real injury risk -- confidence
    # must reflect that, not just the raw delta.
    assert result["swaps"][0]["confidence"] == "risky"


def test_swap_confidence_tiers_by_delta_when_healthy():
    lineup = [
        _p("Starter WR", "WR", "WR", 9.0),
        _p("Bench WR", "BE", "WR", 15.5),
    ]
    result = optimize_lineup(lineup)
    assert result["swaps"][0]["confidence"] == "strong"

    lineup2 = [
        _p("Starter WR", "WR", "WR", 9.0),
        _p("Bench WR", "BE", "WR", 11.5),
    ]
    result2 = optimize_lineup(lineup2)
    assert result2["swaps"][0]["confidence"] == "moderate"

    lineup3 = [
        _p("Starter WR", "WR", "WR", 9.0),
        _p("Bench WR", "BE", "WR", 9.8),
    ]
    result3 = optimize_lineup(lineup3)
    assert result3["swaps"][0]["confidence"] == "lean"


def test_start_sit_confidence_locked_with_no_bench_alternative():
    lineup = [_p("QB1", "QB", "QB", 21.0)]
    calls = start_sit_confidence(lineup)
    assert calls == [
        {
            "name": "QB1",
            "position": "QB",
            "slot": "QB",
            "tier": "locked",
            "margin": None,
            "best_bench_alternative": None,
        }
    ]


def test_start_sit_confidence_comfortable_vs_toss_up():
    lineup = [
        _p("Comfy RB", "RB", "RB", 18.0),
        _p("Bench RB1", "BE", "RB", 4.0),
        _p("Thin RB", "RB", "RB", 10.0),
        _p("Bench RB2", "BE", "RB", 9.6),
    ]
    calls = {c["name"]: c for c in start_sit_confidence(lineup)}
    assert calls["Comfy RB"]["tier"] == "comfortable"
    assert calls["Thin RB"]["tier"] == "toss_up"
    assert calls["Thin RB"]["best_bench_alternative"] == "Bench RB2"


def test_start_sit_confidence_risky_overrides_margin():
    lineup = [
        _p("Hurt WR", "WR", "WR", 18.0, injury_status="DOUBTFUL"),
        _p("Bench WR", "BE", "WR", 5.0),
    ]
    calls = start_sit_confidence(lineup)
    assert calls[0]["tier"] == "risky"
