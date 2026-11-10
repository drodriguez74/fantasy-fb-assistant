"""The user's pasted Betr Picks board (NFL).

Betr (picks.betr.app) is a more/less pick'em app like PrizePicks. The Odds
API has no US Betr feed (its DFS books are PrizePicks, Underdog, Pick6 and
Dabble, checked 2026-11-09), and the site loads its board through a
logged-in GraphQL request with a GeoComply location check, so there's no
file to save either. Instead the founder opens a stat tab on Betr's NFL page
(Receiving Yds, Passing Yds, ...), presses Cmd+A / Cmd+C, and pastes it on
the Bets page; several tabs can go in one paste. The app never signs into or
browses Betr itself.

Each card in the copied text reads, one item per line:

    J. Jefferson          <- first initial + last name (suffixes kept)
    WR                    <- position
    vs BUF • Today, 8:15 PM   <- "vs" = player's team is home, "@" = away
    84.5                  <- optional: the line before a discount (struck through)
    79.5                  <- the current line
    Receiving Yds         <- Betr's stat label
    More
    Less                  <- absent when only More is allowed

The lines are stored in the same slot as a PrizePicks upload
(prizepicks_board, platform "betr"), so the board prices them the same way;
betting_service resolves "J. Jefferson vs BUF" to the books' full name by
first initial, last name and opponent.
"""
import re
from typing import Any, Dict, List, Optional

from app.services import odds_service

# Betr's stat label -> the board's market key (only stats the model prices).
# "Rush+Rec TD" over 0.5 is an anytime TD (the books' market also counts the
# rare return TD). Not priced: Fantasy Pts, Longest *, FG Made, Kicking
# Points, 1st TD Scorer, Targets (no Odds API market).
STAT_MARKETS = {
    "Passing Yds": "player_pass_yds",
    "Rushing Yds": "player_rush_yds",
    "Receiving Yds": "player_reception_yds",
    "Receptions": "player_receptions",
    "Passing TD": "player_pass_tds",
    "Rush+Rec TD": "player_anytime_td",
    "Rush+Rec Yds": "player_rush_rec_yds",
    "Pass+Rush Yds": "player_pass_rush_yds",
    "Interceptions": "player_pass_interceptions",
    "Completions": "player_pass_completions",
    "Passing Att": "player_pass_attempts",
    "Rushing Att": "player_rush_attempts",
}
POSITIONS = frozenset({"QB", "RB", "WR", "TE", "K", "FB"})
PLATFORM = "betr"
_MATCHUP = re.compile(r"^(vs|@)\s+([A-Z]{2,4})\s*[•·]\s*(.+)$")
_NUMBER = re.compile(r"^\d+(\.\d+)?$")


class PasteError(ValueError):
    pass


def parse_paste(text: str) -> Dict[str, Any]:
    """Pasted Betr page text -> {"league", "platform", "lines", "total"}.
    Cards for stats we don't price are counted in `total` but skipped; the
    same card pasted twice (two tabs) is kept once."""
    rows = [r.strip() for r in (text or "").splitlines()]
    rows = [r for r in rows if r]
    lines: List[Dict[str, Any]] = []
    seen = set()
    total = 0
    i = 0
    while i + 2 < len(rows):
        m = _MATCHUP.match(rows[i + 2])
        if rows[i + 1] not in POSITIONS or not m:
            i += 1
            continue
        card = _read_card(rows, i, m)
        if card is None:
            i += 1
            continue
        parsed, i = card
        total += 1
        if parsed is None:
            continue
        key = (parsed["player"], parsed["opponent"], parsed["market"], parsed["line"])
        if key not in seen:
            seen.add(key)
            lines.append(parsed)
    if not total:
        raise PasteError("No Betr player cards found. On Betr's NFL page, open a stat tab, press Cmd+A then Cmd+C, "
                         "and paste here.")
    if not lines:
        raise PasteError("Found Betr cards, but none for a stat we price (passing, rushing, receiving yards, "
                         "receptions, TDs, attempts, completions, interceptions).")
    return {"league": "NFL", "platform": PLATFORM, "lines": lines, "total": total}


def _read_card(rows: List[str], i: int, matchup: "re.Match") -> Optional[tuple]:
    """One card starting at rows[i] -> (line dict or None if unpriced, next index)."""
    j = i + 3
    numbers: List[float] = []
    while j < len(rows) and _NUMBER.match(rows[j]) and len(numbers) < 2:
        numbers.append(float(rows[j]))
        j += 1
    if not numbers or j >= len(rows):
        return None
    stat = rows[j]
    j += 1
    sides = []
    while j < len(rows) and rows[j] in ("More", "Less") and len(sides) < 2:
        sides.append(rows[j])
        j += 1
    market = STAT_MARKETS.get(stat)
    if market is None:
        return None, j
    line = numbers[-1]
    allowed = ["over", "under"] if "Less" in sides or not sides else ["over"]
    if market == "player_anytime_td" and line != 0.5:
        return None, j
    return {
        "player": rows[i],
        "position": rows[i + 1],
        "opponent": odds_service.normalize_team(matchup.group(2)) or matchup.group(2),
        "player_home": matchup.group(1) == "vs",
        "start_label": matchup.group(3),
        "market": market,
        "line": line,
        # A struck-through earlier number: Betr discounted the line toward
        # More. Its payout isn't in the text, so it's ranked by hit chance
        # (like a PrizePicks goblin), never paired at the standard multiplier.
        "was_line": numbers[0] if len(numbers) == 2 else None,
        "odds_type": "discount" if len(numbers) == 2 else "standard",
        "allowed": ["over"] if len(numbers) == 2 else allowed,
    }, j


def merge(previous: Optional[Dict[str, Any]], parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Add a new paste to a recent Betr paste (one stat tab at a time is
    fine): a card in the new paste replaces the same player + stat before."""
    if not previous or previous.get("platform") != PLATFORM:
        return parsed
    new_keys = {(l["player"], l["opponent"], l["market"]) for l in parsed["lines"]}
    kept = [l for l in previous.get("lines") or [] if (l["player"], l["opponent"], l["market"]) not in new_keys]
    return {**parsed, "lines": kept + parsed["lines"], "total": len(kept) + parsed["total"]}
