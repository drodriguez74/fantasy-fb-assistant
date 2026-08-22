"""Canonical, cross-platform fantasy scoring-rules shape.

Real leagues score far more than points-per-reception: they reward or
penalize pass completions/incompletions/attempts, passing/rushing/receiving
yards and touchdowns, interceptions, fumbles lost, etc, each independently.
A real, documented example (confirmed live against Sleeper's public API,
league 289646328504385536): Sleeper's `scoring_settings` dict carries
`pass_cmp` (points per completion) and `pass_att` (points per attempt) as
independent, non-zero-capable knobs distinct from `rec` (points per
reception) -- some real leagues set these to reward accurate, efficient QBs
over high-volume ones (e.g. +0.5 per completion, -0.5 per incompletion).

This module defines one canonical shape that both
sleeper_service.parse_league_settings and
espn_service_enhanced.get_scoring_and_roster_settings populate from their
platform's real, raw scoring settings, so draft_assistant_service and
ai_service can reason about a league's real scoring rules the same way
regardless of which platform a league is connected through -- mirroring
the existing {starters, bench, roster_size, points_per_reception, source}
cross-platform shape those two modules already produce.
"""

from typing import Any, Dict, List, Optional


# Canonical categories/stats this app distinguishes. Deliberately not
# exhaustive of every stat either platform can score (e.g. no IDP, no
# kicking/punting detail, no per-yardage-bucket bonuses) -- these are the
# major QB/RB/WR/TE-relevant categories, enough to make the passing-
# accuracy example (and receiving/rushing yards+TDs, INT, fumbles) real
# and correct, matching this app's existing QB/RB/WR/TE/K/DEF position set.
CANONICAL_CATEGORIES = ("passing", "rushing", "receiving", "fumbles")


def default_scoring_rules(source: str = "fallback_standard") -> Dict[str, Any]:
    """Explicit, named Standard-scoring fallback -- the same honest-fallback
    pattern DraftAssistantService.FALLBACK_ROSTER_REQUIREMENTS uses for
    points_per_reception (0.0), extended to the rest of the major stat
    categories using their common real-world Standard-league point values
    (4pt passing TD at 1pt/25yd, 6pt rushing/receiving TD at 1pt/10yd,
    -2 per INT thrown, -2 per fumble lost, 0 points per reception/
    completion/incompletion/attempt/target). Used only when no real
    per-league scoring settings were fetched -- never presented as if it
    were a specific league's real, confirmed data.
    """
    return {
        "passing": {
            "completion": 0.0,
            "incompletion": 0.0,
            "attempt": 0.0,
            "yard": 0.04,
            "td": 4.0,
            "interception": -2.0,
        },
        "rushing": {
            "attempt": 0.0,
            "yard": 0.1,
            "td": 6.0,
        },
        "receiving": {
            "reception": 0.0,  # implicit Standard (non-PPR); overwritten below by the real points_per_reception
            "yard": 0.1,
            "td": 6.0,
            "target": 0.0,
        },
        "fumbles": {
            "lost": -2.0,
        },
        "source": source,
    }


# Sleeper's real `scoring_settings` dict keys (stat abbreviation -> points),
# verified live against api.sleeper.app/v1/league/<id> -- confirmed real
# keys include pass_cmp, pass_att, pass_int, pass_td, pass_yd, rush_yd,
# rush_td, rush_att, rec, rec_td, rec_yd, fum_lost among many others.
# pass_inc (points per incomplete pass) is not present on every league's
# response (real leagues that don't override it simply omit the key rather
# than sending an explicit 0.0), so it's read defensively with .get().
_SLEEPER_KEY_MAP = {
    ("passing", "completion"): "pass_cmp",
    ("passing", "incompletion"): "pass_inc",
    ("passing", "attempt"): "pass_att",
    ("passing", "yard"): "pass_yd",
    ("passing", "td"): "pass_td",
    ("passing", "interception"): "pass_int",
    ("rushing", "attempt"): "rush_att",
    ("rushing", "yard"): "rush_yd",
    ("rushing", "td"): "rush_td",
    ("receiving", "reception"): "rec",
    ("receiving", "yard"): "rec_yd",
    ("receiving", "td"): "rec_td",
    ("receiving", "target"): "rec_tgt",
    ("fumbles", "lost"): "fum_lost",
}


def scoring_rules_from_sleeper(scoring_settings: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Build the canonical scoring-rules shape from Sleeper's real,
    already-fetched `scoring_settings` dict (see
    sleeper_service.parse_league_settings, which already pulls `rec` out
    of this same dict for points_per_reception -- this reads the rest of
    it instead of discarding it).
    """
    rules = default_scoring_rules(source="sleeper")
    scoring_settings = scoring_settings or {}
    for (category, stat), sleeper_key in _SLEEPER_KEY_MAP.items():
        if sleeper_key in scoring_settings:
            rules[category][stat] = float(scoring_settings.get(sleeper_key) or 0.0)
    return rules


# ESPN statId -> canonical (category, stat), grounded in the installed
# espn_api package's own id->abbr table
# (espn_api/football/constant.py::SETTINGS_SCORING_FORMAT_MAP -- read
# directly from the installed 0.46.0 package rather than guessed from
# memory) so these ids are verified real, not assumed:
#   0  PA    "Each Pass Attempted"     -> passing.attempt
#   1  PC    "Each Pass Completed"     -> passing.completion
#   2  INC   "Each Incomplete Pass"    -> passing.incompletion
#   3  PY    "Passing Yards"           -> passing.yard
#   4  PTD   "TD Pass"                 -> passing.td
#   20 INTT  "Interceptions Thrown"    -> passing.interception
#   23 RA    "Rushing Attempts"        -> rushing.attempt
#   24 RY    "Rushing Yards"           -> rushing.yard
#   25 RTD   "TD Rush"                 -> rushing.td
#   42 REY   "Receiving Yards"         -> receiving.yard
#   43 RETD  "TD Reception"            -> receiving.td
#   53 REC   "Each reception"          -> receiving.reception (the same id
#            get_scoring_and_roster_settings already reads for points_per_reception)
#   58 RET   "Receiving Target"        -> receiving.target
#   72 FUML  "Total Fumbles Lost"      -> fumbles.lost
# The long tail of kicking/defense/punter/head-coach ids in that table
# aren't part of this app's QB/RB/WR/TE/K/DEF position set and are left out.
ESPN_STAT_ID_MAP: Dict[int, Any] = {
    0: ("passing", "attempt"),
    1: ("passing", "completion"),
    2: ("passing", "incompletion"),
    3: ("passing", "yard"),
    4: ("passing", "td"),
    20: ("passing", "interception"),
    23: ("rushing", "attempt"),
    24: ("rushing", "yard"),
    25: ("rushing", "td"),
    42: ("receiving", "yard"),
    43: ("receiving", "td"),
    53: ("receiving", "reception"),
    58: ("receiving", "target"),
    72: ("fumbles", "lost"),
}


def scoring_rules_from_espn(scoring_format: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Build the canonical scoring-rules shape from ESPN's real
    `Settings.scoring_format` list (see
    espn_service_enhanced.get_scoring_and_roster_settings, which already
    scans this same list for statId 53 for points_per_reception -- this
    reads the rest of it instead of discarding it)."""
    rules = default_scoring_rules(source="espn")
    for item in scoring_format or []:
        if not isinstance(item, dict):
            continue
        target = ESPN_STAT_ID_MAP.get(item.get("id"))
        if target is None:
            continue
        category, stat = target
        rules[category][stat] = float(item.get("points") or 0.0)
    return rules


# Raw per-stat-count field names this app uses when a player record
# legitimately carries un-scored raw projections (see
# draft_assistant_service._calculate_player_values for which platforms/
# fields actually populate these today -- currently none in production
# data, same honest situation as the pre-existing `projected_receptions`
# path this generalizes).
_STAT_COUNT_TO_RULE = {
    "completions": ("passing", "completion"),
    "incompletions": ("passing", "incompletion"),
    "pass_attempts": ("passing", "attempt"),
    "pass_yards": ("passing", "yard"),
    "pass_tds": ("passing", "td"),
    "interceptions": ("passing", "interception"),
    "rush_attempts": ("rushing", "attempt"),
    "rush_yards": ("rushing", "yard"),
    "rush_tds": ("rushing", "td"),
    "receptions": ("receiving", "reception"),
    "rec_yards": ("receiving", "yard"),
    "rec_tds": ("receiving", "td"),
    "targets": ("receiving", "target"),
    "fumbles_lost": ("fumbles", "lost"),
}


def calculate_points_from_stats(stat_counts: Dict[str, float], scoring_rules: Optional[Dict[str, Any]]) -> float:
    """Compute total fantasy points for a raw per-stat-count dict (e.g.
    {"completions": 380, "incompletions": 190, "pass_yards": 4500, ...})
    against a canonical scoring_rules dict, by multiplying each present
    stat count by its real per-unit point value and summing. This is the
    same "count * rate" arithmetic the pre-existing reception-only
    adjustment already used (`receptions * points_per_reception`),
    generalized to every category this module maps.
    """
    rules = scoring_rules or default_scoring_rules()
    stat_counts = stat_counts or {}
    total = 0.0
    for stat_name, (category, stat) in _STAT_COUNT_TO_RULE.items():
        count = stat_counts.get(stat_name)
        if not count:
            continue
        rate = (rules.get(category) or {}).get(stat, 0.0) or 0.0
        total += count * rate
    return total


def scoring_rules_from_league_scoring(config: Any) -> Dict[str, Any]:
    """Build the canonical scoring-rules shape from a manually-configured
    LeagueScoring row (see app.models.league_scoring.LeagueScoring, written
    by POST /league-scoring/configure) -- the same canonical shape
    scoring_rules_from_sleeper/scoring_rules_from_espn build from each
    platform's real auto-detected settings, so draft_assistant_service can
    layer a manual override on top of (or in place of) auto-detected
    settings without the rest of the app needing to know whether a
    league's scoring rules came from a platform's live API or from a
    user's own hand-entered configuration. Takes the ORM row directly
    (duck-typed, like the rest of this module takes each platform's raw
    shape) rather than importing the model here, to keep this module free
    of a model-layer dependency.

    LeagueScoring stores *_yards_per_point the way ESPN/Sleeper/Yahoo
    present it to end users -- "yards needed for 1 point", e.g. 25.0 for
    "1 point per 25 passing yards" -- while the canonical shape wants
    points per single yard (see default_scoring_rules: 0.04 == 1/25).
    This inverts each rate, guarding the pathological zero-yards-per-point
    case rather than dividing by zero.
    """
    def _rate(yards_per_point: Optional[float]) -> float:
        return 1.0 / yards_per_point if yards_per_point else 0.0

    return {
        "passing": {
            "completion": config.completion_points or 0.0,
            "incompletion": config.incompletion_points or 0.0,
            "attempt": 0.0,
            "yard": _rate(config.passing_yards_per_point),
            "td": config.passing_td_points or 0.0,
            "interception": config.passing_int_points or 0.0,
        },
        "rushing": {
            "attempt": config.carry_points or 0.0,
            "yard": _rate(config.rushing_yards_per_point),
            "td": config.rushing_td_points or 0.0,
        },
        "receiving": {
            "reception": config.reception_points or 0.0,
            "yard": _rate(config.receiving_yards_per_point),
            "td": config.receiving_td_points or 0.0,
            "target": config.target_points or 0.0,
        },
        "fumbles": {
            "lost": config.fumble_lost_points or 0.0,
        },
        "source": "manual_override",
    }


def describe_scoring_rules(rules: Optional[Dict[str, Any]]) -> str:
    """Human-readable, LLM-prompt-ready summary of the ways a league's real
    scoring deviates from bare Standard scoring -- e.g. "rewards completed
    passes (+0.5) and penalizes incomplete passes (-0.5)". Only surfaces
    rules that actually differ from default_scoring_rules(), so a genuinely
    Standard league doesn't get a paragraph of "0 points per X" noise, and
    a real non-zero rule is stated as a real number, not hedged.
    """
    if not rules:
        return ""

    baseline = default_scoring_rules()
    notes = []

    passing = rules.get("passing", {})
    if passing.get("completion"):
        notes.append(f"{passing['completion']:+g} points per completed pass")
    if passing.get("incompletion"):
        notes.append(f"{passing['incompletion']:+g} points per incomplete pass")
    if passing.get("attempt"):
        notes.append(f"{passing['attempt']:+g} points per pass attempt")
    if passing.get("yard") and passing["yard"] != baseline["passing"]["yard"]:
        notes.append(f"{passing['yard']:g} points per passing yard")
    if passing.get("td") and passing["td"] != baseline["passing"]["td"]:
        notes.append(f"{passing['td']:g} points per passing TD")
    if passing.get("interception") and passing["interception"] != baseline["passing"]["interception"]:
        notes.append(f"{passing['interception']:+g} points per interception thrown")

    rushing = rules.get("rushing", {})
    if rushing.get("td") and rushing["td"] != baseline["rushing"]["td"]:
        notes.append(f"{rushing['td']:g} points per rushing TD")

    receiving = rules.get("receiving", {})
    if receiving.get("td") and receiving["td"] != baseline["receiving"]["td"]:
        notes.append(f"{receiving['td']:g} points per receiving TD")
    if receiving.get("target"):
        notes.append(f"{receiving['target']:+g} points per target")

    fumbles = rules.get("fumbles", {})
    if fumbles.get("lost") and fumbles["lost"] != baseline["fumbles"]["lost"]:
        notes.append(f"{fumbles['lost']:+g} points per fumble lost")

    return "; ".join(notes)
