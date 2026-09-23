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
    FLEX slots folded into RB/WR/TE. Every other real starter requirement
    (QB/K/DEF/any other slot the league carries) passes through unchanged.

    FLEX slots are first credited to positions whose rostered depth already
    exceeds their base requirement (largest surplus first) -- those players
    are what actually fills FLEX. Only FLEX slots no surplus can cover fall
    through to the thinnest position (largest shortfall), i.e. where the
    roster really does need another body. Before, every FLEX slot went to
    the thinnest position regardless of surplus: a real Yahoo roster with 6
    RBs for 1 RB slot and 1 TE for 1 TE slot got both FLEX slots assigned
    to TE and was told it needed 3 TEs. A simplification (real lineups
    don't pre-assign a FLEX slot), but an explicit heuristic, not a
    fabrication.
    """
    starters = dict(league_settings.get("starters", {}) or {})
    flex_count = starters.pop("FLEX", 0)

    flex_eligible_requirements = {
        pos: starters.get(pos, 0) for pos in FLEX_ELIGIBLE_POSITIONS
    }
    for _ in range(flex_count):
        surplus = {
            pos: position_counts.get(pos, 0) - flex_eligible_requirements[pos]
            for pos in FLEX_ELIGIBLE_POSITIONS
        }
        deepest = max(FLEX_ELIGIBLE_POSITIONS, key=lambda pos: surplus[pos])
        if surplus[deepest] > 0:
            flex_eligible_requirements[deepest] += 1
            continue
        thinnest = max(
            FLEX_ELIGIBLE_POSITIONS,
            key=lambda pos: flex_eligible_requirements[pos] - position_counts.get(pos, 0),
        )
        flex_eligible_requirements[thinnest] += 1

    merged = dict(starters)
    merged.update(flex_eligible_requirements)
    return merged
