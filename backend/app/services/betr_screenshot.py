"""Read screenshots of Betr's NFL board into board lines.

Betr's site doesn't let the founder select its text (2026-11-09), so a
screenshot of a stat tab is the easy way in: a vision model (OpenAI first,
Claude as fallback, entry_screenshot.read_image_json) reads each player card,
and betr_board.line_from_card turns it into the same line the paste parser
makes. One model call per screenshot, nothing stored but the lines. A misread
card can't land as the wrong player: names still have to match the books'
board by initial, last name and opponent (betting_service.
_resolve_abbreviated_names), or the line stays unpriced.
"""
import re
from typing import Any, Dict, List, Tuple

from app.services import betr_board
from app.services.entry_screenshot import ScreenshotError, read_image_json

MAX_FILES = 12

PROMPT = """This is a screenshot of the Betr Picks NFL board (a more/less pick'em app).
Read every player card that is fully visible into the JSON schema. Each card shows:
- player: the name exactly as shown, usually a first initial and last name ("J. Jefferson", "A. St. Brown",
  "J. Cook III"). Keep suffixes and punctuation as shown.
- position: QB, RB, WR, TE or K as shown.
- matchup: "vs XXX" or "@ XXX" with the opponent's abbreviation, copied from the line under the name
  (e.g. "vs BUF" or "@ MIN"). Leave out the date and time.
- line: the current number on the card (the large one).
- was_line: if a second number is shown crossed out (struck through) next to the line, that crossed-out number;
  otherwise null.
- stat: the stat label under the number exactly as shown (e.g. "Receiving Yds", "Passing Yds", "Rushing Yds",
  "Receptions", "Passing TD", "Rush+Rec Yds", "Pass+Rush Yds", "Interceptions", "Completions", "Passing Att",
  "Rushing Att", "Rush+Rec TD").
- more_only: true if the card has only a "More" button and no "Less" button; false if it shows both.
Skip cards that are cut off at the edge of the screenshot. notes: anything you couldn't read, in one short
sentence; empty string if none. Copy numbers exactly; never guess a value you can't see."""

SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "player": {"type": "string"},
                    "position": {"type": "string"},
                    "matchup": {"type": "string"},
                    "line": {"type": "number"},
                    "was_line": {"type": ["number", "null"]},
                    "stat": {"type": "string"},
                    "more_only": {"type": "boolean"},
                },
                "required": ["player", "position", "matchup", "line", "was_line", "stat", "more_only"],
                "additionalProperties": False,
            },
        },
        "notes": {"type": "string"},
    },
    "required": ["cards", "notes"],
    "additionalProperties": False,
}

_MATCHUP = re.compile(r"^\s*(vs\.?|@)\s*([A-Za-z]{2,4})\b")


def cards_to_lines(cards: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """The model's cards -> (board lines, warnings). Unpriced stats are
    skipped quietly; unreadable matchups are reported."""
    lines, warnings = [], []
    for c in cards:
        m = _MATCHUP.match(c.get("matchup") or "")
        if not m:
            warnings.append(f"{c.get('player')}: couldn't read the opponent (\"{c.get('matchup')}\"), skipped.")
            continue
        side = "vs" if m.group(1).startswith("vs") else "@"
        numbers = [float(c["was_line"]), float(c["line"])] if c.get("was_line") is not None else [float(c["line"])]
        line = betr_board.line_from_card(c["player"].strip(), (c.get("position") or "").strip().upper(), side,
                                         m.group(2).upper(), None, (c.get("stat") or "").strip(), numbers,
                                         bool(c.get("more_only")))
        if line:
            lines.append(line)
    return lines, warnings


async def read_screenshots(images: List[Tuple[bytes, str]]) -> Dict[str, Any]:
    """Screenshots -> {"league", "platform", "lines", "total", "warnings"},
    the shape betr_board.parse_paste returns (so merge/save work the same)."""
    if not images:
        raise ScreenshotError("Add at least one screenshot of Betr's board.")
    if len(images) > MAX_FILES:
        raise ScreenshotError(f"Up to {MAX_FILES} screenshots at a time.")
    lines: List[Dict[str, Any]] = []
    warnings: List[str] = []
    total = 0
    seen = set()
    for data, media_type in images:
        read = await read_image_json(data, media_type, PROMPT, SCHEMA, "betr_board",
                                     too_big="That screenshot is over 5 MB; crop it to the board and try again.")
        if read.get("notes"):
            warnings.append(read["notes"])
        total += len(read.get("cards") or [])
        got, warn = cards_to_lines(read.get("cards") or [])
        warnings += warn
        for line in got:
            key = (line["player"], line["opponent"], line["market"], line["line"])
            if key not in seen:
                seen.add(key)
                lines.append(line)
    if not total:
        raise ScreenshotError("No Betr player cards found in those screenshots.")
    if not lines:
        raise ScreenshotError("Found Betr cards, but none for a stat we price.")
    return {"league": "NFL", "platform": betr_board.PLATFORM, "lines": lines, "total": total, "warnings": warnings}
