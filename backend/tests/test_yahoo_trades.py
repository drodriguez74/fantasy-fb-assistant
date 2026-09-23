"""Tests for Yahoo's real trade suggestions (was AI-invented) and the
league-wide roster fetch they're built on."""
import asyncio
from unittest.mock import MagicMock

from app.models.user_league import PlatformType, UserLeague
from app.services import league_management_service as lms
from app.services.trade_finder_service import find_trade_suggestions
from app.services.yahoo_service import yahoo_service


def _row(first, last, team, position, pts):
    return {"player": {"first_name": first, "last_name": last, "position": position, "team": team},
            "team": team, "stats": {"pts_std": pts}}


def _yp(name, team, position, slot):
    return {"name": name, "team": team, "position": position, "selected_position": slot}


def _league():
    return UserLeague(user_id=1, platform=PlatformType.YAHOO, league_id="1", league_key="461.l.1",
                      team_id="1", season=2026, yahoo_access_token="tok")


def _patch(monkeypatch, rosters, rows):
    async def token(self, league):
        return "tok"

    async def get_rosters(tok, key):
        return rosters

    async def get_settings(tok, key):
        return {"scoring_rules": None, "stat_values": {}, "trade_end_date": "2026-11-28"}

    async def season(season):
        return rows

    monkeypatch.setattr(lms.LeagueManagementService, "_get_yahoo_token", token)
    monkeypatch.setattr(yahoo_service, "get_league_rosters", get_rosters)
    monkeypatch.setattr(yahoo_service, "get_league_settings", get_settings)
    monkeypatch.setattr(lms, "fetch_season_projections", season)


def test_yahoo_trades_name_real_rostered_players(monkeypatch):
    rosters = [
        {"team_id": "1", "team_name": "Mine", "players": [
            _yp("My RB", "MIN", "RB", "RB"), _yp("My Bench WR", "DAL", "WR", "BN"),
            _yp("My WR", "DAL", "WR", "WR")]},
        {"team_id": "2", "team_name": "Theirs", "players": [
            _yp("Their Bench RB", "SF", "RB", "BN"), _yp("Their WR", "SF", "WR", "WR"),
            _yp("Their RB", "SF", "RB", "RB"), _yp("Unprojected Guy", "SF", "RB", "BN")]},
    ]
    rows = [
        _row("My", "RB", "MIN", "RB", 100.0), _row("My Bench", "WR", "DAL", "WR", 190.0),
        _row("My", "WR", "DAL", "WR", 200.0), _row("Their Bench", "RB", "SF", "RB", 180.0),
        _row("Their", "WR", "SF", "WR", 120.0), _row("Their", "RB", "SF", "RB", 150.0),
    ]
    _patch(monkeypatch, rosters, rows)

    out = asyncio.run(lms.LeagueManagementService(MagicMock())._get_trade_recommendations(_league()))

    assert out["trade_deadline"] == "2026-11-28"
    assert "not AI-generated" in out["basis"]
    [s] = out["suggestions"]
    assert s["you_receive"]["name"] == "Their Bench RB"
    assert s["you_send"]["name"] == "My Bench WR"


def test_yahoo_trades_error_when_projections_unavailable(monkeypatch):
    _patch(monkeypatch, [{"team_id": "1", "team_name": "Mine", "players": []}], [])
    out = asyncio.run(lms.LeagueManagementService(MagicMock())._get_trade_recommendations(_league()))
    assert "error" in out and "projections" in out["error"]


def test_trade_finder_treats_yahoo_bn_as_bench():
    teams = [
        {"team_id": "1", "team_name": "Mine", "roster": [
            {"name": "A", "position": "RB", "lineup_slot": "RB", "projected_points": 100},
            {"name": "B", "position": "WR", "lineup_slot": "BN", "projected_points": 190}]},
        {"team_id": "2", "team_name": "Theirs", "roster": [
            {"name": "C", "position": "RB", "lineup_slot": "BN", "projected_points": 180},
            {"name": "D", "position": "WR", "lineup_slot": "WR", "projected_points": 120}]},
    ]
    [s] = find_trade_suggestions("1", teams)
    assert (s["you_send"]["name"], s["you_receive"]["name"]) == ("B", "C")


def test_get_league_rosters_parses_every_team(monkeypatch):
    def player(name, pos, slot):
        return {"player": [[{"player_key": "k"}, {"name": {"full": name}}, {"primary_position": pos},
                            {"editorial_team_abbr": "Buf"}], {"selected_position": [{"week": "3"}, {"position": slot}]}]}

    def team(tid, name, players):
        return {"team": [[{"team_key": f"461.l.1.t.{tid}"}, {"team_id": tid}, {"name": name}],
                         {"roster": {"coverage_type": "week", "0": {"players": {
                             **{str(i): p for i, p in enumerate(players)}, "count": len(players)}}}}]}

    payload = {"fantasy_content": {"league": [{"league_key": "461.l.1"}, {"teams": {
        "0": team("1", "Mine", [player("Josh Allen", "QB", "QB")]),
        "1": team("2", "Theirs", [player("Bench Guy", "WR", "BN")]),
        "count": 2}}]}}

    response = MagicMock()
    response.json.return_value = payload
    response.headers = {"content-type": "application/json"}
    response.raise_for_status.return_value = None

    async def fake_get(*a, **kw):
        return response

    client = MagicMock()
    client.get = fake_get
    monkeypatch.setattr(type(yahoo_service), "client", property(lambda self: client))

    teams = asyncio.run(yahoo_service.get_league_rosters("tok", "461.l.1"))
    assert [(t["team_id"], t["team_name"]) for t in teams] == [("1", "Mine"), ("2", "Theirs")]
    assert teams[0]["players"][0]["name"] == "Josh Allen"
    assert teams[1]["players"][0]["selected_position"] == "BN"
