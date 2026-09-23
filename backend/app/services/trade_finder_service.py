"""Real, roster-grounded trade finder.

Replaces the old `_get_espn_trade_recommendations` path, which asked the AI
to invent "3 realistic trade scenarios" knowing only `len(teams)` -- it had
zero visibility into any other team's actual roster, so `target_player` and
`offer_players` were free-form AI guesses, not real players available in a
real trade. That's fabrication, not a heuristic (contrast with
`trade.py`'s manual analyzer, which is honestly labeled as a heuristic over
real input players).

This module finds real two-way trade suggestions using only real, already-
rostered players and ESPN's own real season-long projection
(`projected_points` from `_format_player`, sourced from `projected_total_
points` -- this league's actual scoring settings, not a generic average).
No AI, no invented names -- every player in a suggestion is a real rostered
player on a real other team's real bench or starting lineup this week.
"""
from collections import defaultdict
from typing import Any, Dict, List, Optional

# Same convention as this_week_service.py -- a lineup_slot of BE/IR/blank
# (or Yahoo's BN/IR+) is bench, anything else is a real current starting slot.
BENCH_SLOTS = {"BE", "IR", "BENCH", "", "BN", "IR+"}

# Minimum real projection gap before a swap counts as an actual upgrade --
# without this, two players 0.1 pts apart on ESPN's own projection would
# spam "trade" suggestions that are really a coin flip.
_UPGRADE_MARGIN = 1.5

# A suggested trade must be roughly fair by value (the two real projections
# within this ratio of each other) or it reads as a lopsided ask, not a
# realistic trade either side would actually consider.
_FAIRNESS_MIN_RATIO = 0.55


def _is_starter(player: Dict[str, Any]) -> bool:
    return (player.get("lineup_slot") or "").upper() not in BENCH_SLOTS


def _proj(player: Dict[str, Any]) -> float:
    return float(player.get("projected_points") or 0.0)


def _group_by_position(roster: List[Dict[str, Any]]):
    starters: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    bench: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for p in roster:
        pos = p.get("position") or "UNKNOWN"
        (starters if _is_starter(p) else bench)[pos].append(p)
    return starters, bench


def _trim(player: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": player.get("name"),
        "position": player.get("position"),
        "team": player.get("team"),
        "projected_points": round(_proj(player), 1),
    }


def find_trade_suggestions(
    my_team_id: Any,
    teams: List[Dict[str, Any]],
    max_suggestions: int = 3,
) -> List[Dict[str, Any]]:
    """Find real, two-way, value-grounded trade suggestions.

    `teams` is the league's real roster list (each item: team_id,
    team_name, roster -- roster entries need `position`, `lineup_slot`,
    `projected_points`, `name`, `team`; this is exactly what
    `espn_service_enhanced.get_league_teams` already returns, and what
    league_management_service builds for Yahoo).

    For each other team, this looks for a real bench player of theirs who
    out-projects one of MY real starters at the same position (a genuine
    upgrade for me), then looks for a real bench player of MINE who
    out-projects one of THEIR real starters at a different position (a
    genuine upgrade for them) -- so the suggestion is symmetric: something
    they'd plausibly accept, not just a one-sided ask. Both value AND
    fairness (the two swapped players' real projections within
    `_FAIRNESS_MIN_RATIO` of each other) gate every suggestion.
    """
    my_team = next((t for t in teams if str(t.get("team_id")) == str(my_team_id)), None)
    if not my_team:
        return []

    my_starters, my_bench = _group_by_position(my_team.get("roster") or [])
    suggestions: List[Dict[str, Any]] = []

    for team in teams:
        if str(team.get("team_id")) == str(my_team_id):
            continue
        their_starters, their_bench = _group_by_position(team.get("roster") or [])

        # What could I get: a real player on their bench who beats my
        # weakest real starter at that position. Track the biggest real
        # projection gap across positions so the most valuable upgrade
        # this team can actually offer wins, not just the first one found.
        upgrade_for_me: Optional[Dict[str, Any]] = None
        upgrade_pos: Optional[str] = None
        my_weakest_at_pos: Optional[Dict[str, Any]] = None
        best_gap = -1.0
        for pos, my_starters_at_pos in my_starters.items():
            if not my_starters_at_pos:
                continue
            my_weakest = min(my_starters_at_pos, key=_proj)
            candidates = [
                p for p in their_bench.get(pos, [])
                if _proj(p) > _proj(my_weakest) + _UPGRADE_MARGIN
            ]
            if not candidates:
                continue
            best = max(candidates, key=_proj)
            gap = _proj(best) - _proj(my_weakest)
            if gap > best_gap:
                best_gap = gap
                upgrade_for_me = best
                upgrade_pos = pos
                my_weakest_at_pos = my_weakest

        if upgrade_for_me is None or upgrade_pos is None or my_weakest_at_pos is None:
            continue

        # What would they want back: a real player on MY bench who beats
        # one of THEIR real starters at some other position.
        counter_offer: Optional[Dict[str, Any]] = None
        their_weakest_countered: Optional[Dict[str, Any]] = None
        for their_pos, their_starters_at_pos in their_starters.items():
            if their_pos == upgrade_pos or not their_starters_at_pos:
                continue
            their_weakest = min(their_starters_at_pos, key=_proj)
            candidates = [
                p for p in my_bench.get(their_pos, [])
                if _proj(p) > _proj(their_weakest) + _UPGRADE_MARGIN
            ]
            if not candidates:
                continue
            counter_offer = max(candidates, key=_proj)
            their_weakest_countered = their_weakest
            break

        if counter_offer is None or their_weakest_countered is None:
            continue

        give_value = _proj(counter_offer)
        get_value = _proj(upgrade_for_me)
        if give_value <= 0 or get_value <= 0:
            continue
        ratio = min(give_value, get_value) / max(give_value, get_value)
        if ratio < _FAIRNESS_MIN_RATIO:
            continue

        suggestions.append(
            {
                "team_id": team.get("team_id"),
                "team_name": team.get("team_name"),
                "you_send": _trim(counter_offer),
                "you_receive": _trim(upgrade_for_me),
                "reasoning": (
                    f"{upgrade_for_me.get('name')} projects {round(get_value, 1)} pts on "
                    f"{team.get('team_name')}'s bench vs your {my_weakest_at_pos.get('name')}'s "
                    f"{round(_proj(my_weakest_at_pos), 1)} at {upgrade_pos} -- a real upgrade. In "
                    f"return, {counter_offer.get('name')} ({round(give_value, 1)} proj) out-projects "
                    f"their {their_weakest_countered.get('name')} "
                    f"({round(_proj(their_weakest_countered), 1)}) at {their_weakest_countered.get('position')}, "
                    f"so it's a real value-for-value swap, not a one-sided ask."
                ),
                "value_ratio": round(ratio, 2),
            }
        )

    suggestions.sort(key=lambda s: s["value_ratio"], reverse=True)
    return suggestions[:max_suggestions]
