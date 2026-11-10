"""Pasted Betr Picks board: parsing, merging and name matching."""
import pytest

from app.services import betr_board
from app.services.betting_service import _resolve_abbreviated_names

# Layout of text copied from picks.betr.app's NFL page (2026-11-09).
PASTE = """
$78
Popular
Passing Yds
Receiving Yds
J. Cook III
RB
@ MIN • Today, 8:15 PM
84.5
74.5
Rushing Yds
More
Less
T. Bass
K
@ MIN • Today, 8:15 PM
1.5
FG Made
More
Less
J. Jefferson
WR
vs BUF • Today, 8:15 PM
79.5
Receiving Yds
More
Less
T. Johnson
RB
@ MIN • Today, 8:15 PM
14.5
Receiving Yds
More
Less
T. Johnson
TE
vs WAS • Thu, 8:15 PM
4.5
Receiving Yds
More
Less
A. St. Brown
WR
vs NE • Sun, 9:30 AM
78.5
Receiving Yds
More
J. Jefferson
WR
vs BUF • Today, 8:15 PM
79.5
Receiving Yds
More
Less
2+ picks required
"""


def test_parse_reads_cards_discounts_and_sides():
    parsed = betr_board.parse_paste(PASTE)
    assert parsed["platform"] == "betr" and parsed["total"] == 7  # FG Made read but not priced
    by = {(l["player"], l["opponent"], l["market"]): l for l in parsed["lines"]}
    assert len(parsed["lines"]) == 5  # Jefferson pasted twice is kept once
    cook = by[("J. Cook III", "MIN", "player_rush_yds")]
    assert cook["line"] == 74.5 and cook["was_line"] == 84.5 and cook["odds_type"] == "discount"
    assert cook["allowed"] == ["over"] and cook["player_home"] is False
    jj = by[("J. Jefferson", "BUF", "player_reception_yds")]
    assert jj["odds_type"] == "standard" and jj["allowed"] == ["over", "under"] and jj["player_home"] is True
    assert by[("T. Johnson", "WSH", "player_reception_yds")]["line"] == 4.5  # WAS -> the board's WSH
    assert by[("A. St. Brown", "NE", "player_reception_yds")]["allowed"] == ["over"]  # no Less button


def test_parse_rejects_text_without_cards():
    with pytest.raises(betr_board.PasteError):
        betr_board.parse_paste("Home\nFeed\nSearch")


def test_merge_adds_tabs_and_replaces_same_player_stat():
    first = betr_board.parse_paste(PASTE)
    update = betr_board.parse_paste("J. Jefferson\nWR\nvs BUF • Today, 8:15 PM\n81.5\nReceiving Yds\nMore\nLess\n")
    merged = betr_board.merge({**first, "uploaded_at": "x"}, update)
    jj = [l for l in merged["lines"] if l["player"] == "J. Jefferson"]
    assert len(merged["lines"]) == 5 and [l["line"] for l in jj] == [81.5]
    # A PrizePicks upload isn't merged into: the paste replaces it.
    assert betr_board.merge({"lines": [{"player": "X"}], "platform": None}, update) == update


def _m(player, team, home, away, market):
    return ({"id": f"{away}@{home}"}, f"{away} @ {home}", team, home, away, player, market, {}, 1.0)


def test_abbreviated_names_resolve_by_initial_last_name_and_opponent():
    matched = [_m("Justin Jefferson", "MIN", "MIN", "BUF", "player_reception_yds"),
               _m("Ty Johnson", "BUF", "MIN", "BUF", "player_reception_yds"),
               _m("Theo Johnson", "NYG", "NYG", "WSH", "player_reception_yds"),
               _m("James Cook", "BUF", "MIN", "BUF", "player_rush_yds"),
               _m("Amon-Ra St. Brown", "DET", "DET", "NE", "player_reception_yds")]
    lines = betr_board.parse_paste(PASTE)["lines"]
    names = {(l["player"], l["market"]) for l in _resolve_abbreviated_names(lines, matched)}
    assert names == {("James Cook", "player_rush_yds"), ("Justin Jefferson", "player_reception_yds"),
                     ("Ty Johnson", "player_reception_yds"), ("Theo Johnson", "player_reception_yds"),
                     ("Amon-Ra St. Brown", "player_reception_yds")}


def test_ambiguous_name_stays_unresolved():
    matched = [_m("Tre Johnson", "BUF", "MIN", "BUF", "player_reception_yds"),
               _m("Ty Johnson", "BUF", "MIN", "BUF", "player_reception_yds")]
    line = {"player": "T. Johnson", "opponent": "MIN", "market": "player_reception_yds"}
    assert _resolve_abbreviated_names([line], matched)[0]["player"] == "T. Johnson"


def _leg(player, team, game, p=0.6):
    return {"player": player, "team": team, "game": game, "market": "player_reception_yds",
            "market_label": "Receiving Yds", "projection": 50.0,
            "prizepicks": {"side": "More", "line": 40.5, "p_win": p, "p_value": p, "market_prob": 0.55,
                           "espn_agrees": True}}


def test_betr_pairs_and_entries_use_one_pick_per_game():
    from app.services import betting_model as bm
    from app.services.betting_service import prizepicks_entries, prizepicks_pairs
    props = [_leg("A", "WSH", "WSH @ NYG"), _leg("B", "NYG", "WSH @ NYG"), _leg("C", "DET", "NE @ DET"),
             _leg("D", "BUF", "BUF @ MIN")]
    games = lambda pair: {l["game"] for l in pair["legs"]}
    assert any(len(games(p)) == 1 for p in prizepicks_pairs(props)["pairs"])  # PrizePicks: same-game pairs priced
    betr_pairs = prizepicks_pairs(props, distinct_games=True)["pairs"]
    assert betr_pairs and all(len(games(p)) == 2 for p in betr_pairs)
    legs = prizepicks_pairs(props)["legs"]
    entries = prizepicks_entries(legs, bm.BETR_PERFECT_PAYOUTS, bm.BETR_FLEX_PAYOUTS, distinct_games=True)
    assert entries and all(len({l["game"] for l in e["legs"]}) == e["size"] for e in entries)
    assert {(e["type"], e["size"]) for e in entries} <= {("power", 3), ("flex", 2)}  # only known Betr payouts


def test_screenshot_cards_become_the_same_lines_as_a_paste(monkeypatch):
    import asyncio
    from app.services import betr_screenshot

    read = {"notes": "", "cards": [
        {"player": "J. Cook III", "position": "RB", "matchup": "@ MIN", "line": 74.5, "was_line": 84.5,
         "stat": "Rushing Yds", "more_only": True},
        {"player": "J. Jefferson", "position": "WR", "matchup": "vs BUF", "line": 79.5, "was_line": None,
         "stat": "Receiving Yds", "more_only": False},
        {"player": "T. Johnson", "position": "TE", "matchup": "vs WAS", "line": 4.5, "was_line": None,
         "stat": "Receiving Yds", "more_only": False},
        {"player": "J. Allen", "position": "QB", "matchup": "@ MIN", "line": 130.5, "was_line": None,
         "stat": "Passing Yds", "more_only": True},
        {"player": "T. Bass", "position": "K", "matchup": "@ MIN", "line": 1.5, "was_line": None,
         "stat": "FG Made", "more_only": False},
        {"player": "X. Unknown", "position": "WR", "matchup": "Thu 8:15 PM", "line": 10.5, "was_line": None,
         "stat": "Receiving Yds", "more_only": False}]}

    async def fake_read(*a, **k):
        return read
    monkeypatch.setattr(betr_screenshot, "read_image_json", fake_read)
    got = asyncio.run(betr_screenshot.read_screenshots([(b"png", "image/png"), (b"png", "image/png")]))
    pasted = {(l["player"], l["opponent"], l["market"]): l for l in betr_board.parse_paste(PASTE)["lines"]}
    shot = {(l["player"], l["opponent"], l["market"]): l for l in got["lines"]}
    assert len(got["lines"]) == 4 and got["total"] == 12  # two images, deduped; FG Made unpriced
    for key in [("J. Cook III", "MIN", "player_rush_yds"), ("J. Jefferson", "BUF", "player_reception_yds"),
                ("T. Johnson", "WSH", "player_reception_yds")]:
        same = ("line", "was_line", "odds_type", "allowed", "player_home")
        assert {k: shot[key][k] for k in same} == {k: pasted[key][k] for k in same}
    assert shot[("J. Allen", "MIN", "player_pass_yds")]["allowed"] == ["over"]  # More-only card
    assert any("X. Unknown" in w for w in got["warnings"])
