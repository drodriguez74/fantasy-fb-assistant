"""
Shared, stateless grading helpers.

Extracted from `PostDraftAnalysisService._grade_from_score` so that both the
real post-draft analysis path and the mock-draft grading path
(`mock_draft_service.py`) use one implementation of the score -> letter grade
thresholds instead of two copies that could drift apart.

Also holds the shared value-vs-ADP and bye-week-collision primitives so every
grading path (mock draft, real connected-league roster, post-draft analysis,
Yahoo comprehensive analysis) can combine composition + value + bye-week
signals into one overall grade the same way, instead of composition-only
letter grades with value/bye analysis as decorative text.
"""

from typing import Any, Dict, List, Optional

# ESPN's roster fetch (espn_service_enhanced.py::_format_player) is the only
# real source of per-player `projected_points` this app has today -- Yahoo
# and Sleeper's roster methods supply none at all (see roster_grading.py's
# has_real_projections guard). ESPN's value is `projected_total_points`, a
# real SEASON-LONG total, not a per-game rate. Every per-game-shaped
# threshold below (and in roster_grading.py/post_draft_analysis_service.py)
# was written assuming a weekly number (a QB scoring ~18/game, an RB
# ~12/game are normal "good starter" weekly benchmarks) and never updated
# when ESPN's season-total field got wired in -- off by roughly this
# constant, which silently made every ESPN quality check trivially pass
# regardless of real per-game quality. Divide a season-total projection by
# this constant before comparing it against a weekly threshold.
NFL_SEASON_GAMES = 17


def grade_from_score(score: float) -> str:
    """Convert a 0-100 numeric score into a letter grade.

    Thresholds: A >= 90, B >= 80, C >= 70, D >= 60, else F.
    """
    if score >= 90:
        return "A"
    elif score >= 80:
        return "B"
    elif score >= 70:
        return "C"
    elif score >= 60:
        return "D"
    else:
        return "F"


def value_score_from_picks(value_entries: List[Dict[str, Any]]) -> Optional[float]:
    """Average a list of per-pick value_percentage entries (see
    `mock_draft_service._pick_value` / `post_draft_analysis_service
    ._calculate_draft_value` for how value_percentage is computed: ~100 =
    picked at fair market value/ADP, >100 = value, <100 = reach) into one
    0-100 score component.

    value_percentage=100 (fair value) maps to 75 (a "C", i.e. average is
    unremarkable, not automatically good); the same slope that maps
    value_percentage's own "Excellent Value" cutoff (120) to 90 (this
    module's own "A" cutoff) and "Significant Reach" (70) down into F range.

    Entries with value_percentage=None (no ADP/rank/projection data for that
    pick) are excluded rather than counted as 0 or ignored-as-100. Returns
    None (not 0) when nothing is scoreable, so callers can drop the value
    component entirely instead of penalizing a grade for missing data.
    """
    scored = [v["value_percentage"] for v in value_entries if v.get("value_percentage") is not None]
    if not scored:
        return None
    per_pick_scores = [max(0.0, min(100.0, 75.0 + (vp - 100.0) * 0.75)) for vp in scored]
    return round(sum(per_pick_scores) / len(per_pick_scores), 1)


def detect_bye_week_collisions(
    players: List[Dict[str, Any]], requirements: Dict[str, int]
) -> List[Dict[str, Any]]:
    """Flag every week where a position's active (non-bye) player count would
    drop below the number of starters that position requires.

    players: dicts with a normalized `position` (caller's own alias mapping
             already applied, e.g. D/ST -> DEF) and an optional `bye_week`.
    requirements: {position: required_starter_count}, same shape used for
             composition scoring (real per-league starters when available,
             `_FALLBACK_STARTERS` otherwise).

    Returns a list of {"position", "week", "active_count", "required"} for
    every position/week combination where you'd be forced to start fewer
    players than your lineup requires. Players with no `bye_week` are treated
    as always active (never contribute to a collision) rather than assumed
    on bye.
    """
    collisions: List[Dict[str, Any]] = []
    by_position: Dict[str, List[Dict[str, Any]]] = {}
    for player in players:
        position = (player.get("position") or "UNKNOWN").upper()
        by_position.setdefault(position, []).append(player)

    for position, required in requirements.items():
        if required <= 0:
            continue
        group = by_position.get(position, [])
        total = len(group)
        if total == 0:
            continue
        weeks = {p.get("bye_week") for p in group if p.get("bye_week")}
        for week in weeks:
            on_bye = sum(1 for p in group if p.get("bye_week") == week)
            active = total - on_bye
            if active < required:
                collisions.append(
                    {
                        "position": position,
                        "week": week,
                        "active_count": active,
                        "required": required,
                    }
                )
    return sorted(collisions, key=lambda c: (c["week"], c["position"]))


def bye_week_score(collisions: List[Dict[str, Any]]) -> float:
    """Map bye-week collisions to a 0-100 score component (100 = no
    collisions). A complete wipeout at a position (active_count == 0, e.g.
    your only two QBs share a bye) costs more than a partial shortfall
    (e.g. 1 of 2 required starters left standing).
    """
    if not collisions:
        return 100.0
    penalty = 0.0
    for collision in collisions:
        shortfall = collision["required"] - collision["active_count"]
        penalty += 15.0 if collision["active_count"] == 0 else 8.0 * shortfall
    return max(0.0, 100.0 - penalty)


DEFAULT_COMPONENT_WEIGHTS = {"composition": 0.5, "value": 0.35, "bye_weeks": 0.15}


def value_and_bye_strengths_weaknesses(
    position_breakdown: Dict[str, Any],
    bye_collisions: Optional[List[Dict[str, Any]]] = None,
    value_entries: Optional[List[Dict[str, Any]]] = None,
    top_n: int = 3,
) -> Dict[str, List[str]]:
    """Real, data-driven strengths/weaknesses from the same signals that now
    drive the grade itself (composition vs. real per-league requirements,
    ADP-vs-pick value, bye-week collisions) -- instead of the generic,
    hardcoded "player_count >= N and avg_projection >= M" heuristics
    (`mock_draft_service`/`roster_grading`/`post_draft_analysis_service` each
    had their own near-identical copy of that instead) which never mentioned
    a specific pick or bye week regardless of what actually happened in the
    draft.

    position_breakdown: {position: {"players_drafted", "recommended_minimum",
        "needs_attention", "overstocked", ...}} -- the same dict every
        composition-scoring function here already returns, already computed
        against real per-league starter requirements when available.
    bye_collisions: `detect_bye_week_collisions`'s output, or None/empty if
        not computed for this context.
    value_entries: per-pick dicts with `player_name`/`position` plus either
        `pick` or `round`, and `value_percentage` (None entries are skipped).
        Pass None when there's no ADP/value signal available (e.g. a live
        roster snapshot with no draft-pick context) rather than an empty
        list -- both are treated the same (value section omitted) but None
        documents at the call site that it was never computed, not just empty.
    top_n: max number of value-based strengths/weaknesses to surface, so one
        exceptional or disastrous position doesn't crowd out every other
        signal.

    Returns {"strengths": [...], "weaknesses": [...]} of short, specific
    human-readable sentences, ready to merge with any additional
    quality-aware (e.g. avg projected points) checks a caller still wants to
    run on top.
    """
    strengths: List[str] = []
    weaknesses: List[str] = []

    for position, info in (position_breakdown or {}).items():
        drafted = info.get("players_drafted")
        required = info.get("recommended_minimum")
        if info.get("needs_attention"):
            weaknesses.append(
                f"{position} is below your league's required depth ({drafted}/{required})."
            )
        elif info.get("overstocked"):
            strengths.append(
                f"{position} has extra depth beyond your starting requirement ({drafted} rostered, {required} required)."
            )

    scored = [v for v in (value_entries or []) if v.get("value_percentage") is not None]
    steals = sorted(
        (v for v in scored if v["value_percentage"] >= 110),
        key=lambda v: v["value_percentage"],
        reverse=True,
    )[:top_n]
    reaches = sorted(
        (v for v in scored if v["value_percentage"] < 90),
        key=lambda v: v["value_percentage"],
    )[:top_n]

    for v in steals:
        spot = v.get("pick") or v.get("round")
        spot_label = f"pick {spot}" if v.get("pick") else f"round {spot}"
        strengths.append(
            f"{v.get('player_name', 'Unknown')} ({v.get('position', '?')}) was real value at {spot_label} "
            f"({v['value_percentage']:.0f}% of expected draft cost)."
        )
    for v in reaches:
        spot = v.get("pick") or v.get("round")
        spot_label = f"pick {spot}" if v.get("pick") else f"round {spot}"
        weaknesses.append(
            f"{v.get('player_name', 'Unknown')} ({v.get('position', '?')}) was a reach at {spot_label} "
            f"({v['value_percentage']:.0f}% of expected draft cost)."
        )

    for c in bye_collisions or []:
        if c["active_count"] == 0:
            weaknesses.append(
                f"Week {c['week']}: every rostered {c['position']} is on bye -- zero active starters."
            )
        else:
            weaknesses.append(
                f"Week {c['week']}: only {c['active_count']} of {c['required']} required {c['position']}s active -- the rest are on bye."
            )

    return {"strengths": strengths, "weaknesses": weaknesses}


def bench_depth_notes(
    players: List[Dict[str, Any]],
    requirements: Dict[str, int],
    thin_ratio: float = 0.5,
    thin_floor: float = 8.0,
) -> List[str]:
    """Flag positions where headcount looks fine but the players beyond your
    real per-league starter count are meaningfully worse than your starters
    -- a "stud, stud, then a cliff" roster construction risk that a plain
    headcount + average-projected-points check can silently average away
    (e.g. 5 rostered RBs at a 12-points-per-player average reads as
    "Excellent depth" even when that's two 20-point starters and three
    2-point committee dart-throws with real injury exposure).

    players: dicts with `position` and `projected_points` (0/None treated
        as 0 -- a player with no real projection can't misrepresent this
        check as either strong or weak).
    requirements: {position: required_starter_count}, same shape every
        composition-scoring function here already uses.
    thin_ratio / thin_floor: a position is flagged only when the backup-tier
        average is BOTH under `thin_ratio` of the starter-tier average AND
        under the absolute `thin_floor` -- catches a real cliff without
        flagging positions where even the "backups" are still solid.

    Returns a list of ready-to-use weakness sentences (empty when nothing's
    flagged, including when a position has no players beyond its starter
    count at all -- that's a depth problem `needs_attention` already covers
    elsewhere, not this check's job).
    """
    by_position: Dict[str, List[float]] = {}
    for player in players:
        position = (player.get("position") or "UNKNOWN").upper()
        # Normalize to a per-game rate -- see NFL_SEASON_GAMES docstring
        # above. thin_floor/thin_ratio are weekly-shaped, and ESPN's real
        # projected_points is a season total; without this, backup_avg
        # never dips under thin_floor for any real ESPN roster, and this
        # check silently never fires.
        raw = (player.get("projected_points") or 0) / NFL_SEASON_GAMES
        by_position.setdefault(position, []).append(raw)

    notes: List[str] = []
    for position, required in requirements.items():
        points = sorted(by_position.get(position, []), reverse=True)
        if required <= 0 or len(points) <= required:
            continue
        starters, backups = points[:required], points[required:]
        starter_avg = sum(starters) / len(starters) if starters else 0.0
        backup_avg = sum(backups) / len(backups)
        if starter_avg > 0 and backup_avg < starter_avg * thin_ratio and backup_avg < thin_floor:
            notes.append(
                f"{position} depth beyond your top {required} is thin (backup avg "
                f"{backup_avg:.1f} pts vs {starter_avg:.1f} for your starters) -- "
                "an injury to a starter would hurt."
            )
    return notes


def combined_grade(
    composition_score: float,
    value_score: Optional[float] = None,
    bye_weeks_score: Optional[float] = None,
    weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Combine composition/value/bye-week component scores into one overall
    score and letter grade, instead of a composition-only grade with
    value/bye analysis relegated to decorative text.

    A component that's None (no ADP/rank data to compute value_score; no
    bye_week data to compute bye_weeks_score) is dropped and the remaining
    weights renormalized -- missing data shrinks the basis for the grade,
    it never gets silently treated as a 0 or a 100.
    """
    components = {"composition": composition_score}
    if value_score is not None:
        components["value"] = value_score
    if bye_weeks_score is not None:
        components["bye_weeks"] = bye_weeks_score

    weights = weights or DEFAULT_COMPONENT_WEIGHTS
    used_weights = {name: weights.get(name, 0.0) for name in components}
    total_weight = sum(used_weights.values()) or 1.0

    overall = sum(components[name] * used_weights[name] for name in components) / total_weight

    return {
        "overall_score": round(overall, 1),
        "grade": grade_from_score(overall),
        "components": {name: round(value, 1) for name, value in components.items()},
    }
