"""The user's uploaded PrizePicks NFL board.

PrizePicks serves its full board (standard, goblin and demon lines, every
stat) at api.prizepicks.com/projections?league_id=9, but behind DataDome
bot protection: a server request gets a CAPTCHA page, and getting around
that isn't something this app does. A logged-in browser passes it, so the
user saves that page (Cmd+S, ~4 MB) and uploads it on the Bets page; this
module keeps the lines betting_service can price. `per_page` doesn't matter:
the API returns the whole board on one page.

Stored in the odds_cache table (key "prizepicks_board") so it survives
Render restarts. The Odds API's PrizePicks standard lines remain the
fallback when no recent upload exists.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.services import odds_service

# PrizePicks stat_type -> the board's market key (only stats the model prices).
STAT_MARKETS = {
    "Receiving Yards": "player_reception_yds",
    "Rush Yards": "player_rush_yds",
    "Receptions": "player_receptions",
    "Pass Yards": "player_pass_yds",
    "Anytime TDs": "player_anytime_td",
}
CACHE_KEY = "prizepicks_board"
MAX_AGE = timedelta(hours=36)  # lines move daily; an older upload is ignored


class BoardError(ValueError):
    pass


def _allowed_sides(value: Any) -> List[str]:
    """`allowed_wager_types` comes as a string: "over" (goblins/demons),
    "under_or_over", or null (both)."""
    text = value if isinstance(value, str) else " ".join(value or [])
    sides = [side for side in ("over", "under") if side in text]
    return sides or ["over", "under"]


def parse_board(raw: Any) -> Dict[str, Any]:
    """Saved projections JSON -> {"lines": [...], "total": n}. Keeps
    single-player NFL lines for the priced stats; raises BoardError when the
    file isn't a PrizePicks projections response (e.g. the CAPTCHA page)."""
    if not isinstance(raw, dict) or not isinstance(raw.get("data"), list) or not isinstance(raw.get("included"), list):
        raise BoardError("That isn't a PrizePicks projections file. Save the api.prizepicks.com/projections page itself.")
    players = {i.get("id"): i.get("attributes") or {} for i in raw["included"] if i.get("type") == "new_player"}
    lines: List[Dict[str, Any]] = []
    for p in raw["data"]:
        a = p.get("attributes") or {}
        if a.get("league_ppid") not in (None, "NFL"):
            continue
        market = STAT_MARKETS.get(a.get("stat_type"))
        if market is None or a.get("event_type") != "team" or a.get("line_score") is None:
            continue
        player_id = (((p.get("relationships") or {}).get("new_player") or {}).get("data") or {}).get("id")
        player = players.get(player_id) or {}
        name = player.get("name") or player.get("display_name")
        if not name:
            continue
        lines.append({
            "player": name,
            "team": odds_service.normalize_team(player.get("team")),
            "market": market,
            "line": float(a["line_score"]),
            "odds_type": a.get("odds_type") or "standard",
            "allowed": _allowed_sides(a.get("allowed_wager_types")),
            "start_time": a.get("start_time"),
        })
    if not lines:
        raise BoardError("No NFL lines found in that file. Use the league_id=9 (NFL) URL.")
    return {"lines": lines, "total": len(raw["data"])}


async def save(parsed: Dict[str, Any]) -> Dict[str, Any]:
    stored = {**parsed, "uploaded_at": datetime.now(timezone.utc).isoformat()}
    await asyncio.to_thread(odds_service._db_write, CACHE_KEY, stored)
    return stored


async def load_recent() -> Optional[Dict[str, Any]]:
    """The last upload if it's under MAX_AGE old, else None."""
    stored = await asyncio.to_thread(odds_service._db_read, CACHE_KEY)
    if not stored:
        return None
    fetched_at, data = stored
    if datetime.now(timezone.utc) - fetched_at > MAX_AGE:
        return None
    return data
