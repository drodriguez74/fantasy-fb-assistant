"""Uploaded PrizePicks board: parsing and pricing (no network)."""
import pytest

from app.services import prizepicks_board as ppb
from app.services.betting_service import price_uploaded_board


def _proj(pid, player_id, stat, line, odds_type="standard", allowed="under_or_over", event="team"):
    return {"type": "projection", "id": pid,
            "attributes": {"league_ppid": "NFL", "stat_type": stat, "line_score": line, "odds_type": odds_type,
                           "event_type": event, "allowed_wager_types": allowed,
                           "start_time": "2026-10-11T13:00:00.000-04:00"},
            "relationships": {"new_player": {"data": {"type": "new_player", "id": player_id}}}}


RAW = {
    "data": [
        _proj("1", "p1", "Receiving Yards", 60.5),
        _proj("2", "p1", "Receiving Yards", 45.5, "goblin", "over"),  # PrizePicks' real shape: a string
        _proj("3", "p1", "Longest Reception", 20.5),           # stat we don't price
        _proj("4", "p2", "Pass Yards", 250.5, event="combo"),  # combo line
    ],
    "included": [
        {"type": "new_player", "id": "p1", "attributes": {"name": "WR One", "team": "KC"}},
        {"type": "new_player", "id": "p2", "attributes": {"name": "QB Two", "team": "KC"}},
    ],
}


def test_parse_board_keeps_priced_single_player_lines():
    parsed = ppb.parse_board(RAW)
    assert parsed["total"] == 4
    assert [l["allowed"] for l in parsed["lines"]] == [["over", "under"], ["over"]]
    assert [(l["player"], l["market"], l["line"], l["odds_type"]) for l in parsed["lines"]] == [
        ("WR One", "player_reception_yds", 60.5, "standard"),
        ("WR One", "player_reception_yds", 45.5, "goblin"),
    ]


def test_parse_board_rejects_captcha_page_and_non_nfl():
    with pytest.raises(ppb.BoardError):
        ppb.parse_board({"html": "Please enable JS"})
    with pytest.raises(ppb.BoardError):
        ppb.parse_board({"data": [], "included": []})


def test_price_uploaded_board_prices_goblins_on_allowed_side():
    offers = {"books": {"draftkings": {60.5: {"Over": -110, "Under": -110}}}, "prizepicks": None}
    game = {"id": "g1", "commence_time": "2026-10-11T17:00:00Z"}
    matched = [(game, "BUF @ KC", "KC", "KC", "BUF", "WR One", "player_reception_yds", offers, 62.0)]
    out = price_uploaded_board({"lines": ppb.parse_board(RAW)["lines"], "uploaded_at": "t"}, matched, 5,
                               {}, {}, {}, {})
    assert out["source"] == "upload" and out["lines_priced"] == 2 and out["lines_unmatched"] == 0
    goblin = out["goblins"][0]
    assert goblin["side"] == "More" and goblin["line"] == 45.5
    assert goblin["p_win"] > 0.6  # 15 yards under the books' 50% line (receiving yards are noisy)
    # The search list carries every priced line, standard and alternate.
    assert len(out["board_lines"]) == 2
    assert {r["odds_type"] for r in out["board_lines"]} == {"standard", "goblin"}
    assert all(r["player"] == "WR One" and r["side"] in ("More", "Less") for r in out["board_lines"])


def test_upload_endpoint_stores_board_and_rejects_captcha_page(monkeypatch):
    import json
    from fastapi.testclient import TestClient
    from app.api.deps import get_current_active_user
    from app.main import app

    saved = {}

    async def fake_save(parsed):
        saved.update(parsed)
        return {**parsed, "uploaded_at": "2026-10-07T00:00:00+00:00"}

    monkeypatch.setattr(ppb, "save", fake_save)  # never touch the real odds_cache
    app.dependency_overrides[get_current_active_user] = lambda: object()
    try:
        client = TestClient(app)
        ok = client.post("/api/v1/betting/prizepicks-board",
                         files={"file": ("prizepicks.json", json.dumps(RAW), "application/json")})
        assert ok.status_code == 200 and ok.json()["lines"] == 2 and len(saved["lines"]) == 2
        captcha = client.post("/api/v1/betting/prizepicks-board",
                              files={"file": ("p.json", "<html>Please enable JS</html>", "text/html")})
        assert captcha.status_code == 400
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)


def test_parse_board_detects_college_and_keeps_full_team_name():
    import copy
    raw = copy.deepcopy(RAW)
    for p in raw["data"]:
        p["attributes"]["league_ppid"] = "NCAAFB"  # PrizePicks' real college label
    raw["included"][0]["attributes"].update({"market": "Alabama", "team_name": "Crimson Tide", "team": "BAMA"})
    parsed = ppb.parse_board(raw)
    assert parsed["league"] == "NCAAFB" and parsed["lines"][0]["team_full"] == "Alabama Crimson Tide"
    for p in raw["data"]:
        p["attributes"]["league_ppid"] = "NBA"
    with pytest.raises(ppb.BoardError):
        ppb.parse_board(raw)


def test_market_leg_prices_off_book_line():
    from app.services.betting_service import _market_leg
    fair = {60.5: 0.5}
    easier = _market_leg(52.5, "player_reception_yds", fair, ["over", "under"], "s")
    assert easier["side"] == "More" and easier["p_win"] > 0.5 and easier["model_prob"] is None
    same = _market_leg(60.5, "player_reception_yds", fair, ["over"], "s")
    assert abs(same["p_win"] - 0.5) < 0.01


def test_spread_only_model_leaves_totals_market_only():
    from app.services.betting_service import evaluate_game
    game = {"id": "g", "home_team": "Home U", "away_team": "Away U", "commence_time": "2026-10-10T16:00:00Z",
            "bookmakers": [{"key": "draftkings", "markets": [
                {"key": "spreads", "outcomes": [{"name": "Home U", "point": -3.5, "price": -110},
                                                {"name": "Away U", "point": 3.5, "price": -110}]},
                {"key": "totals", "outcomes": [{"name": "Over", "point": 55.5, "price": -110},
                                               {"name": "Under", "point": 55.5, "price": -110}]}]}]}
    rows = {r["market"]: r for r in evaluate_game(game, {"margin": 10.0}, (15.5, 15.0), 0.15, 1.0)}
    assert rows["spread"]["model_prob"] is not None and rows["spread"]["units"] <= 1.0
    assert rows["total"]["model_prob"] is None and rows["total"]["model_line"] is None


def test_college_upload_refused_while_college_props_are_shelved(monkeypatch):
    import copy
    import json
    from fastapi.testclient import TestClient
    from app.api.deps import get_current_active_user
    from app.main import app
    from app.services import betting_service

    assert betting_service.CFB_PROPS_ENABLED is False
    saved = []

    async def fake_save(parsed):
        saved.append(parsed)
        return {**parsed, "uploaded_at": "t"}

    monkeypatch.setattr(ppb, "save", fake_save)
    raw = copy.deepcopy(RAW)
    for p in raw["data"]:
        p["attributes"]["league_ppid"] = "NCAAFB"
    app.dependency_overrides[get_current_active_user] = lambda: object()
    try:
        r = TestClient(app).post("/api/v1/betting/prizepicks-board",
                                 files={"file": ("cfb.json", json.dumps(raw), "application/json")})
        assert r.status_code == 400 and "shelved" in r.json()["detail"] and not saved
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)
