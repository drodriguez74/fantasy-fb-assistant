"""Yahoo waiver parity: free-agent paging, per-player enrichment, drop
candidates on Yahoo's "BN" bench, and the waiver-competition snapshot."""
import asyncio
from unittest.mock import MagicMock

from app.models.user_league import PlatformType, UserLeague
from app.services import league_snapshots, yahoo_waiver_context
from app.services.waiver_wire_service import pick_drop_candidate
from app.services.yahoo_service import yahoo_service


def _fa(i):
    return {"player": [[{"player_key": f"k{i}"}, {"player_id": str(i)}, {"name": {"full": f"Player {i}"}},
                        {"primary_position": "WR"}, {"editorial_team_abbr": "Min"}],
                       {"percent_owned": [{"coverage_type": "week"}, {"value": i}, {"delta": "0"}]}]}


def test_available_players_pages_in_25s_with_ownership(monkeypatch):
    urls = []

    async def fake_get(url, headers=None, params=None):
        urls.append(url)
        start = int(url.split(";start=")[1].split(";")[0])
        page = {str(j): _fa(start + j) for j in range(25 if start < 50 else 3)}
        resp = MagicMock()
        resp.headers = {"content-type": "application/json"}
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"fantasy_content": {"league": [{"league_key": "l"}, {"players": {**page, "count": len(page)}}]}}
        return resp

    client = MagicMock()
    client.get = fake_get
    monkeypatch.setattr(type(yahoo_service), "client", property(lambda self: client))

    players = asyncio.run(yahoo_service.get_available_players("tok", "461.l.1", count=75))

    assert len(urls) == 3 and all(";status=A" in u and ";count=25" in u and "out=percent_owned" in u for u in urls)
    assert len(players) == 53
    assert players[7]["ownership_percentage"] == 7


def test_waiver_context_scores_free_agents_and_maps_byes(monkeypatch):
    async def rosters(tok, key):
        return [{"team_id": "1", "players": [
            {"team": "Min", "bye_week": 3}, {"team": "Dal", "bye_week": 10}]}]

    async def season(s):
        return [{"player": {"first_name": "Player", "last_name": "4", "position": "WR", "team": "MIN"},
                 "team": "MIN", "stats": {"pts_std": 100.0, "rec": 50.0}}]

    async def info(tok, key):
        return {"current_week": "3"}

    monkeypatch.setattr(yahoo_service, "get_league_rosters", rosters)
    monkeypatch.setattr(yahoo_service, "get_league_info", info)
    monkeypatch.setattr(yahoo_waiver_context, "fetch_season_projections", season)

    fas = [{"name": "Player 4", "team": "Min", "position": "WR", "ownership_percentage": 12}]
    rules = {"receiving": {"reception": 1.0}}
    enrichment, byes = asyncio.run(
        yahoo_waiver_context.build_yahoo_waiver_context("tok", "l", 2026, fas, {"scoring_rules": rules})
    )

    assert enrichment["player 4"] == {"ownership_percentage": 12, "season_projected_points": 150.0,
                                      "espn_player_id": None, "team": "MIN"}
    assert byes == {"MIN": True, "DAL": False}


def test_drop_candidate_reads_yahoo_bn_bench():
    roster = [
        {"name": "Starter", "position": "WR", "lineup_slot": "WR", "projected_points": 50},
        {"name": "Bench WR", "position": "WR", "lineup_slot": "BN", "projected_points": 80},
        {"name": "IR Guy", "position": "WR", "lineup_slot": "IR", "projected_points": 10},
    ]
    assert pick_drop_candidate(roster, "WR")["name"] == "Bench WR"


def test_yahoo_position_pressure_uses_league_rosters(monkeypatch):
    async def token(ul):
        return "tok"

    def players(*specs):
        return [{"position": pos, "selected_position": slot, "status": status, "bye_week": bye}
                for pos, slot, status, bye in specs]

    async def rosters(tok, key):
        return [
            {"team_id": "1", "team_name": "Mine", "players": players(("RB", "RB", None, 9))},
            # Starting RB on bye with no healthy bench RB -> acute RB need.
            {"team_id": "2", "team_name": "Thin", "players": players(("RB", "RB", None, 3), ("RB", "IR", "O", 7))},
            {"team_id": "3", "team_name": "Deep", "players": players(("RB", "RB", None, 9), ("RB", "BN", None, 9))},
        ]

    async def settings(tok, key):
        return {"starters": {"RB": 1}}

    async def info(tok, key):
        return {"current_week": "3"}

    monkeypatch.setattr(league_snapshots, "_require_yahoo_token", token)
    monkeypatch.setattr(yahoo_service, "get_league_rosters", rosters)
    monkeypatch.setattr(yahoo_service, "get_league_settings", settings)
    monkeypatch.setattr(yahoo_service, "get_league_info", info)

    ul = UserLeague(id=1, user_id=1, platform=PlatformType.YAHOO, league_id="1", league_key="461.l.1", team_id="1")
    out = asyncio.run(league_snapshots.build_position_pressure_snapshot(ul))

    assert out["supported"] is True and out["other_teams_considered"] == 2
    rb = out["position_pressure"]["RB"]
    assert rb["this_week"]["team_names"] == ["Thin"]
    assert rb["level"] == "high"
