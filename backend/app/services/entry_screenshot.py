"""Read a PrizePicks entry screenshot into the "My entries" form.

The founder screenshots an entry they placed; a vision model (OpenAI first,
Claude as fallback, like ai_service) reads the entry type, fee, payout and
picks into a JSON schema. The result only prefills the
form: the user checks it and saves it themselves, so a misread never lands in
the record unseen. One call per screenshot, nothing stored.
"""
import base64
import json
import logging
from typing import Any, Dict

import anthropic
import openai

from app.core.config import settings
from app.services.ai_service import AIService
from app.services.user_entries import MARKETS

logger = logging.getLogger(__name__)

MEDIA_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
MAX_BYTES = 5 * 1024 * 1024  # the API's per-image limit


class ScreenshotError(ValueError):
    pass


_STAT_GUIDE = "\n".join(f"- {key}: {label}" for key, (label, _) in MARKETS.items())

PROMPT = f"""This is a screenshot of a PrizePicks entry the user placed (NFL or college football).
Read it into the JSON schema.

- entry_type: "power" (Power Play: every pick must hit) or "flex" (Flex Play: pays on most hits).
  Use null if the screenshot doesn't say.
- stake: the entry fee in dollars. to_win: what the entry pays if every pick hits
  (PrizePicks shows e.g. "$10 to pay $30"; to_win is 30, not the profit). null if not shown.
- picks: one per player, in screen order. side is "More" or "Less"; PrizePicks often shows it as an
  arrow instead: an up arrow is "More", a down arrow is "Less". line is the number shown.
  market is the stat, mapped to one of these keys (use "other" if it matches none):
{_STAT_GUIDE}
  Short labels count: "Recs" is Receptions, "Rec Yds" is Receiving Yards. "Rush+Rec Yds" and
  "Pass+Rush Yds" are the combo stats; "Fantasy Score" and other stats are "other".
  stat_label: the stat exactly as written on screen. team: the player's team abbreviation if shown, else null.
  pick_type: "goblin" (green goblin icon, an easier line) or "demon" (red/purple demon icon, a harder
  line) if the pick shows one, else "standard".
  If the screenshot says it's page 1 of 2 or the entry type names more picks than are visible,
  read the visible ones and say so in notes.
- notes: anything you couldn't read or weren't sure of, in one short sentence; empty string if none.

Copy numbers exactly as shown. Never guess a value you can't see: use null instead."""

SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "entry_type": {"type": ["string", "null"], "enum": ["power", "flex", None]},
        "stake": {"type": ["number", "null"]},
        "to_win": {"type": ["number", "null"]},
        "picks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "player": {"type": "string"},
                    "team": {"type": ["string", "null"]},
                    "market": {"type": "string", "enum": [*MARKETS, "other"]},
                    "stat_label": {"type": "string"},
                    "side": {"type": "string", "enum": ["More", "Less"]},
                    "line": {"type": "number"},
                    "pick_type": {"type": "string", "enum": ["standard", "goblin", "demon"]},
                },
                "required": ["player", "team", "market", "stat_label", "side", "line", "pick_type"],
                "additionalProperties": False,
            },
        },
        "notes": {"type": "string"},
    },
    "required": ["entry_type", "stake", "to_win", "picks", "notes"],
    "additionalProperties": False,
}


def _warnings(data: Dict[str, Any]) -> list:
    out = []
    if data.get("notes"):
        out.append(data["notes"])
    for p in data.get("picks", []):
        if p["market"] == "other":
            out.append(f"{p['player']}: \"{p['stat_label']}\" isn't a stat we grade yet; pick the closest or skip it.")
        if p["pick_type"] != "standard":
            out.append(f"{p['player']} is a {p['pick_type']} pick; check the payout matches the screenshot.")
    if not 2 <= len(data.get("picks", [])) <= 6:
        out.append("An entry has 2 to 6 picks; check the screenshot shows the whole entry.")
    return out


async def _read_openai(b64: str, media_type: str) -> Dict[str, Any]:
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OpenAI not configured")
    client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    # GPT-5 family: max_completion_tokens, no temperature (see ai_service._call_openai).
    response = await client.chat.completions.create(
        model=AIService.DEEP_OPENAI_MODEL,
        max_completion_tokens=8000,
        response_format={"type": "json_schema",
                         "json_schema": {"name": "prizepicks_entry", "strict": True, "schema": SCHEMA}},
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
            {"type": "text", "text": PROMPT},
        ]}],
    )
    choice = response.choices[0]
    if choice.finish_reason != "stop" or not choice.message.content:
        raise RuntimeError(f"OpenAI stopped: {choice.finish_reason}")
    return json.loads(choice.message.content)


async def _read_anthropic(b64: str, media_type: str) -> Dict[str, Any]:
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("Anthropic not configured")
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model=AIService.DEEP_ANTHROPIC_MODEL,
        max_tokens=8000,
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
            {"type": "text", "text": PROMPT},
        ]}],
    )
    if response.stop_reason != "end_turn":
        raise RuntimeError(f"Anthropic stopped: {response.stop_reason}")
    return json.loads(next(b.text for b in response.content if b.type == "text"))


async def read_screenshot(image: bytes, media_type: str) -> Dict[str, Any]:
    if media_type not in MEDIA_TYPES:
        raise ScreenshotError("Upload a PNG, JPEG, WebP or GIF screenshot.")
    if len(image) > MAX_BYTES:
        raise ScreenshotError("That image is over 5 MB; crop it to the entry and try again.")
    if not (settings.OPENAI_API_KEY or settings.ANTHROPIC_API_KEY):
        raise ScreenshotError("Screenshot reading isn't configured (no AI key set).")

    b64 = base64.standard_b64encode(image).decode()
    data, last_error = None, None
    for provider, call in (("openai", _read_openai), ("anthropic", _read_anthropic)):
        try:
            data = await call(b64, media_type)
            break
        except Exception as e:  # noqa: BLE001 - fall through to the next provider
            last_error = e
            # Type only: never log the request (it carries the image and key headers).
            logger.warning("Screenshot read via %s failed: %s", provider, type(e).__name__)
    if data is None:
        raise ScreenshotError("Couldn't read the screenshot right now; try again or enter it by hand.") from last_error
    if not data.get("picks"):
        raise ScreenshotError("No picks found. Is this a PrizePicks entry screenshot?")
    return {**data, "warnings": _warnings(data)}
