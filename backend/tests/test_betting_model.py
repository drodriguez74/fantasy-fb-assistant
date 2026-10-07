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
    assert bm.yards_cv("player_rush_yds", 12.0) > 1.5 * bm.yards_cv("player_rush_yds", 70.0)
    assert bm.yards_cv("player_rush_yds", 0.5) == bm.MAX_YARDS_CV


def test_joint_prob_copula():
    assert bm.joint_prob(0.6, 0.6, 0.0) == 0.36
    assert math.isclose(bm.joint_prob(0.5, 0.5, 0.5), 1 / 3, abs_tol=1e-4)  # closed form: 1/4 + asin(rho)/2pi
    assert bm.joint_prob(0.6, 0.6, 0.45) > 0.36 > bm.joint_prob(0.6, 0.6, -0.2)
    assert bm.leg_correlation("player_reception_yds", "player_pass_yds", True, True) == 0.38
    assert bm.leg_correlation("player_pass_yds", "player_reception_yds", False, False) == 0.0


def test_prizepicks_leg_uses_market_at_prizepicks_number():
    from app.services.betting_service import prizepicks_pairs
    offers = _offers(60.5, -110, -110)
    offers["prizepicks"] = 52.5  # well under the books' 60.5: More is the side
    rec = evaluate_player_prop("WR One", "player_reception_yds", offers, 60.0, "pp1")
    leg = rec["prizepicks"]
    assert leg["side"] == "More" and leg["book_line"] == 60.5
    assert leg["market_prob"] > 0.5 and leg["p_win"] > 0.5

    def prop(player, team, market, side, p):
        return {"player": player, "team": team, "game": "BUF @ KC", "market": market, "market_label": market,
                "projection": 1.0, "prizepicks": {"line": 1.5, "side": side, "p_win": p, "p_push": 0.0,
                                                    "model_prob": p, "market_prob": p, "book_line": 1.5}}
    props = [
        prop("QB", "KC", "player_pass_yds", "More", 0.6),
        prop("WR", "KC", "player_reception_yds", "More", 0.6),  # QB's teammate: PrizePicks won't allow the pair
        prop("OPP QB", "BUF", "player_pass_yds", "More", 0.6),
        prop("RB", "BUF", "player_rush_yds", "Less", 0.45),     # under 50%: not a leg
    ]
    out = prizepicks_pairs(props)
    teams = [{l["team"] for l in r["legs"]} for r in out["pairs"]]
    assert teams and all(len(t) == 2 for t in teams)            # never two players from one team
    assert all("RB" not in {l["player"] for l in r["legs"]} for r in out["pairs"])
    shootout = next(r for r in out["pairs"] if {l["player"] for l in r["legs"]} == {"QB", "OPP QB"})
    assert shootout["correlation"] == 0.08 and shootout["joint_prob"] > shootout["independent_prob"]


def test_slate_centering_removes_systematic_projection_bias():
    # Lines at the projected mean: right-skewed yardage puts the median below
    # the mean, so the uncentered model leans Under on every prop; the fitted
    # scale brings the median prop back to 50%.
    pairs = [(p, p + 0.5) for p in (30, 42, 55, 61, 70, 77, 85, 96, 104)]
    k = bm.fit_projection_scale("player_reception_yds", pairs)
    assert k > 1.0
    median_over = np.median([bm.prob_over(bm.simulate_stat("player_reception_yds", p * k, f"c{i}"), line)[0]
                             for i, (p, line) in enumerate(pairs)])
    assert abs(median_over - 0.5) < 0.03
    assert bm.fit_projection_scale("player_reception_yds", pairs[:3]) == 1.0  # too few props: untouched
    # Anytime TD: projections at half the market-implied scoring rate -> scale ~2.
    td = [(0.2, 1 - math.exp(-0.4))] * 10
    assert math.isclose(bm.fit_projection_scale("player_anytime_td", td), 1.6)  # clipped at the bound


def test_anytime_td_devig_uses_game_total():
    # 20 players at 30% each imply ~7.1 TDs; a 45-point total supports ~4.5.
    scale = bm.td_rate_scale([0.30] * 20, 45.0)
    assert 0.6 < scale < 0.7
    fair = bm.td_fair_prob(0.30, scale)
    assert 0.20 < fair < 0.23                      # a 30% price is really ~21%
    assert bm.td_rate_scale([0.30] * 5, 45.0) is None   # partial prop list: no game estimate
    assert bm.td_rate_scale([0.30] * 20, None) is None  # no total
    assert bm.td_fair_prob(0.30, None) < 0.30           # fallback still removes a hold


def test_espn_must_agree_before_units():
    # Sleeper above the line (not far enough to be an outlier): Over gets units on its own...
    rec = evaluate_player_prop("WR One", "player_reception_yds", _offers(60.5, +120, -140), 80.0, "x1")
    assert rec["side"] == "Over" and rec["units"] > 0 and "espn_agrees" not in rec
    # ...but not when ESPN projects him under the line.
    rec = evaluate_player_prop("WR One", "player_reception_yds", _offers(60.5, +120, -140), 80.0, "x1",
                               espn_projection=40.0)
    assert rec["espn_agrees"] is False and rec["units"] == 0.0
    assert rec["espn_projection"] == 40.0
    rec = evaluate_player_prop("WR One", "player_reception_yds", _offers(60.5, +120, -140), 80.0, "x1",
                               espn_projection=80.0)
    assert rec["espn_agrees"] is True and rec["units"] > 0


def test_prizepicks_pairs_skip_legs_espn_disagrees_with():
    from app.services.betting_service import prizepicks_pairs

    def prop(player, agrees):
        # One team per player: PrizePicks needs two different teams.
        return {"player": player, "team": player, "game": "BUF @ KC", "market": "player_rush_yds", "market_label": "",
                "projection": 1.0, "prizepicks": {"line": 1.5, "side": "More", "p_win": 0.6, "p_push": 0.0,
                                                    "model_prob": 0.6, "market_prob": 0.55, "book_line": 1.5,
                                                    "espn_prob": None, "espn_agrees": agrees}}
    out = prizepicks_pairs([prop("A", True), prop("B", None), prop("C", False)])
    assert [{l["player"] for l in r["legs"]} for r in out["pairs"]] == [{"A", "B"}]


def test_hit_count_distribution_and_entry_ev():
    dist = bm.hit_count_distribution([0.5, 0.5, 0.5])
    assert np.allclose(dist, [0.125, 0.375, 0.375, 0.125])
    # 3-pick Power at 6x with 55% legs is about break-even (0.55^3 * 6 = 0.998).
    assert abs(bm.entry_ev(bm.hit_count_distribution([0.55] * 3), {3: 6.0})) < 0.01
    # Positive same-game correlation raises P(all hit).
    corr = np.array([[1, 0.4, 0], [0.4, 1, 0], [0, 0, 1.0]])
    assert bm.hit_count_distribution([0.55] * 3, corr)[3] > 0.55 ** 3


def test_prizepicks_entries_respect_rules():
    from app.services.betting_service import prizepicks_entries

    def leg(player, team, game, p):
        return {"player": player, "team": team, "game": game, "market": "player_rush_yds", "market_label": "",
                "side": "More", "line": 50.5, "p_win": p}
    legs = [leg("A", "KC", "BUF @ KC", 0.6), leg("B", "KC", "BUF @ KC", 0.6), leg("C", "KC", "BUF @ KC", 0.6),
            leg("D", "BUF", "BUF @ KC", 0.55), leg("E", "SF", "SF @ SEA", 0.55)]
    entries = prizepicks_entries(legs)
    assert entries and {e["size"] for e in entries} <= {2, 3, 4, 5}
    for e in entries:
        assert len({l["team"] for l in e["legs"]}) >= 2
        assert len({l["player"] for l in e["legs"]}) == e["size"]


def test_worst_price_is_the_min_ev_cutoff():
    # 55% at even money: EV +10%. The cutoff price leaves exactly MIN_EV.
    cut = bm.worst_price(0.55)
    assert cut is not None and cut < 100
    assert bm.ev(0.55, cut) >= bm.MIN_EV - 1e-9
    assert bm.ev(0.55, cut - 1) < bm.MIN_EV + 0.002     # one cent worse is (about) at/below the bar
    assert bm.price_offer(0.55, 100)["min_price"] == cut
    assert bm.price_offer(0.50, -110)["min_price"] is None   # no bet, no cutoff


def test_calibration_knobs_default_to_current_behavior():
    # Empty overrides: same draws as the single global setting.
    assert bm.projection_error("player_reception_yds") == bm.PROJECTION_ERROR
    assert not bm.DUD_PROB
    rng = np.random.default_rng(0)
    x = rng.gamma(4.0, 15.0, 50_000)
    assert bm.apply_duds(x, np.full_like(x, 60.0), 0.0, rng) is x
    # With duds on, the mean is preserved and the low tail gets heavier.
    m = np.full_like(x, 60.0)
    y = bm.apply_duds(x, m, 0.08, np.random.default_rng(1))
    assert abs(y.mean() - x.mean()) / x.mean() < 0.02
    assert np.mean(y < 10) > np.mean(x < 10)


# --- 2026-10-07 model review (evidence: docs/guides/BETTING_GUIDE.md section 9) ---

def _spread_game(spreads):
    """One NFL game; spreads = [(book, DAL home spread, DAL price, TB price)]."""
    return {"id": "kn", "home_team": "Dallas Cowboys", "away_team": "Tampa Bay Buccaneers",
            "commence_time": "2026-10-09T00:15:00Z",
            "bookmakers": [{"key": k, "markets": [
                {"key": "spreads", "outcomes": [{"name": "Dallas Cowboys", "point": pt, "price": hp},
                                                {"name": "Tampa Bay Buccaneers", "point": -pt, "price": ap}]},
                {"key": "totals", "outcomes": [{"name": "Over", "point": 44.5, "price": -110},
                                               {"name": "Under", "point": 44.5, "price": -110}]}]}
                for k, pt, hp, ap in spreads]}


def test_key_numbers_price_the_half_point_around_3():
    p = bm.market_margin_pmf(-3.0)
    k = bm._MARGINS
    assert 0.07 < p[k == 3].sum() < 0.11              # real push rate at 3 is ~8-11%; a plain normal says 3%
    assert p[k > 2.5].sum() - p[k > 3.5].sum() > 0.07  # so -2.5 vs -3.5 is worth ~8 points of probability
    margin, _ = bm.simulate_game(-3.0, 44.0, "kn", key_numbers=True)
    assert 0.07 < float((margin == 3).mean()) < 0.11
    # Consensus DAL -3; one book hangs TB +3.5 at -110: the hook over 3 is a real edge.
    game = _spread_game([("draftkings", -3.0, -110, -110), ("fanduel", -3.0, -110, -110),
                         ("hardrockbet", -3.5, -110, -110)])
    spread = next(r for r in evaluate_game(game) if r["market"] == "spread")
    assert spread["book"] == "Hard Rock Bet" and spread["line"] == 3.5 and spread["units"] > 0


def test_nfl_game_model_has_no_weight():
    game = _spread_game([("draftkings", -7.0, -110, -110), ("fanduel", -7.0, -110, -110), ("hardrockbet", -7.0, -110, -110)])
    # A model that loves Dallas by 17 changes nothing: the price is the market's.
    for r in evaluate_game(game, {"margin": 17.0, "total": 60.0}):
        assert r["units"] == 0.0 and r["p_win"] == r["market_prob"]
        assert r["model_prob"] is not None  # still shown for reference


def test_cover_total_correlation_is_small():
    assert bm.COVER_TOTAL_RHO <= 0.05


def test_teammates_are_correlated_in_entries():
    from app.services.betting_service import prizepicks_entries

    def leg(player, team, market, side):
        return {"player": player, "team": team, "game": "BUF @ KC", "market": market, "side": side, "p_win": 0.55}
    other = {"player": "Far", "team": "SF", "game": "SF @ SEA", "market": "player_rush_yds", "side": "More", "p_win": 0.55}
    stack = [leg("QB", "KC", "player_pass_yds", "More"), leg("WR", "KC", "player_reception_yds", "More"), other]
    split = [leg("QB", "KC", "player_pass_yds", "More"), leg("WR", "KC", "player_reception_yds", "Less"), other]
    p_stack = next(e for e in prizepicks_entries(stack) if e["type"] == "power" and e["size"] == 3)["p_all"]
    p_split = next(e for e in prizepicks_entries(split) if e["type"] == "power" and e["size"] == 3)["p_all"]
    assert p_stack > 0.55 ** 3 + 0.02 and p_split < 0.55 ** 3 - 0.02


def test_espn_check_does_not_gate_passing_yards():
    from app.services.betting_service import _espn_check
    c = {"side": "Over", "line": 250.5, "market_prob": 0.5, "units": 1.0, "confidence": "lean"}
    espn_says_under = np.full(1000, 200.0)
    assert _espn_check(c, espn_says_under, "player_pass_yds")["units"] == 1.0
    assert _espn_check(c, espn_says_under, "player_reception_yds")["units"] == 0.0


def test_card_is_filled_to_three_picks():
    from app.services.betting_service import fill_card

    def rec(name, ev, units=0.0, **kw):
        return {"type": "player_prop", "player": name, "game": "G", "market": "player_rush_yds",
                "units": units, "confidence": "lean" if units else "none", "ev": ev, **kw}
    recs = [rec("Bet", 0.05, 1.0), rec("Watch", 0.01, watch=True), rec("Best", 0.02), rec("Neg", -0.02),
            rec("Stale", 0.30, projection_outlier=True)]
    assert fill_card(recs) == 2
    filled = {r["player"] for r in recs if r.get("card_fill")}
    assert filled == {"Watch", "Best"}  # watch list first, then EV; never a stale projection
    assert all(r["units"] == bm.FILL_UNITS and r["confidence"] == "fill" for r in recs if r.get("card_fill"))
    # A line already filled this week keeps its spot as prices move.
    recs = [rec("Watch", 0.01, watch=True), rec("Best", 0.02), rec("Neg", -0.02), rec("Kept", -0.05)]
    fill_card(recs, frozenset({("player_prop", "Kept", "player_rush_yds")}))
    assert {r["player"] for r in recs if r.get("card_fill")} == {"Kept", "Watch", "Best"}
    # Enough real bets: nothing is filled.
    assert fill_card([rec(f"B{i}", 0.05, 1.0) for i in range(3)]) == 0
