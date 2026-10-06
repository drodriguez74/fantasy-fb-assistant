"""league_advice_service helpers that shape the waiver API response."""
from app.services.league_advice_service import _my_defense


def test_my_defense_prefers_the_starting_defense():
    roster = [
        {"name": "Chiefs", "position": "DEF", "team": "kc", "slot": "BN"},
        {"name": "Eagles D/ST", "position": "D/ST", "team": "PHI", "slot": "D/ST"},
        {"name": "Some WR", "position": "WR", "team": "DAL", "slot": "WR"},
    ]
    assert _my_defense(roster) == "PHI"


def test_my_defense_none_without_one():
    assert _my_defense([{"name": "Some WR", "position": "WR", "team": "DAL", "slot": "WR"}]) is None
