"""Tests for Yahoo's trade path (league_value_model over real Yahoo rosters)
and the league-wide roster fetch it's built on."""
import asyncio
from unittest.mock import MagicMock

from app.models.user_league import PlatformType, UserLeague
from app.services import league_management_service as lms
from app.services.yahoo_service import yahoo_service


def _row(first, last, team, position, pts):
    return {"player": {"first_name": first, "last_name": last, "position": position, "team": team},
            "team": team, "stats": {"pts_std": pts}}


def _yp(name, team, position, slot):
    return {"player_key": name, "name": name, "team": team, "position": position, "selected_position": slot}


def _league():
    return UserLeague(user_id=1, platform=PlatformType.YAHOO, league_id="1", league_key="461.l.1",
                      team_id="1", season=2026, yahoo_access_token="tok")


def _patch(monkeypatch, rosters, rows):
    from unittest.mock import AsyncMock
    from app.services import league_value_data as lvd

    monkeypatch.setattr(lvd, "get_valid_yahoo_token", AsyncMock(return_value="tok"))
    monkeypatch.setattr(yahoo_service, "get_league_rosters", AsyncMock(return_value=rosters))
    monkeypatch.setattr(yahoo_service, "get_available_players", AsyncMock(return_value=[]))
    monkeypatch.setattr(yahoo_service, "get_league_settings", AsyncMock(return_value={
        "starters": {"RB": 1, "WR": 1}, "scoring_rules": None, "stat_values": {}, "trade_end_date": "2026-11-28"}))
    monkeypatch.setattr(yahoo_service, "get_league_info", AsyncMock(return_value={"current_week": "3"}))
    monkeypatch.setattr(lvd, "fetch_rest_of_season_projections", AsyncMock(return_value=rows))
    monkeypatch.setattr(lvd, "fetch_weekly_projections", AsyncMock(return_value=[]))
    monkeypatch.setattr(lvd, "_trending_by_name", AsyncMock(return_value={}))


def test_yahoo_trades_name_real_rostered_players(monkeypatch):
    rosters = [
        {"team_id": "1", "team_name": "Mine", "players": [
            _yp("My RB", "MIN", "RB", "RB"), _yp("My WR", "DAL", "WR", "WR"), _yp("My Bench WR", "DAL", "WR", "BN")]},
        {"team_id": "2", "team_name": "Theirs", "players": [
            _yp("Their RB", "SF", "RB", "RB"), _yp("Their WR", "SF", "WR", "WR"), _yp("Their Bench RB", "SF", "RB", "BN"),
            _yp("Unprojected Guy", "SF", "RB", "BN")]},
    ]
    rows = [
        _row("My", "RB", "MIN", "RB", 100.0), _row("My", "WR", "DAL", "WR", 250.0),
        _row("My Bench", "WR", "DAL", "WR", 220.0), _row("Their", "RB", "SF", "RB", 260.0),
        _row("Their", "WR", "SF", "WR", 90.0), _row("Their Bench", "RB", "SF", "RB", 210.0),
    ]
    _patch(monkeypatch, rosters, rows)

    out = asyncio.run(lms.LeagueManagementService(MagicMock())._get_trade_recommendations(_league()))

    assert out["trade_deadline"] == "2026-11-28"
    assert "improves both teams" in out["basis"]
    s = out["suggestions"][0]
    assert s["you_send"]["name"] == "My Bench WR"
    assert s["you_receive"]["name"] in ("Their RB", "Their Bench RB")
    assert s["my_gain"] > 0 and s["their_gain"] > 0
    names = {p["name"] for p in s["you_send_players"]} | {s["you_receive"]["name"]}
    assert "Unprojected Guy" not in names


def test_yahoo_trades_error_when_projections_unavailable(monkeypatch):
    _patch(monkeypatch, [{"team_id": "1", "team_name": "Mine", "players": []}], [])
    out = asyncio.run(lms.LeagueManagementService(MagicMock())._get_trade_recommendations(_league()))
    assert "error" in out and "projections" in out["error"].lower()


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
