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


def test_board_rolls_to_next_week_once_this_weeks_games_have_started():
    # Monday 2026-11-09: MNF kicked off 01:15 UTC Tue; Thursday and Sunday are next week.
    games = [{"id": "mnf", "commence_time": "2026-11-10T01:15:00Z"},
             {"id": "tnf", "commence_time": "2026-11-13T01:15:00Z"},
             {"id": "sun", "commence_time": "2026-11-15T14:30:00Z"},
             {"id": "far", "commence_time": "2026-11-20T01:15:00Z"}]
    before = datetime(2026, 11, 9, 23, 0, tzinfo=timezone.utc)
    assert odds_service.upcoming_games(games, before) == ([games[0]], False)
    during = datetime(2026, 11, 10, 2, 0, tzinfo=timezone.utc)  # MNF under way
    got, rolled = odds_service.upcoming_games(games, during)
    assert rolled and [g["id"] for g in got] == ["tnf", "sun"]


def _fake_props_api(monkeypatch, cached_age_hours=None):
    """get_event_props with a fake cache and API: returns the list of markets requested."""
    from datetime import timedelta
    calls = []
    monkeypatch.setattr(odds_service.settings, "ODDS_API_KEY", "test")

    async def entry(key):
        return (cached_age_hours * 3600, {"cached": True}) if cached_age_hours is not None else None

    async def get(path, params, sport="x"):
        calls.append(params["markets"].split(","))
        return {"fresh": True}

    async def put(key, data):
        return None

    async def credits():
        return 19000

    monkeypatch.setattr(odds_service, "_cache_entry", entry)
    monkeypatch.setattr(odds_service, "_get", get)
    monkeypatch.setattr(odds_service, "_cache_put", put)
    monkeypatch.setattr(odds_service, "credits_remaining_async", credits)
    monkeypatch.setattr(odds_service, "_db_read", lambda key: None)
    return calls


def test_free_plan_fetches_five_markets_and_no_closing_line(monkeypatch):
    kickoff = datetime(2026, 11, 13, 1, 15, tzinfo=timezone.utc)
    one_hour_before = datetime(2026, 11, 13, 0, 15, tzinfo=timezone.utc)
    # Paid: a game fetched 20h ago gets its closing fetch, all 16 markets.
    monkeypatch.setattr(odds_service.settings, "ODDS_PLAN", "paid")
    calls = _fake_props_api(monkeypatch, cached_age_hours=20)
    asyncio.run(odds_service.get_event_props("g", kickoff.isoformat(), now=one_hour_before))
    assert len(calls) == 1 and len(calls[0]) == len(odds_service.PROP_MARKETS) == 16
    # Free: the same moment serves the 36h fetch, no closing fetch.
    monkeypatch.setattr(odds_service.settings, "ODDS_PLAN", "free")
    calls = _fake_props_api(monkeypatch, cached_age_hours=20)
    got = asyncio.run(odds_service.get_event_props("g", kickoff.isoformat(), now=one_hour_before))
    assert calls == [] and got == {"cached": True}
    # Free, never fetched: the 5 core markets only.
    calls = _fake_props_api(monkeypatch)
    asyncio.run(odds_service.get_event_props("g", kickoff.isoformat(), now=one_hour_before))
    assert calls == [list(odds_service.FREE_PROP_MARKETS)] and len(calls[0]) == 5
    assert odds_service.lines_ttl_seconds() == 24 * 3600


def test_paid_plan_is_the_default():
    from app.core.config import Settings
    assert Settings.model_fields["ODDS_PLAN"].default == "paid"
