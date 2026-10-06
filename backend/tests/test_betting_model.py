"""betting_model math and betting_service pricing (no network)."""
import math

import numpy as np

from app.services import betting_model as bm
from app.services.betting_service import evaluate_game, evaluate_player_prop


def test_odds_conversion_and_devig():
    assert bm.american_to_decimal(-110) == 1 + 100 / 110
    assert bm.american_to_decimal(150) == 2.5
    over, under = bm.devig_pair(-110, -110)
    assert math.isclose(over, 0.5) and math.isclose(over + under, 1)
    over, _ = bm.devig_pair(-150, 130)
    assert 0.57 < over < 0.59  # 0.6 and 0.435 implied, normalized


def test_ev_and_kelly_units():
    assert math.isclose(bm.ev(0.5, -110), 0.5 * (100 / 110) - 0.5)
    assert bm.kelly_units(0.5, -110) == 0.0          # no edge at a fair coin flip
    assert bm.kelly_units(0.55, -110) == 1.0         # f=5.5%, quarter -> 1.4u, floor to 1.0
    assert bm.kelly_units(0.80, 100) == bm.MAX_UNITS  # capped
    assert bm.confidence_label(3.0) == "high" and bm.confidence_label(0.5) == "lean"


def test_simulation_is_reproducible_and_centered():
    a = bm.simulate_stat("player_reception_yds", 60.0, "seed")
    b = bm.simulate_stat("player_reception_yds", 60.0, "seed")
    assert np.array_equal(a, b)
    assert 55 < a.mean() < 65
    over, push = bm.prob_over(bm.simulate_stat("player_receptions", 5.0, "s"), 5.0)
    assert push > 0  # whole-number line on a count stat can push


def test_projection_outlier_bounds():
    assert bm.projection_outlier("player_rush_yds", 38.0, market_line=70.5)       # 46% off
    assert not bm.projection_outlier("player_rush_yds", 60.0, market_line=70.5)   # 15% off
    assert not bm.projection_outlier("player_rush_yds", 8.0, market_line=11.5)    # floor: 3.5/20
    assert bm.projection_outlier("player_anytime_td", 0.36, market_td_prob=0.14)  # 2.4x market rate
    assert not bm.projection_outlier("player_anytime_td", 0.45, market_td_prob=0.33)


def _offers(point, over, under, extra_books=()):
    books = {"draftkings": {point: {"Over": over, "Under": under}}}
    for name, pt, o, u in extra_books:
        books[name] = {pt: {"Over": o, "Under": u}}
    return {"books": books, "prizepicks": None}


def test_player_prop_needs_model_agreement_and_sane_projection():
    # Projection clearly above the line: over is the pick, model agrees.
    # (Not 72 vs 60.5: receiving yards are right-skewed, so a 72-yard mean
    # has a median near 59 and that line is fair -- the simulation knows.)
    rec = evaluate_player_prop("WR One", "player_reception_yds", _offers(60.5, -110, -110), 80.0, "t1")
    assert rec["side"] == "Over" and rec["model_prob"] > rec["market_prob"]
    assert not rec["projection_outlier"]

    # Projection far off the market: flagged, never sized.
    rec = evaluate_player_prop("WR Two", "player_reception_yds", _offers(60.5, -110, -110), 20.0, "t2")
    assert rec["projection_outlier"] and rec["units"] == 0.0


def test_game_edges_only_from_off_market_books():
    def book(key, home_spread, total, spread_price=-110):
        return {"key": key, "markets": [
            {"key": "spreads", "outcomes": [{"name": "Dallas Cowboys", "point": home_spread, "price": spread_price},
                                            {"name": "Tampa Bay Buccaneers", "point": -home_spread, "price": -110}]},
            {"key": "totals", "outcomes": [{"name": "Over", "point": total, "price": -110},
                                           {"name": "Under", "point": total, "price": -110}]},
        ]}
    game = {"id": "g1", "home_team": "Dallas Cowboys", "away_team": "Tampa Bay Buccaneers",
            "commence_time": "2026-10-09T00:15:00Z",
            "bookmakers": [book("draftkings", -7.0, 47.5), book("fanduel", -7.0, 47.5), book("hardrockbet", -7.0, 47.5)]}
    recs = evaluate_game(game)
    assert {r["market"] for r in recs} == {"spread", "total"}
    assert all(r["units"] == 0.0 for r in recs)  # everyone agrees at -110: no edge

    # One book hangs DAL -7 at +130 while consensus is -110: that's a real price edge.
    game["bookmakers"][2] = book("hardrockbet", -7.0, 47.5, spread_price=130)
    spread = next(r for r in evaluate_game(game) if r["market"] == "spread")
    assert spread["book"] == "Hard Rock Bet" and spread["units"] > 0


def test_board_rows_are_plain_json():
    import json
    rec = evaluate_player_prop("WR Three", "player_anytime_td",
                               {"books": {"draftkings": {None: {"Yes": 250.0}}}, "prizepicks": None}, 0.4, "t3")
    json.dumps(rec)  # numpy scalars would raise here (and 500 the API)
    assert isinstance(rec["projection_outlier"], bool)


def test_low_volume_yardage_is_noisier():
    assert bm.yards_cv("player_rush_yds", 12.0) > 2 * bm.yards_cv("player_rush_yds", 70.0)
    assert bm.yards_cv("player_rush_yds", 0.5) == bm.MAX_YARDS_CV
