"""odds_service: Vegas lines -> implied team totals (pure parts)."""
import asyncio
from datetime import datetime, timezone

from app.services import odds_service
from app.services.odds_service import implied_totals, normalize_team, week_cutoff


def _book(key, home, home_spread, total):
    return {"key": key, "markets": [
        {"key": "spreads", "outcomes": [{"name": home, "point": home_spread}, {"name": "Other", "point": -home_spread}]},
        {"key": "totals", "outcomes": [{"name": "Over", "point": total}, {"name": "Under", "point": total}]},
    ]}


def _game(home, away, kickoff, books):
    return {"home_team": home, "away_team": away, "commence_time": kickoff, "bookmakers": books}


NOW = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)  # a Tuesday afternoon


def test_week_cutoff_is_the_next_tuesday_morning():
    assert week_cutoff(NOW) == datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc)
    # Early Tuesday (Monday night game still on): this week ends today.
    early = datetime(2026, 10, 13, 3, 0, tzinfo=timezone.utc)
    assert week_cutoff(early) == datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc)


def test_implied_totals_use_the_median_line_and_skip_next_week():
    games = [
        _game("Dallas Cowboys", "Tampa Bay Buccaneers", "2026-10-09T00:15:00Z", [
            _book("draftkings", "Dallas Cowboys", -8.5, 47.5),
            _book("fanduel", "Dallas Cowboys", -8.5, 47.5),
            _book("hardrockbet", "Dallas Cowboys", -8.0, 48.5),
        ]),
        _game("Kansas City Chiefs", "Denver Broncos", "2026-10-18T20:25:00Z", [
            _book("draftkings", "Kansas City Chiefs", -3.0, 45.0),
        ]),
    ]
    t = implied_totals(games, NOW)

    assert set(t) == {"DAL", "TB"}  # KC-DEN is next week
    assert t["DAL"]["implied_total"] == 28.0 and t["TB"]["implied_total"] == 19.5
    assert t["DAL"]["opponent"] == "TB" and t["TB"]["opponent_implied_total"] == 28.0
    assert t["TB"]["spread"] == 8.5 and t["DAL"]["home"] is True


def test_game_without_both_lines_is_left_out():
    g = _game("Dallas Cowboys", "Tampa Bay Buccaneers", "2026-10-09T00:15:00Z",
              [{"key": "draftkings", "markets": [{"key": "totals", "outcomes": [{"name": "Over", "point": 47.5}]}]}])
    assert implied_totals([g], NOW) == {}


def test_team_aliases_match_espn_abbreviations():
    assert normalize_team("Was") == "WSH"
    assert normalize_team("JAC") == "JAX"
    assert normalize_team(None) is None


def test_no_key_means_no_odds(monkeypatch):
    monkeypatch.setattr(odds_service.settings, "ODDS_API_KEY", None)
    assert asyncio.run(odds_service.get_implied_totals()) == {}
