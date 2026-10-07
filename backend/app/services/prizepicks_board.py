"""The user's uploaded PrizePicks boards (NFL and college football).

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
CACHE_KEY = "prizepicks_board"  # NFL; other leagues append ":<league>"
# Leagues the board prices, by PrizePicks' own league_ppid (college football
# is "NCAAFB" in a real file, 2026-10-07) -- used as-is, never translated.
LEAGUES = ("NFL", "NCAAFB")
# Each league's board URL (PrizePicks league_id).
BOARD_URLS = {
    "NFL": "https://api.prizepicks.com/projections?league_id=9&per_page=1000",
    "NCAAFB": "https://api.prizepicks.com/projections?league_id=15&per_page=1000",
}


def _key(league: str) -> str:
    return CACHE_KEY if league == "NFL" else f"{CACHE_KEY}:{league}"
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
    """Saved projections JSON -> {"league", "lines": [...], "total": n}. The
    league (NFL or NCAAFB) is read from the file; keeps single-player lines for
    the priced stats. Raises BoardError when the file isn't a PrizePicks
    projections response (e.g. the CAPTCHA page) or is another sport."""
    if not isinstance(raw, dict) or not isinstance(raw.get("data"), list) or not isinstance(raw.get("included"), list):
        raise BoardError("That isn't a PrizePicks projections file. Save the api.prizepicks.com/projections page itself.")
    counts: Dict[str, int] = {}
    for p in raw["data"]:
        lg = (p.get("attributes") or {}).get("league_ppid")
        if lg:
            counts[lg] = counts.get(lg, 0) + 1
    league = max(counts, key=counts.get) if counts else "NFL"
    if league not in LEAGUES:
        raise BoardError(f"That's a {league} board. Upload the NFL (league_id=9) or college football (league_id=15) page.")
    players = {i.get("id"): i.get("attributes") or {} for i in raw["included"] if i.get("type") == "new_player"}
    lines: List[Dict[str, Any]] = []
    for p in raw["data"]:
        a = p.get("attributes") or {}
        if a.get("league_ppid") not in (None, league):
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
            # "Alabama" + "Crimson Tide": The Odds API's team name, used to
            # match college players to games.
            "team_full": " ".join(x for x in (player.get("market"), player.get("team_name")) if x) or None,
            "market": market,
            "line": float(a["line_score"]),
            "odds_type": a.get("odds_type") or "standard",
            "allowed": _allowed_sides(a.get("allowed_wager_types")),
            "start_time": a.get("start_time"),
        })
    if not lines:
        raise BoardError(f"No {league} lines for the stats we price were found in that file.")
    return {"league": league, "lines": lines, "total": len(raw["data"])}


async def save(parsed: Dict[str, Any]) -> Dict[str, Any]:
    stored = {**parsed, "uploaded_at": datetime.now(timezone.utc).isoformat()}
    await asyncio.to_thread(odds_service._db_write, _key(parsed.get("league", "NFL")), stored)
    return stored


async def load_recent(league: str = "NFL") -> Optional[Dict[str, Any]]:
    """The league's last upload if it's under MAX_AGE old, else None."""
    stored = await asyncio.to_thread(odds_service._db_read, _key(league))
    if not stored:
        return None
    fetched_at, data = stored
    if datetime.now(timezone.utc) - fetched_at > MAX_AGE:
        return None
    return data
