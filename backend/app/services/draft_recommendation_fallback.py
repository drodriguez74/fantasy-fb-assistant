"""
Algorithmic draft-recommendation baseline for when AI is genuinely
unavailable (both providers circuit-broken -- see ai_service.py's
_generate_with_fallback -- or otherwise failed).

Pure, deterministic, no AI calls. Same principle as roster_grading.py: real
math over real data instead of an empty result, using the exact ranking
preference order mock_draft_service.py already established for the same
"a player might only have some of these signals" problem --
search_rank/adp (both already expressed on a "draft pick" scale) preferred,
projected_points as a fallback, and an honest "Insufficient Data" outcome
when a player has none of the three rather than a fabricated rank.

This intentionally produces a DIFFERENT, clearly-labeled kind of result from
a real AI recommendation -- callers must surface `source: "algorithmic"`
rather than let it look identical to genuine AI reasoning (see
draft.py::get_draft_recommendations).
"""

from typing import Any, Dict, List, Optional


def _player_rank_signal(player: Dict[str, Any]) -> Optional[tuple]:
    """Returns a (tier, sort_key) tuple usable to sort players best-first, or
    None if the player carries none of the real signals this can use.

    tier 0 = search_rank/adp present (lower is better, most direct signal).
    tier 1 = only projected_points present (higher is better).
    Lower tier always sorts ahead of higher tier, matching
    mock_draft_service.py's documented preference order.
    """
    search_rank = player.get("search_rank")
    adp = player.get("adp")
    if search_rank is not None:
        return (0, float(search_rank))
    if adp is not None:
        return (0, float(adp))

    projected_points = player.get("projected_points")
    if projected_points is not None:
        return (1, -float(projected_points))  # negate: higher points sorts first within tier 1

    return None


def _reasoning_for(player: Dict[str, Any], rank_signal: Optional[tuple], addresses_need: bool) -> str:
    name = player.get("full_name") or player.get("name") or "This player"
    need_clause = " Addresses a stated positional need." if addresses_need else ""

    if rank_signal is None:
        return f"{name} has no ranking or projection data available to rank against other options.{need_clause}"

    tier, _ = rank_signal
    if tier == 0:
        source = "search rank" if player.get("search_rank") is not None else "ADP"
        value = player.get("search_rank") if player.get("search_rank") is not None else player.get("adp")
        return f"Ranked #{value:g} by {source} among available players.{need_clause}"

    points = player.get("projected_points")
    return f"Highest projected points among available players without rank/ADP data ({points:g} pts).{need_clause}"


def _confidence_for(rank_signal: Optional[tuple]) -> int:
    """A real, data-availability-tied confidence figure -- not a fabricated
    LLM-style guess. Tied directly to which real signal (if any) backed the
    ranking, so it degrades honestly instead of always showing a fixed
    number regardless of how little data actually supported the pick.
    """
    if rank_signal is None:
        return 0
    tier, _ = rank_signal
    return 70 if tier == 0 else 50


def generate_algorithmic_draft_recommendations(
    available_players: List[Dict[str, Any]],
    team_needs: List[str],
    limit: int = 3,
) -> Dict[str, Any]:
    """Real, deterministic top-N draft recommendations.

    available_players: same shape the AI path already receives (real player
        dicts, whichever of search_rank/adp/projected_points each carries).
    team_needs: list of position strings the caller considers a need.

    Returns {"recommendations": [...], "source": "algorithmic"} -- always
    include the source flag so a caller can never present this as if it
    were genuine AI reasoning.
    """
    needs = {n.upper() for n in (team_needs or [])}

    ranked = []
    for player in available_players:
        rank_signal = _player_rank_signal(player)
        addresses_need = (player.get("position") or "").upper() in needs
        # Positional need moves a player up half a tier's worth of players,
        # not to the very top regardless of quality -- a real but bounded
        # boost, matching the spirit (not the exact formula) of
        # _effective_position_requirements' need-aware treatment elsewhere
        # in this codebase, without needing a full roster to compute against
        # (this endpoint only ever receives team_needs, not a full roster).
        need_bonus = -0.5 if addresses_need else 0.0
        sort_key = (
            rank_signal[0] if rank_signal else 2,
            (rank_signal[1] if rank_signal else 0.0) + need_bonus,
        )
        ranked.append((sort_key, player, rank_signal, addresses_need))

    ranked.sort(key=lambda entry: entry[0])

    recommendations = []
    for _, player, rank_signal, addresses_need in ranked[:limit]:
        recommendations.append({
            "player_name": player.get("full_name") or player.get("name") or "Unknown Player",
            "position": player.get("position"),
            "reasoning": _reasoning_for(player, rank_signal, addresses_need),
            "confidence": _confidence_for(rank_signal),
        })

    return {"recommendations": recommendations, "source": "algorithmic"}
