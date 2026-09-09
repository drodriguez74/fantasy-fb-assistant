"""Per-league starter-requirement math, shared by the in-season grading
and waiver-wire code.

Extracted from the (now removed) draft assistant service, which is where
this logic originally lived -- `roster_grading.py`, `waiver_wire_service.py`
and `post_draft_analysis_service.py` all depended on it, so it outlives the
draft feature. Pure function, no state.
"""

from typing import Any, Dict

# FLEX slots are folded into one of these when computing effective need.
FLEX_ELIGIBLE_POSITIONS = ("RB", "WR", "TE")


def effective_position_requirements(
    position_counts: Dict[str, int],
    league_settings: Dict[str, Any],
) -> Dict[str, int]:
    """Real per-position starter requirement for the connected league, with
    FLEX slots folded into whichever of RB/WR/TE currently has the largest
    shortfall against what's been rostered so far -- i.e. each FLEX slot
    counts toward whichever position is thinnest at the time it's
    considered, rather than being ignored or split evenly across all three
    regardless of actual roster construction. This is a simplification
    (real lineups don't pre-assign a FLEX slot to one position), but it's
    an explicit, documented heuristic, not a fabrication -- and it only
    affects RB/WR/TE; every other real starter requirement (QB/K/DEF/any
    other slot the league carries) passes through unchanged.
    """
    starters = dict(league_settings.get("starters", {}) or {})
    flex_count = starters.pop("FLEX", 0)

    flex_eligible_requirements = {
        pos: starters.get(pos, 0) for pos in FLEX_ELIGIBLE_POSITIONS
    }
    for _ in range(flex_count):
        thinnest = max(
            FLEX_ELIGIBLE_POSITIONS,
            key=lambda pos: flex_eligible_requirements[pos] - position_counts.get(pos, 0),
        )
        flex_eligible_requirements[thinnest] += 1

    merged = dict(starters)
    merged.update(flex_eligible_requirements)
    return merged
