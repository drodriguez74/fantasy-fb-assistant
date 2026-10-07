"""My entries screenshot import: input checks, provider fallback and warnings (providers mocked, no network)."""
import pytest

from app.services import entry_screenshot as es

READ = {"entry_type": "power", "stake": 10, "to_win": 30, "notes": "",
        "picks": [{"player": "Christian McCaffrey", "team": "SF", "market": "player_reception_yds",
                   "stat_label": "Receiving Yards", "side": "Less", "line": 36.5, "pick_type": "standard"},
                  {"player": "Bucky Irving", "team": "TB", "market": "player_rush_yds",
                   "stat_label": "Rush Yards", "side": "More", "line": 51.5, "pick_type": "standard"}]}


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    monkeypatch.setattr(es.settings, "OPENAI_API_KEY", "test", raising=False)
    monkeypatch.setattr(es.settings, "ANTHROPIC_API_KEY", "test", raising=False)


def _provider(result):
    async def call(b64, media_type):
        if isinstance(result, Exception):
            raise result
        return result
    return call


@pytest.mark.asyncio
async def test_rejects_bad_input():
    with pytest.raises(es.ScreenshotError):
        await es.read_screenshot(b"x", "image/heic")
    with pytest.raises(es.ScreenshotError):
        await es.read_screenshot(b"x" * (es.MAX_BYTES + 1), "image/png")


@pytest.mark.asyncio
async def test_clean_read_has_no_warnings(monkeypatch):
    monkeypatch.setattr(es, "_read_openai", _provider(READ))
    out = await es.read_screenshot(b"img", "image/png")
    assert out["to_win"] == 30 and out["picks"][0]["side"] == "Less" and out["warnings"] == []


@pytest.mark.asyncio
async def test_falls_back_to_claude(monkeypatch):
    monkeypatch.setattr(es, "_read_openai", _provider(RuntimeError("quota")))
    monkeypatch.setattr(es, "_read_anthropic", _provider(READ))
    assert (await es.read_screenshot(b"img", "image/png"))["stake"] == 10


@pytest.mark.asyncio
async def test_both_fail_or_no_picks(monkeypatch):
    monkeypatch.setattr(es, "_read_openai", _provider(RuntimeError("quota")))
    monkeypatch.setattr(es, "_read_anthropic", _provider(RuntimeError("credits")))
    with pytest.raises(es.ScreenshotError):
        await es.read_screenshot(b"img", "image/png")
    monkeypatch.setattr(es, "_read_openai", _provider({**READ, "picks": []}))
    with pytest.raises(es.ScreenshotError):
        await es.read_screenshot(b"img", "image/png")


def test_warnings_flag_unknown_stats_and_goblins():
    picks = [{**READ["picks"][0], "market": "other", "stat_label": "Fantasy Score"},
             {**READ["picks"][1], "pick_type": "goblin"}]
    w = es._warnings({**READ, "picks": picks, "notes": "Fee was cut off."})
    assert w[0] == "Fee was cut off."
    assert any("Fantasy Score" in x for x in w) and any("goblin" in x for x in w)
