"""Show picks: validation, the board snapshot (which side our engine leans), grading and units (no network/DB)."""
import pytest

from app.services import analyst_picks as ap
from app.services import user_entries as ue

BOARD = {
    "generated_at": "2026-10-08T23:02:00Z",
    "player_props": [
        {"player": "Tyler Warren", "market": "player_reception_yds", "side": "Under", "line": 51.5, "price": -120,
         "p_win": 0.562, "p_push": 0.0, "market_prob": 0.5051, "ev": 0.031, "units": 0.0, "game": "IND @ PIT"},
        {"player": "George Pickens", "market": "player_reception_yds", "side": "Over", "line": 62.5, "price": -115,
         "p_win": 0.5075, "p_push": 0.0, "market_prob": 0.5, "ev": -0.051, "units": 0.0, "game": "TB @ DAL"},
        {"player": "George Pickens", "market": "player_anytime_td", "side": "Yes", "line": None, "price": 110,
         "p_win": 0.3119, "p_push": 0.0, "market_prob": 0.3371, "ev": -0.345, "units": 0.0, "game": "TB @ DAL"},
    ],
    "game_props": [
        {"market": "spread", "side": "IND", "line": 2.5, "price": -105, "p_win": 0.4958, "p_push": 0.0,
         "market_prob": 0.4958, "ev": -0.032, "units": 0.0, "home": "PIT", "away": "IND", "game": "IND @ PIT"},
        {"market": "total", "side": "Under", "line": 48.5, "price": -110, "p_win": 0.5034, "p_push": 0.0,
         "market_prob": 0.5034, "ev": -0.039, "units": 0.0, "home": "DAL", "away": "TB", "game": "TB @ DAL"},
    ],
}


def _pick(**kw):
    return ap.validate({"analyst": "Tom Brawley", "player": "Tyler Warren", "market": "player_reception_yds",
                        "side": "Less", "line": 51.5, **kw})


def test_validate():
    assert _pick()["conviction"] == "bet" and _pick()["line_stated"] is True
    assert _pick(player="PIT", market="team_spread", side="More", line=2.5)["team"] == "PIT"
    for bad in ({"market": "parlay"}, {"side": "Over"}, {"conviction": "lock"}, {"analyst": ""}):
        with pytest.raises(ap.PickError):
            _pick(**bad)


def test_snapshot_same_side_as_our_lean():
    snap = ap.board_snapshot(_pick(), BOARD)
    assert snap["agrees"] is True and snap["our_prob"] == 0.562 and snap["ev"] == 0.031
    assert snap["board_line"] == "Under 51.5" and snap["line_value"] == 0


def test_snapshot_agrees_means_our_chance_beats_the_books():
    # The board shows Pickens' TD on Yes, but we give it less than the books do.
    td = ap.board_snapshot(_pick(side="More", line=0.5, player="George Pickens", market="player_anytime_td"), BOARD)
    assert td["agrees"] is False and td["line_value"] is None
    over = ap.board_snapshot(_pick(side="More"), BOARD)
    assert over["agrees"] is False and over["our_prob"] == pytest.approx(0.438) and over["ev"] is None


def test_snapshot_line_value_and_far_alt_lines():
    near = ap.board_snapshot(_pick(player="George Pickens", side="More", line=61.5), BOARD)
    assert near["line_value"] == 1.0 and near["our_prob"] == 0.5075  # got 61.5; the board has 62.5
    alt = ap.board_snapshot(_pick(player="George Pickens", side="More", line=89.5), BOARD)
    assert alt["far_line"] is True and alt["our_prob"] is None and alt["agrees"] is None


def test_snapshot_spreads_and_totals():
    # Game lines are market-only: our chance is the books', so no lean either way.
    pit = ap.board_snapshot(_pick(player="PIT", market="team_spread", side="More", line=1.5), BOARD)
    assert pit["agrees"] is None and pit["board_line"] == "IND +2.5"
    assert pit["our_prob"] == pytest.approx(1 - 0.4958, abs=1e-4)
    assert pit["line_value"] == 1.0  # PIT -1.5 taken; the board has -2.5 now
    ind = ap.board_snapshot(_pick(player="IND", market="team_spread", side="More", line=-3.5), BOARD)
    assert ind["our_prob"] == 0.4958 and ind["line_value"] == 1.0  # took +3.5; only +2.5 now: beat the move
    over = ap.board_snapshot(_pick(player="TB @ DAL", team="DAL", market="game_total", side="More", line=48.5), BOARD)
    assert over["agrees"] is None and over["books_prob"] == pytest.approx(0.4966, abs=1e-4)
    assert ap.board_snapshot(_pick(player="Nobody"), BOARD) is None


def test_grading_reuses_my_entries_rules():
    pit = _pick(player="PIT", market="team_spread", side="More", line=2.5)
    over = _pick(player="TB @ DAL", team="DAL", market="game_total", side="More", line=48.5)
    warren = _pick()
    legs = [{**p, "status": "pending", "actual": None} for p in (pit, over, warren)]
    finals = {("PIT", "IND"): (24, 20), ("DAL", "TB"): (27, 17)}
    stats = {("tyler warren", "IND"): {"gp": 1, "rec_yd": 38}}
    out = ue.grade_legs(legs, stats, finals, week_over=False)
    assert [l["status"] for l in out] == ["won", "lost", "won"]  # PIT by 4 covers 2.5; 44 < 48.5; 38 < 51.5


def test_units_and_record():
    assert ap.units_won("won", None) == pytest.approx(0.9091, abs=1e-4)  # -110 assumed
    assert ap.units_won("won", 268) == 2.68
    assert ap.units_won("lost", -113) == -1.0 and ap.units_won("push", -110) == 0.0
    rec = ap._record([{"status": "won", "price": None}, {"status": "lost", "price": None},
                      {"status": "pending", "price": None}, {"status": "void", "price": None}])
    assert (rec["won"], rec["lost"], rec["pending"], rec["push"], rec["hit_rate"]) == (1, 1, 1, 1, 0.5)
    assert rec["units"] == pytest.approx(-0.09, abs=1e-2)


CFB_BOARD = {"game_props": [
    {"market": "spread", "side": "UCLA Bruins", "line": 12.5, "price": -110, "p_win": 0.5269, "p_push": 0.0,
     "market_prob": 0.5269, "ev": 0.0058, "units": 0.0, "home": "Oregon Ducks", "away": "UCLA Bruins",
     "game": "UCLA Bruins @ Oregon Ducks", "kickoff": "2026-10-10T19:30:00Z"},
    {"market": "spread", "side": "Alabama Crimson Tide", "line": -1.5, "price": -110, "p_win": 0.5037, "p_push": 0.0,
     "market_prob": 0.5037, "ev": -0.0385, "units": 0.0, "home": "Alabama Crimson Tide", "away": "Georgia Bulldogs",
     "game": "Georgia Bulldogs @ Alabama Crimson Tide", "kickoff": "2026-10-10T23:30:00Z"},
]}


def test_college_picks_match_full_names_and_moneylines_get_a_kickoff():
    ucla = ap.board_snapshot(ap.validate({"analyst": "Emory Hunt", "player": "UCLA Bruins", "market": "team_spread",
                                          "side": "More", "line": -11.5}, "cfb"), CFB_BOARD, "cfb")
    assert ucla["board_line"] == "UCLA Bruins +12.5" and ucla["line_value"] == -1.0  # took +11.5; +12.5 now
    uga = ap.board_snapshot(ap.validate({"analyst": "Emory Hunt", "player": "Georgia Bulldogs", "market": "team_win",
                                         "side": "More", "line": 0.5}, "cfb"), CFB_BOARD, "cfb")
    assert uga["kickoff"] == "2026-10-10T23:30:00Z" and uga["our_prob"] is None and uga["agrees"] is None


def test_college_grading_keys():
    from app.services.espn_game_predictor import cfb_team_key
    from app.models.analyst_pick import AnalystPick
    r = AnalystPick(sport="cfb", player="UCLA Bruins", team="UCLA Bruins", market="team_spread", side="More",
                    line=-11.5, status="pending")
    leg = ap._leg(r)
    finals = {(cfb_team_key("Oregon Ducks"), cfb_team_key("UCLA Bruins")): (31, 24)}
    assert ue.grade_legs([leg], {}, finals, week_over=False)[0]["status"] == "won"  # lost by 7 < 11.5
