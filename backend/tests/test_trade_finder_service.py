"""Tests for the real, roster-grounded trade finder."""
from app.services.trade_finder_service import find_trade_suggestions


def _p(name, pos, slot, proj, team="XX"):
    return {"name": name, "position": pos, "lineup_slot": slot, "projected_points": proj, "team": team}


def test_finds_a_real_two_way_upgrade_trade():
    my_team = {
        "team_id": 1,
        "team_name": "My Team",
        "roster": [
            _p("My Weak RB", "RB", "RB", 8.0),
            _p("My Surplus WR", "WR", "BE", 14.0),
        ],
    }
    other_team = {
        "team_id": 2,
        "team_name": "Rival Team",
        "roster": [
            _p("Their Weak WR", "WR", "WR", 7.0),
            _p("Their Bench RB", "RB", "BE", 15.0),
        ],
    }
    suggestions = find_trade_suggestions(my_team_id=1, teams=[my_team, other_team])
    assert len(suggestions) == 1
    s = suggestions[0]
    assert s["team_id"] == 2
    assert s["you_receive"]["name"] == "Their Bench RB"
    assert s["you_send"]["name"] == "My Surplus WR"


def test_no_suggestion_without_a_real_upgrade_margin():
    my_team = {
        "team_id": 1,
        "team_name": "My Team",
        "roster": [_p("My RB", "RB", "RB", 10.0), _p("My Bench WR", "WR", "BE", 10.0)],
    }
    other_team = {
        "team_id": 2,
        "team_name": "Rival",
        "roster": [_p("Their Bench RB", "RB", "BE", 10.2), _p("Their WR", "WR", "WR", 5.0)],
    }
    # Gap is under the upgrade margin -- no real upgrade, no suggestion.
    assert find_trade_suggestions(my_team_id=1, teams=[my_team, other_team]) == []


def test_skips_lopsided_trade_even_if_both_sides_show_an_upgrade():
    my_team = {
        "team_id": 1,
        "team_name": "My Team",
        "roster": [
            _p("My Weak RB", "RB", "RB", 5.0),
            _p("My Bench WR", "WR", "BE", 6.0),
        ],
    }
    other_team = {
        "team_id": 2,
        "team_name": "Rival",
        "roster": [
            # A massive real upgrade for me...
            _p("Their Star RB", "RB", "BE", 25.0),
            # ...but their real need is only barely addressed -- lopsided.
            _p("Their Weak WR", "WR", "WR", 4.5),
        ],
    }
    assert find_trade_suggestions(my_team_id=1, teams=[my_team, other_team]) == []


def test_unknown_my_team_id_returns_empty():
    assert find_trade_suggestions(my_team_id=99, teams=[{"team_id": 1, "roster": []}]) == []


def test_no_other_teams_returns_empty():
    my_team = {"team_id": 1, "team_name": "Me", "roster": [_p("QB1", "QB", "QB", 20.0)]}
    assert find_trade_suggestions(my_team_id=1, teams=[my_team]) == []


def test_caps_at_max_suggestions():
    my_team = {
        "team_id": 1,
        "team_name": "Me",
        "roster": [
            _p("My Weak RB", "RB", "RB", 8.0),
            _p("My Surplus WR", "WR", "BE", 14.0),
        ],
    }
    rivals = []
    for i in range(5):
        rivals.append(
            {
                "team_id": i + 2,
                "team_name": f"Rival {i}",
                "roster": [
                    _p(f"Their Weak WR {i}", "WR", "WR", 7.0),
                    _p(f"Their Bench RB {i}", "RB", "BE", 15.0),
                ],
            }
        )
    suggestions = find_trade_suggestions(my_team_id=1, teams=[my_team] + rivals, max_suggestions=2)
    assert len(suggestions) == 2
