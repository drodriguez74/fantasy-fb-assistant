"""betting_tracking: grading rules, profit and calibration (pure parts)."""
from types import SimpleNamespace

from app.services.betting_tracking import _record, calibration, game_outcome, profit, prop_outcome


def test_prop_outcomes():
    assert prop_outcome("player_reception_yds", "Over", 80.5, 189) == "won"
    assert prop_outcome("player_reception_yds", "Under", 80.5, 189) == "lost"
    assert prop_outcome("player_receptions", "Over", 5.0, 5) == "push"
    assert prop_outcome("player_anytime_td", "Yes", None, 1) == "won"
    assert prop_outcome("player_anytime_td", "Yes", None, 0) == "lost"


def test_game_outcomes():
    # CLE 27, PIT 24 (home CLE).
    assert game_outcome("spread", "CLE", -2.5, "CLE", 27, 24) == ("won", 3)
    assert game_outcome("spread", "CLE", -3.0, "CLE", 27, 24) == ("push", 3)
    assert game_outcome("spread", "PIT", 2.5, "CLE", 27, 24) == ("lost", -3)
    assert game_outcome("total", "Over", 47.5, "CLE", 27, 24) == ("won", 51)
    assert game_outcome("total", "Under", 47.5, "CLE", 27, 24) == ("lost", 51)


def test_profit_in_units():
    assert profit("won", 2.0, 150) == 3.0
    assert profit("won", 1.0, -110) == round(100 / 110, 3)
    assert profit("lost", 1.5, -110) == -1.5
    assert profit("push", 1.0, -110) == 0.0 and profit("void", 1.0, -110) == 0.0


def _pick(status, p_win, units=1.0, price=-110, model=None, market=None, kind="player_prop"):
    return SimpleNamespace(status=status, p_win=p_win, units=units, price=price, kind=kind,
                           model_prob=model, market_prob=market,
                           profit_units=profit(status, units, price))


def test_record_counts_units_and_roi():
    picks = [_pick("won", 0.6), _pick("lost", 0.6), _pick("won", 0.6, units=2.0), _pick("void", 0.6), _pick("pending", 0.6)]
    r = _record(picks)
    assert (r["won"], r["lost"], r["void"], r["pending"]) == (2, 1, 1, 1)
    assert r["units_staked"] == 4.0
    assert r["units_profit"] == round(3 * 100 / 110 - 1, 2)
    assert r["win_rate"] == round(2 / 3, 4)


def test_calibration_buckets_and_brier():
    picks = [_pick("won", 0.62, model=0.7, market=0.55), _pick("lost", 0.64, model=0.7, market=0.55),
             _pick("won", 0.31, model=0.3, market=0.3), _pick("push", 0.5)]
    c = calibration(picks)
    assert c["lines"] == 3  # push excluded
    assert {b["range"]: (b["n"], b["actual"]) for b in c["buckets"]} == {"30-40%": (1, 1.0), "60-70%": (2, 0.5)}
    assert c["brier"]["blend"] is not None and c["brier"]["model"] is not None


def test_college_finals_match_by_full_team_name():
    from app.services.betting_tracking import _completed_scores
    from app.services.espn_game_predictor import cfb_team_key

    def team(name, side, score):
        return {"homeAway": side, "score": str(score), "team": {"displayName": name, "abbreviation": name[:4]}}
    data = {"events": [
        {"competitions": [{"status": {"type": {"completed": True}},
                           "competitors": [team("UTEP Miners", "home", 17), team("Nevada Wolf Pack", "away", 31)]}]},
        {"competitions": [{"status": {"type": {"completed": False}},
                           "competitors": [team("Memphis Tigers", "home", 7), team("UAB Blazers", "away", 3)]}]},
    ]}
    finals = _completed_scores(data, lambda t: cfb_team_key(t.get("displayName")))
    # The Odds API's spelling of the same teams finds the final; unfinished games are left out.
    assert finals[(cfb_team_key("UTEP Miners"), cfb_team_key("Nevada Wolf Pack"))] == (17.0, 31.0)
    assert len(finals) == 1
    # College spreads grade with full team names as the side (Nevada -8.5 won by 14).
    outcome, actual = game_outcome("spread", "Nevada Wolf Pack", -8.5, "UTEP Miners", 17, 31)
    assert outcome == "won" and actual == 14
