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
