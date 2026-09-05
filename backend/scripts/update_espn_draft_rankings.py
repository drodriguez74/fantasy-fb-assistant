#!/usr/bin/env python3
"""Push a custom player-ranking spreadsheet into ESPN's pre-draft strategy.

ESPN's "Edit Pre-Draft Strategy" page (fantasy.espn.com/football/editdraftstrategy)
has no bulk-import for an external rankings file -- reordering is drag-and-drop
only, one player at a time, which is impractical for a few hundred ranked
players. This script instead resolves each spreadsheet player to ESPN's real
numeric playerId (via this app's existing ESPN connection) and POSTs the full
ordered list directly to the same private write endpoint ESPN's own "Save
Rankings" button uses.

Only the top N players in your spreadsheet are reordered. Every other player
ESPN tracks (deep bench, etc.) is preserved in whatever order ESPN already had
them in and appended after your list, so nothing is dropped.

Usage (run from backend/, with venv activated):
    python scripts/update_espn_draft_rankings.py path/to/rankings.xlsx --league-id 1428917746

    # See what would happen without writing anything to ESPN:
    python scripts/update_espn_draft_rankings.py path/to/rankings.xlsx --league-id 1428917746 --dry-run

Spreadsheet format expected: a sheet (default name "Overall") with a header
row containing at least "Player", "Pos", and "Team" columns (case-insensitive,
any column order), one player per row below it, in the order you want them
ranked. Leading title/blank rows before the header are fine -- the header row
is located automatically.

If ESPN rejects the write (401/403), your stored SWID/espn_s2 cookies have
likely expired -- reconnect via POST /leagues/espn/connect and retry.

If ESPN rejects it with a different error mentioning the URL/version, the
--platform-version value below is stale (it's a hash tied to ESPN's current
frontend build, not documented or versioned by ESPN). To get a fresh one:
open the Edit Pre-Draft Strategy page, drag one player, click "Save Rankings",
and read the "platformVersion" query param off the POST request to
lm-api-writes.fantasy.espn.com in your browser's Network tab.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
import openpyxl
from espn_api.football import League

from app.db.base import SessionLocal
from app.models.user_league import UserLeague

# Tied to ESPN's current frontend build -- see the docstring above for how to
# refresh this if writes start failing.
DEFAULT_PLATFORM_VERSION = "96e7cdc122a61e6c778b4087703c10d123d0565d"

# Known name/team mismatches between spreadsheet sources and ESPN's own
# player database. Add to these as new mismatches turn up -- matching first
# falls back to exact normalized name, so most players never need an entry
# here.
NAME_ALIASES = {
    "nick singleton": "nicholas singleton",
}
TEAM_ALIASES = {
    "WAS": "WSH",
}


def normalize_name(name: str) -> str:
    if not name:
        return ""
    s = name.lower()
    s = re.sub(r"[.\-']", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return NAME_ALIASES.get(s, s)


def load_spreadsheet_rankings(xlsx_path: str, sheet_name: str) -> list[dict]:
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    if sheet_name not in wb.sheetnames:
        raise SystemExit(
            f"Sheet '{sheet_name}' not found. Available sheets: {wb.sheetnames}"
        )
    ws = wb[sheet_name]

    header_row_idx = None
    header_map = {}
    for row in ws.iter_rows(min_row=1, max_row=min(20, ws.max_row)):
        cells = {str(c.value).strip().lower(): c.column - 1 for c in row if c.value}
        if "player" in cells and ("pos" in cells or "position" in cells):
            header_row_idx = row[0].row
            header_map = cells
            break
    if header_row_idx is None:
        raise SystemExit(
            f"Could not find a header row with 'Player' and 'Pos' columns in "
            f"sheet '{sheet_name}' (checked first 20 rows)."
        )

    name_col = header_map["player"]
    pos_col = header_map.get("pos", header_map.get("position"))
    team_col = header_map.get("team")

    players = []
    for row in ws.iter_rows(min_row=header_row_idx + 1, values_only=True):
        name = row[name_col] if name_col < len(row) else None
        if not name:
            continue
        players.append(
            {
                "name": str(name).strip(),
                "pos": str(row[pos_col]).strip().upper() if pos_col is not None and row[pos_col] else None,
                "team": str(row[team_col]).strip().upper() if team_col is not None and row[team_col] else None,
            }
        )
    return players


def fetch_espn_player_universe(league_id: str, season: int, swid: str, espn_s2: str) -> list[dict]:
    league = League(league_id=int(league_id), year=season, swid=swid, espn_s2=espn_s2)
    free_agents = league.free_agents(size=2000)
    return [
        {"playerId": p.playerId, "name": p.name, "position": p.position, "team": getattr(p, "proTeam", None)}
        for p in free_agents
    ]


def match_players(sheet_players: list[dict], espn_players: list[dict]) -> tuple[list[int], list[dict]]:
    """Returns (ordered playerId list covering every ESPN player, unmatched sheet rows)."""
    espn_by_name: dict[str, list[dict]] = {}
    for p in espn_players:
        espn_by_name.setdefault(normalize_name(p["name"]), []).append(p)
    espn_dst_by_team = {p["team"]: p for p in espn_players if p["position"] in ("D/ST", "DST")}

    matched_ids: list[int] = []
    used_ids: set[int] = set()
    unmatched: list[dict] = []

    for sp in sheet_players:
        if sp["pos"] in ("DST", "D/ST", "DEF"):
            team = TEAM_ALIASES.get(sp["team"], sp["team"])
            ep = espn_dst_by_team.get(team)
            if ep and ep["playerId"] not in used_ids:
                matched_ids.append(ep["playerId"])
                used_ids.add(ep["playerId"])
            else:
                unmatched.append(sp)
            continue

        cands = [c for c in espn_by_name.get(normalize_name(sp["name"]), []) if c["playerId"] not in used_ids]
        if not cands:
            unmatched.append(sp)
            continue
        if len(cands) == 1:
            chosen = cands[0]
        else:
            pos_cands = [c for c in cands if c["position"] == sp["pos"]]
            if len(pos_cands) != 1:
                unmatched.append(sp)
                continue
            chosen = pos_cands[0]
        matched_ids.append(chosen["playerId"])
        used_ids.add(chosen["playerId"])

    remaining = [p["playerId"] for p in espn_players if p["playerId"] not in used_ids]
    return matched_ids + remaining, unmatched


def push_to_espn(
    league_id: str,
    team_id: str,
    season: int,
    swid: str,
    espn_s2: str,
    ordered_player_ids: list[int],
    platform_version: str,
) -> None:
    url = (
        f"https://lm-api-writes.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}"
        f"/segments/0/leagues/{league_id}/teams/{team_id}"
        f"?platformVersion={platform_version}"
    )
    payload = {"draftStrategy": {"draftList": [{"playerId": pid} for pid in ordered_player_ids]}}
    cookies = {"SWID": swid, "espn_s2": espn_s2}
    resp = httpx.post(url, json=payload, cookies=cookies, timeout=30.0)
    resp.raise_for_status()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("xlsx_path", help="Path to the rankings spreadsheet")
    parser.add_argument("--league-id", required=True, help="ESPN league ID (from the league URL)")
    parser.add_argument("--user-id", type=int, default=None, help="App user ID, if more than one user has this league connected")
    parser.add_argument("--sheet", default="Overall", help="Sheet name to read rankings from (default: Overall)")
    parser.add_argument("--platform-version", default=DEFAULT_PLATFORM_VERSION, help="ESPN frontend build hash -- see docstring if writes start failing")
    parser.add_argument("--dry-run", action="store_true", help="Resolve and report matches without writing to ESPN")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        query = db.query(UserLeague).filter(UserLeague.league_id == args.league_id, UserLeague.platform == "ESPN")
        if args.user_id is not None:
            query = query.filter(UserLeague.user_id == args.user_id)
        leagues = query.all()
        if not leagues:
            raise SystemExit(f"No connected ESPN league found for league_id={args.league_id}")
        if len(leagues) > 1:
            raise SystemExit(
                f"Multiple users have league_id={args.league_id} connected "
                f"(user_ids: {[l.user_id for l in leagues]}); pass --user-id to disambiguate."
            )
        ul = leagues[0]
        if not ul.espn_swid or not ul.espn_s2 or not ul.team_id:
            raise SystemExit(
                "This league is missing espn_swid/espn_s2/team_id -- reconnect via "
                "POST /leagues/espn/connect and make sure your team is set."
            )
    finally:
        db.close()

    print(f"Loading rankings from '{args.xlsx_path}' (sheet: {args.sheet})...")
    sheet_players = load_spreadsheet_rankings(args.xlsx_path, args.sheet)
    print(f"  {len(sheet_players)} ranked players found")

    print(f"Fetching ESPN's player universe for league {ul.league_id} (season {ul.season})...")
    espn_players = fetch_espn_player_universe(ul.league_id, ul.season, ul.espn_swid, ul.espn_s2)
    print(f"  {len(espn_players)} players known to ESPN")

    ordered_ids, unmatched = match_players(sheet_players, espn_players)
    matched_count = len(sheet_players) - len(unmatched)
    print(f"Matched {matched_count}/{len(sheet_players)} spreadsheet rows to ESPN players.")
    if unmatched:
        print("Unmatched rows (not reordered -- will keep ESPN's existing position for these):")
        for u in unmatched:
            print(f"  - {u['name']} ({u['pos']}, {u['team']})")

    if args.dry_run:
        print("\n--dry-run: no write performed. Top 10 of the order that would be sent:")
        id_to_name = {p["playerId"]: p["name"] for p in espn_players}
        for i, pid in enumerate(ordered_ids[:10], 1):
            print(f"  {i}. {id_to_name.get(pid, pid)}")
        return

    print(f"Writing {len(ordered_ids)}-player draft order to ESPN...")
    push_to_espn(ul.league_id, ul.team_id, ul.season, ul.espn_swid, ul.espn_s2, ordered_ids, args.platform_version)
    print("Done. Reload the Edit Pre-Draft Strategy page in ESPN to verify.")


if __name__ == "__main__":
    main()
