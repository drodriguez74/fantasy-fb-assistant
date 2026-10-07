"""My entries: validation, PrizePicks grading rules and the engine snapshot (no network/DB)."""
import pytest

from app.services import betting_service as bs
from app.services import user_entries as ue


def _body(**kw):
    body = {"entry_type": "power", "stake": 10, "to_win": 30,
            "legs": [{"player": "Christian McCaffrey", "market": "player_reception_yds", "side": "Less", "line": 36.5},
                     {"player": "Bucky Irving", "market": "player_rush_yds", "side": "More", "line": 51.5}]}
    return {**body, **kw}


def test_validate():
    assert ue.validate(_body())["legs"][1]["side"] == "More"
    for bad in (_body(entry_type="parlay"), _body(to_win=5), _body(legs=_body()["legs"][:1]),
                _body(legs=[_body()["legs"][0], {**_body()["legs"][0], "market": "player_receptions"}])):
        with pytest.raises(ue.EntryError):
            ue.validate(bad)


def test_leg_outcomes():
    assert ue.leg_outcome("Less", 36.5, 20) == "won"
    assert ue.leg_outcome("More", 51.5, 40) == "lost"
    assert ue.leg_outcome("More", 6.0, 6) == "push"
    assert ue.leg_outcome("More", 6.0, None) == "void"   # didn't play


def test_power_and_flex_payouts():
    assert ue.entry_payout("power", 10, 30, ["won", "won"]) == ("won", 30.0)
    assert ue.entry_payout("power", 10, 30, ["won", "lost"]) == ("lost", 0.0)
    assert ue.entry_payout("power", 10, 30, ["won", "void"]) == ("refunded", 10)       # down to one pick
    assert ue.entry_payout("power", 10, 60, ["won", "won", "push"]) == ("won", 30.0)   # reverts to a 2-pick (3x)
    assert ue.entry_payout("flex", 10, 30, ["won", "won", "won"]) == ("won", 30.0)
    assert ue.entry_payout("flex", 10, 30, ["won", "won", "lost"]) == ("partial", 10.0)  # 2 of 3 pays 1x
    assert ue.entry_payout("flex", 10, 30, ["won", "lost", "lost"]) == ("lost", 0.0)


def test_snapshot_uses_the_engine_view():
    offers = {"books": {"draftkings": {60.5: {"Over": -110, "Under": -110}}}, "prizepicks": None}
    game = {"id": "g1", "commence_time": "2026-10-11T17:00:00Z"}
    bs._pricing_context["nfl"] = {"matched": [(game, "BUF @ KC", "KC", "KC", "BUF", "WR One", "player_reception_yds", offers, 62.0)],
                                  "week": 6, "scales": {}, "td_scales": {}, "espn_means": {}, "espn_scales": {}}
    try:
        snap = bs.snapshot_leg({"player": "WR One", "market": "player_reception_yds", "side": "More", "line": 52.5})
        assert snap["team"] == "KC" and snap["books_prob"] > 0.5 and snap["books_line"] == 60.5
        assert bs.snapshot_leg({"player": "Nobody", "market": "player_reception_yds", "side": "More", "line": 1}) is None
    finally:
        bs._pricing_context.clear()
