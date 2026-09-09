"""
Real Team Analysis grading for connected leagues (ESPN/Yahoo/Sleeper).

Deterministic, no AI calls -- mirrors `mock_draft_service.py`'s approach of
operating on plain player dicts, since a real ESPN/Yahoo/Sleeper roster's
players aren't guaranteed to have a matching local `Player` row. Generalizes
`mock_draft_service._score_composition`'s formula to use a connected league's
REAL starter requirements (from
`espn_service_enhanced.get_scoring_and_roster_settings` or the Sleeper/Yahoo
equivalents) instead of a fixed standard lineup, via
`DraftAssistantService._effective_position_requirements` (already
FLEX-aware). Strengths/weaknesses reuses
`PostDraftAnalysisService._identify_strengths_weaknesses`'s real,
quality-aware (avg `projected_points`, not just raw counts) per-position
rules, adapted from ORM `Player` attribute access to plain dict access.

This intentionally does NOT call `ai_service` -- per explicit direction, real
computed data/formulas are used wherever they're sufficient, which they are
here (every input is a real number already returned by the platform's own
roster fetch).

One narrow, best-effort DB access was added for bye-week grading: none of
ESPN/Yahoo/Sleeper's own roster-fetch dicts carry a `bye_week` field at all
(verified against `espn_service_enhanced._format_player`, which has no such
key), so `_enrich_bye_weeks` backfills it from the local `Player` table by
name, the same by-name-match pattern
`league_management_service._analyze_position_group` already uses. It opens
its own short-lived session (this module still takes no `db` dependency from
callers) and fails silently -- a DB error or a player with no local match
just leaves `bye_week` absent for that player, exactly like real platform
data lacking it, rather than raising or guessing.
"""

import re
from typing import Any, Dict, List, Optional

from app.services.grading import (
    combined_grade,
    detect_bye_week_collisions,
    bye_week_score,
    value_and_bye_strengths_weaknesses,
    bench_depth_notes,
    NFL_SEASON_GAMES,
)
from app.services.roster_requirements import effective_position_requirements

# Same fallback used elsewhere in this codebase when no real per-league
# roster settings are available (see DraftAssistantService.FALLBACK_ROSTER_REQUIREMENTS).
_FALLBACK_STARTERS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1}


# ESPN's own player.position for a defense is "D/ST", but real per-league
# starter requirements (get_scoring_and_roster_settings) already normalize
# that same slot to "DEF" (see espn_service_enhanced.py's own label_map) --
# without this, a real rostered defense was invisible to the requirement
# check (0/1 "DEF" instead of the real 1/1), silently understating the grade.
_POSITION_ALIASES = {"D/ST": "DEF"}


def _position_counts(players: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for player in players:
        position = (player.get("position") or "UNKNOWN").upper()
        position = _POSITION_ALIASES.get(position, position)
        counts[position] = counts.get(position, 0) + 1
    return counts


def _normalize_positions(players: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apply the same `_POSITION_ALIASES` normalization `_position_counts` uses
    (e.g. ESPN's "D/ST" -> "DEF") to a copy of each player dict, so
    `detect_bye_week_collisions` sees the same normalized positions the
    composition/requirements check does instead of a second, divergent
    mapping.
    """
    normalized = []
    for player in players:
        position = (player.get("position") or "UNKNOWN").upper()
        position = _POSITION_ALIASES.get(position, position)
        normalized.append({**player, "position": position})
    return normalized


def _enrich_bye_weeks(players: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Best-effort backfill of `bye_week` from the local `Player` table by
    name, for platforms whose roster-fetch dicts don't already carry it
    (true of all three today -- see module docstring). Only looked up for
    players actually missing `bye_week`, so real platform-provided data (if
    a platform ever adds it) is never overridden. Any failure -- no DB
    reachable, no matching local row -- leaves `bye_week` absent for that
    player rather than raising or guessing.
    """
    if all(player.get("bye_week") for player in players):
        return players

    try:
        from app.db.base import SessionLocal
        from app.models.player import Player
    except Exception:
        return players

    enriched = list(players)
    db = None
    try:
        db = SessionLocal()
        for i, player in enumerate(enriched):
            if player.get("bye_week"):
                continue
            name = player.get("name")
            if not name:
                continue
            match = db.query(Player).filter(Player.name.ilike(f"%{name}%")).first()
            if match is not None and getattr(match, "bye_week", None):
                enriched[i] = {**player, "bye_week": match.bye_week}
    except Exception:
        return players
    finally:
        if db is not None:
            db.close()
    return enriched


def _score_composition(
    position_counts: Dict[str, int], requirements: Dict[str, int]
) -> Dict[str, Any]:
    """Mirrors mock_draft_service._score_composition's exact formula, but
    parameterized by the connected league's real starter requirements
    instead of a hardcoded standard lineup.
    """
    if not requirements:
        requirements = _FALLBACK_STARTERS

    composition_score = 0.0
    position_breakdown: Dict[str, Any] = {}

    for position, required_count in requirements.items():
        if required_count <= 0:
            continue
        actual_count = position_counts.get(position, 0)

        if actual_count >= required_count:
            position_score = min(100, 80 + (actual_count - required_count) * 10)
        else:
            position_score = (actual_count / required_count) * 80

        position_breakdown[position] = {
            "players_drafted": actual_count,
            "recommended_minimum": required_count,
            "depth_score": round(position_score, 1),
            "needs_attention": actual_count < required_count,
            "overstocked": actual_count > required_count + 1,
        }
        composition_score += position_score

    composition_score = composition_score / len(position_breakdown) if position_breakdown else 0.0

    return {
        "composition_score": round(composition_score, 1),
        "position_breakdown": position_breakdown,
    }


def _identify_strengths_weaknesses(
    players: List[Dict[str, Any]], requirements: Optional[Dict[str, int]] = None
) -> Dict[str, List[str]]:
    """Adapted from PostDraftAnalysisService._identify_strengths_weaknesses --
    same real, quality-aware per-position rules (count + avg projected_points),
    ported from ORM Player attribute access to plain dict access so it works
    on any platform's roster dicts without a local DB Player match.

    Quality (`avg_projection`) is computed from only the top
    `requirements[position]` players by projected_points -- i.e. this
    league's real starter count for that position -- not the whole rostered
    group. A user-reported bug (2026-09-05, a real 5-RB roster: two
    legitimate starters + three committee/backup-grade backs) showed why:
    averaging the entire group lets replacement-level depth drag down a
    genuinely strong top end, or (just as often) lets a strong top end paper
    over mediocre depth -- "Excellent RB depth" told the user nothing about
    whether their actual starters were any good. `player_count` (used for
    the headcount-only checks below) still reflects the whole group --
    that's a real, separate "do you have bodies" signal, already
    intentionally distinct from the quality question. Falls back to
    `_FALLBACK_STARTERS` when no real per-league requirements are supplied.

    `projected_points`, when real (ESPN only today -- see NFL_SEASON_GAMES's
    docstring in grading.py), is a season-long total; divided by
    NFL_SEASON_GAMES before comparing against these weekly-shaped
    thresholds.
    """
    position_groups: Dict[str, List[Dict[str, Any]]] = {}
    for player in players:
        position = (player.get("position") or "UNKNOWN").upper()
        position = _POSITION_ALIASES.get(position, position)
        position_groups.setdefault(position, []).append(player)

    effective_requirements = requirements or _FALLBACK_STARTERS

    strengths: List[str] = []
    weaknesses: List[str] = []

    for position, group in position_groups.items():
        starter_count = max(effective_requirements.get(position, 1), 1)
        sorted_group = sorted(group, key=lambda p: p.get("projected_points") or 0, reverse=True)
        starters = sorted_group[:starter_count]
        projections = [(p.get("projected_points") or 0) / NFL_SEASON_GAMES for p in starters]
        avg_projection = sum(projections) / len(projections) if projections else 0.0
        player_count = len(group)

        if position == "QB":
            if player_count >= 2 and avg_projection >= 18:
                strengths.append(f"Strong QB depth with {player_count} quality options")
            elif player_count == 1 and avg_projection < 15:
                weaknesses.append("Weak QB situation - consider backup or upgrade")
            elif player_count == 0:
                weaknesses.append("No QB rostered - critical need")

        elif position == "RB":
            if player_count >= 3 and avg_projection >= 12:
                strengths.append(f"Excellent RB depth with {player_count} backs")
            elif player_count < 2:
                weaknesses.append("Insufficient RB depth - high injury risk")
            elif avg_projection < 8:
                weaknesses.append("RB room lacks upside - consider upgrades")

        elif position == "WR":
            if player_count >= 4 and avg_projection >= 10:
                strengths.append(f"Deep WR corps with {player_count} receivers")
            elif player_count < 3:
                weaknesses.append("Thin at WR - need more depth")
            elif avg_projection < 6:
                weaknesses.append("WR group lacks consistent producers")

        elif position == "TE":
            if player_count >= 1 and avg_projection >= 8:
                strengths.append("Solid TE situation")
            elif avg_projection < 5:
                weaknesses.append("TE position is a concern - consider streaming")
            elif player_count == 0:
                weaknesses.append("No TE rostered")

    skill_players = (
        position_groups.get("RB", []) + position_groups.get("WR", []) + position_groups.get("TE", [])
    )
    if len(skill_players) >= 7:
        strengths.append("Strong overall skill position depth")
    elif len(skill_players) < 5:
        weaknesses.append("Lacks sufficient skill position depth")

    return {"strengths": strengths, "weaknesses": weaknesses}


def grade_roster(
    players: List[Dict[str, Any]], league_settings: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Real, deterministic team-analysis grade for a connected league's roster.

    players: flat list of dicts with at least `position` and `projected_points`
             (every platform's roster formatter already produces this shape).
    league_settings: real {"starters": {...}, ...} from
             get_scoring_and_roster_settings (ESPN) or an equivalent
             Sleeper/Yahoo call; falls back to a standard 1-QB lineup when
             None or empty, same fallback used elsewhere in this codebase.

    Returns {"composition_score": float, "grade": str, "overall_score": float,
             "components": {...}, "bye_week_collisions": [...],
             "position_breakdown": {...}, "strengths": [...], "weaknesses": [...]}.
    `grade`/`overall_score`/`components` reflect the combined
    composition + bye-week grade (see `grading.combined_grade`); the
    original composition-only score is kept under `composition_score` for
    backward compat with existing callers.
    """
    position_counts = _position_counts(players)
    raw_starters = dict((league_settings or {}).get("starters") or {}) or _FALLBACK_STARTERS
    requirements = effective_position_requirements(position_counts, {"starters": raw_starters})

    composition = _score_composition(position_counts, requirements)

    # No ADP/value signal exists in this connected-roster context (it's a
    # snapshot of an already-set roster, not a draft), so combined_grade is
    # called with value_score=None -- composition + bye-weeks only.
    bye_week_players = _enrich_bye_weeks(_normalize_positions(players))
    collisions = detect_bye_week_collisions(bye_week_players, requirements)
    combined = combined_grade(
        composition_score=composition["composition_score"],
        value_score=None,
        bye_weeks_score=bye_week_score(collisions),
    )
    grade = combined["grade"]

    # _identify_strengths_weaknesses's per-position rules lean on avg
    # projected_points, not just counts -- if a platform's roster fetch
    # doesn't supply real per-player projections (true for Yahoo/Sleeper's
    # current roster methods, unlike ESPN which computes this server-side),
    # every avg_projection would silently read as 0 and the *count-only*
    # weakness branches (e.g. "avg_projection < 8") would fire for every
    # position regardless of actual roster quality -- a fabricated-looking
    # signal from missing data, not a real one. Skip it honestly instead.
    has_real_projections = any((p.get("projected_points") or 0) > 0 for p in players)
    sw = (
        _identify_strengths_weaknesses(players, requirements)
        if has_real_projections
        else {"strengths": [], "weaknesses": []}
    )

    # Requirement- and bye-week-based signals: real per-league starter
    # requirements (needs_attention/overstocked, already computed above) and
    # real bye-week collisions, neither of which the count/avg-projection
    # rules above ever look at. Merged in rather than replacing `sw` --
    # both are real, independent signals (a position can meet its starter
    # count and still be low-quality, or vice versa).
    position_breakdown = composition["position_breakdown"]
    needs_attention_positions = {pos for pos, info in position_breakdown.items() if info.get("needs_attention")}
    overstocked_positions = {pos for pos, info in position_breakdown.items() if info.get("overstocked")}

    # sw's per-position rules only look at headcount/avg-projection and have
    # no idea what this league actually requires, so they can call a position
    # "solid"/"deep" while the real required-depth check above flags it as
    # needing attention (or vice versa) -- e.g. "Solid TE situation" alongside
    # "TE is below your league's required depth (1/3)". Let the real,
    # league-aware signal win: drop the legacy per-position entry whenever it
    # contradicts it.
    def _mentions_position(text: str, position: str) -> bool:
        return re.search(rf"\b{re.escape(position)}\b", text) is not None

    sw_strengths = [
        s for s in sw["strengths"]
        if not any(_mentions_position(s, pos) for pos in needs_attention_positions)
    ]
    sw_weaknesses = [
        w for w in sw["weaknesses"]
        if not any(_mentions_position(w, pos) for pos in overstocked_positions)
    ]

    value_sw = value_and_bye_strengths_weaknesses(
        position_breakdown, bye_collisions=collisions
    )
    strengths = sw_strengths + [s for s in value_sw["strengths"] if s not in sw_strengths]
    weaknesses = sw_weaknesses + [w for w in value_sw["weaknesses"] if w not in sw_weaknesses]

    # Catches a "stud, stud, then a cliff" position -- headcount and even
    # the plain average above can both look fine while your actual bench
    # is real injury exposure (see grading.bench_depth_notes docstring).
    weaknesses += bench_depth_notes(_normalize_positions(players), requirements)

    return {
        "composition_score": composition["composition_score"],
        "position_breakdown": composition["position_breakdown"],
        "grade": grade,
        "overall_score": combined["overall_score"],
        "components": combined["components"],
        "bye_week_collisions": collisions,
        "strengths": strengths,
        "weaknesses": weaknesses,
    }
