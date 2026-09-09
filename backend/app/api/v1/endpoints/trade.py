"""
Trade Analyzer endpoint.

Lets a user propose "these players for those players" and get back a
grounded verdict on who gives up more value. This is intentionally a real
but simple heuristic -- not an AI/ML model -- and the UI copy must say so.
See `_player_value` below for the full reasoning behind the value curve.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.sleeper_service import sleeper_service
# Retired/inactive-player filter (Sleeper's `status` field alone still tags
# long-retired players like Frank Gore as "Active"; requiring a real `team`
# too is the fix) and the "unranked" sort sentinel.
from app.services.player_pool import (
    is_on_active_roster as _is_on_active_roster,
    UNRANKED_SENTINEL as _UNRANKED_SENTINEL,
)

router = APIRouter()


# --- Value model ------------------------------------------------------------
#
# HONESTY NOTE: this is a simple, transparent heuristic over Sleeper's own
# `search_rank` field (already used elsewhere in this app as an ADP/value
# proxy -- see draft.py's positional-rankings and players.py's ?sort=rank).
# It is NOT an AI/ML model, it does not know about matchups, injuries beyond
# the active-roster check below, contract situations, or scheme fit. Label it
# as a heuristic everywhere it's surfaced.
#
# Why inverse-rank-with-offset instead of a flat linear scale (e.g.
# `500 - rank`)? Real trade value does not decline linearly with rank: the
# gap in actual fantasy value between the #1 and #2 overall player is much
# larger than the gap between the #150 and #151 player. A flat linear scale
# would treat both gaps as identical and would go negative past rank 500.
# An inverse curve (value = SCALE / (rank + OFFSET)) is steep at the top and
# flattens out for deep bench players, which matches how real ADP-based
# trade value charts behave, without pretending to model anything this app
# doesn't actually have data for.
#
# SCALE and OFFSET are chosen so the #1 overall player scores exactly 500
# (a clean, arbitrary starting point) and the curve decays smoothly from
# there. These constants are a documented judgment call, not derived from
# any statistical fit -- there is no real historical trade outcome data in
# this app to fit a curve to.
_VALUE_SCALE = 10000
_VALUE_OFFSET = 19
_UNRANKED_FLOOR_VALUE = 1.0


def _player_value(search_rank: Optional[int]) -> float:
    """Convert a Sleeper search_rank into a 0-500ish heuristic value score.
    Lower search_rank (more in-demand/highly-drafted player) => higher value.
    Missing/unranked players (Sleeper's 9999999 sentinel, or no rank at all)
    get a small floor value rather than zero, since "unranked by Sleeper"
    isn't the same claim as "confirmed retired/inactive" -- that distinction
    is handled separately by `_is_on_active_roster`.
    """
    if search_rank is None or search_rank >= _UNRANKED_SENTINEL:
        return _UNRANKED_FLOOR_VALUE
    return round(_VALUE_SCALE / (search_rank + _VALUE_OFFSET), 1)


def _resolve_player(sleeper_id: str, all_players: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Look up one player by sleeper_id and compute their trade value.

    Retired/inactive players (per the same team+status check used in the
    Draft Assistant) are always assigned zero trade value, regardless of
    what search_rank Sleeper happens to have on file for them -- a trade
    analysis should never treat a retired player as having real value, even
    if a stale/leftover sleeper_id for one gets passed in directly.
    """
    data = all_players.get(sleeper_id)
    if not isinstance(data, dict):
        return None

    is_active = _is_on_active_roster(data)
    search_rank = data.get("search_rank")
    value = _player_value(search_rank) if is_active else 0.0
    name = data.get("full_name") or f"{data.get('first_name', '')} {data.get('last_name', '')}".strip() or "Unknown Player"

    return {
        "sleeper_id": sleeper_id,
        "name": name,
        "position": data.get("position"),
        "team": data.get("team"),
        "search_rank": search_rank,
        "is_active": is_active,
        "value": value,
    }


class TradeAnalysisRequest(BaseModel):
    side_a_gives: List[str]
    side_b_gives: List[str]


@router.post("/analysis")
async def analyze_trade(request: TradeAnalysisRequest):
    """Analyze a proposed trade: side_a_gives vs side_b_gives (lists of
    sleeper_ids). Returns each side's total heuristic value, each player's
    individual contribution, and a plain-language verdict grounded in the
    actual numbers.
    """
    try:
        if not request.side_a_gives or not request.side_b_gives:
            raise HTTPException(
                status_code=400,
                detail="Both sides of the trade must include at least one player"
            )

        all_players = await sleeper_service.get_all_players()
        if "error" in all_players:
            raise HTTPException(status_code=500, detail=all_players["error"])

        side_a_players: List[Dict[str, Any]] = []
        side_b_players: List[Dict[str, Any]] = []
        missing_ids: List[str] = []

        for sleeper_id in request.side_a_gives:
            resolved = _resolve_player(sleeper_id, all_players)
            if resolved is None:
                missing_ids.append(sleeper_id)
            else:
                side_a_players.append(resolved)

        for sleeper_id in request.side_b_gives:
            resolved = _resolve_player(sleeper_id, all_players)
            if resolved is None:
                missing_ids.append(sleeper_id)
            else:
                side_b_players.append(resolved)

        if missing_ids:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown player id(s): {', '.join(missing_ids)}"
            )

        side_a_total = round(sum(p["value"] for p in side_a_players), 1)
        side_b_total = round(sum(p["value"] for p in side_b_players), 1)

        # Side A gives up side_a_total of value and receives side_b_total of
        # value (what side B is putting in). Side A "wins" if it receives
        # more than it gives up.
        diff_for_a = round(side_b_total - side_a_total, 1)

        if diff_for_a == 0:
            winner = "even"
            summary = (
                f"Side A gives up {side_a_total} points of value, receives {side_b_total} -- "
                f"this trade is dead even by value."
            )
        elif diff_for_a > 0:
            winner = "side_a"
            summary = (
                f"Side A gives up {side_a_total} points of value, receives {side_b_total} -- "
                f"Side A wins this trade by {diff_for_a} points."
            )
        else:
            winner = "side_b"
            summary = (
                f"Side A gives up {side_a_total} points of value, receives {side_b_total} -- "
                f"Side B wins this trade by {abs(diff_for_a)} points."
            )

        retired_flags = [
            p["name"] for p in side_a_players + side_b_players if not p["is_active"]
        ]

        return {
            "side_a": {
                "players": side_a_players,
                "total_value": side_a_total,
            },
            "side_b": {
                "players": side_b_players,
                "total_value": side_b_total,
            },
            "verdict": {
                "winner": winner,
                "value_difference": abs(diff_for_a),
                "summary": summary,
            },
            "warnings": (
                [f"{name} is retired/inactive and was scored with zero trade value." for name in retired_flags]
                if retired_flags else []
            ),
            "value_model": {
                "basis": "Sleeper search_rank (ADP/demand proxy)",
                "description": (
                    "A simple heuristic, not an AI or projection model: each player's value is "
                    "derived only from Sleeper's own search_rank (lower rank = more in-demand "
                    "player = higher value), on a curve that's steep at the top and flattens out "
                    "for deep bench players. Retired/inactive players always score zero."
                ),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze trade: {str(e)}")


@router.get("/player-search")
async def search_trade_players(
    q: str = Query(..., min_length=1, description="Player name search term"),
    limit: int = Query(20, description="Max number of results to return")
):
    """Search for players to add to a trade proposal, filtered to players who
    are actually on an active NFL roster (excludes retired/free-agent
    players) and ranked by Sleeper's search_rank, same filtering rule as the
    Draft Assistant's positional rankings. This is a dedicated, filtered
    search for trade proposals rather than the general /players/search
    endpoint, which does not apply this filter and is used elsewhere for
    broader lookups.
    """
    try:
        all_players = await sleeper_service.get_all_players()
        if "error" in all_players:
            raise HTTPException(status_code=500, detail=all_players["error"])

        search_term = q.lower()
        matches = []
        for player_id, data in all_players.items():
            if not isinstance(data, dict):
                continue
            if not _is_on_active_roster(data):
                continue
            if data.get("position") not in ("QB", "RB", "WR", "TE", "K", "DEF"):
                continue

            full_name = (data.get("full_name") or "").lower()
            if search_term not in full_name:
                continue

            matches.append({
                "sleeper_id": player_id,
                "name": data.get("full_name"),
                "position": data.get("position"),
                "team": data.get("team"),
                "search_rank": data.get("search_rank"),
            })

        matches.sort(key=lambda p: p.get("search_rank") or _UNRANKED_SENTINEL)

        return {"players": matches[:limit], "search_term": q}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to search players: {str(e)}")
