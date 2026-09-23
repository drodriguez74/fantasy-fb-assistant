"""Real per-player weekly projections for platforms that don't expose one.

Yahoo's public API has real team-level projected totals but no per-player
weekly projection anywhere (confirmed live 2026-09-23 -- see
yahoo_service.get_week_matchup's docstring), which left Yahoo's This Week
screen without a lineup optimizer or start/sit calls. Sleeper's public
projections feed (RotoWire-sourced, no auth) does carry one per player per
week, with the projected stat line alongside the points -- so this module
matches a Yahoo lineup against that feed and scores each projected stat
line with the league's own real scoring rules.

Scoring: Sleeper's `pts_std` covers every stat it projects (including K,
DEF, 2-pt conversions) at Sleeper's standard values. Rather than rescoring
from scratch (the canonical scoring_rules shape has no K/DEF categories),
each player's `pts_std` is corrected by `count * (league_rate - sleeper
standard rate)` for every canonical stat the league actually scores
differently. Sleeper's standard rates were confirmed empirically against
the live feed (2026-09-23): recomputing `pts_std` for every projected QB
from its stat line matched to within 0.05 pts only with -1 per INT (not the
-2 in this app's own Standard default); `pts_ppr - pts_std == rec` exactly.
Yahoo leagues can also score stats outside the canonical rules (first
downs, 40+ yard plays, pick-sixes); Sleeper projects those too, so they're
added via YAHOO_EXTRA_STATS. K and DEF points stay on Sleeper's standard
scoring -- their per-category projections aren't in the feed -- and that's
disclosed on the response.
"""
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.services.scoring_rules import _SLEEPER_KEY_MAP

logger = logging.getLogger(__name__)

# The un-versioned host path -- `/v1/projections/...` returns only empty
# per-player stubs (confirmed live), not real projections.
_PROJECTIONS_URL = "https://api.sleeper.app/projections/nfl/{season}/{week}"
_SEASON_PROJECTIONS_URL = "https://api.sleeper.app/projections/nfl/{season}"
_POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")

# Sleeper's own standard-scoring rates behind `pts_std`, per canonical
# (category, stat) -- see module docstring for how these were confirmed.
SLEEPER_STANDARD_RATES: Dict[Tuple[str, str], float] = {
    ("passing", "completion"): 0.0,
    ("passing", "incompletion"): 0.0,
    ("passing", "attempt"): 0.0,
    ("passing", "yard"): 0.04,
    ("passing", "td"): 4.0,
    ("passing", "interception"): -1.0,
    ("rushing", "attempt"): 0.0,
    ("rushing", "yard"): 0.1,
    ("rushing", "td"): 6.0,
    ("receiving", "reception"): 0.0,
    ("receiving", "yard"): 0.1,
    ("receiving", "td"): 6.0,
    ("receiving", "target"): 0.0,
    ("fumbles", "lost"): -2.0,
}

# Yahoo stat_ids a league can score that the canonical rules don't model,
# mapped to the Sleeper projected-stat key(s) that count the same thing.
# Sleeper's standard `pts_std` gives these 0 points (the -1 INT recompute
# above matched without them), except 2-pt conversions at 2.
YAHOO_EXTRA_STATS: Dict[int, Tuple[Tuple[str, ...], float]] = {
    16: (("pass_2pt", "rush_2pt", "rec_2pt"), 2.0),  # 2-point conversions
    58: (("pass_int_td",), 0.0),                      # pick-sixes thrown
    59: (("pass_cmp_40p",), 0.0),                     # 40+ yard completions
    61: (("rush_40p",), 0.0),                         # 40+ yard runs
    63: (("rec_40p",), 0.0),                          # 40+ yard receptions
    79: (("pass_fd",), 0.0),                          # passing first downs
    80: (("rec_fd",), 0.0),                           # receiving first downs
    81: (("rush_fd",), 0.0),                          # rushing first downs
}

PROJECTION_SOURCE = "Sleeper (RotoWire) weekly projection"

# Projections move through the week but not minute to minute; one feed
# fetch per (season, week) -- week 0 meaning full season -- every 30 min is
# plenty and keeps the league page's parallel requests from each
# re-downloading 1-3MB.
_CACHE_TTL_SECONDS = 1800
_cache: Dict[Tuple[int, int], Tuple[float, List[Dict[str, Any]]]] = {}


async def fetch_weekly_projections(season: int, week: int) -> List[Dict[str, Any]]:
    """Sleeper's real weekly projections for every skill position + K/DEF.
    Returns [] on any failure -- callers treat that as "no projections",
    never as a real zero."""
    return await _fetch(_PROJECTIONS_URL.format(season=season, week=week), (int(season), int(week)))


async def fetch_season_projections(season: int) -> List[Dict[str, Any]]:
    """Sleeper's real full-season projections (same row shape, season-total
    stat lines) -- the Yahoo counterpart to ESPN's season-long
    `projected_total_points`, used for trade values."""
    return await _fetch(_SEASON_PROJECTIONS_URL.format(season=season), (int(season), 0))


async def _fetch(url: str, cache_key: Tuple[int, int]) -> List[Dict[str, Any]]:
    cached = _cache.get(cache_key)
    if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    params = [("season_type", "regular")] + [("position[]", p) for p in _POSITIONS]
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as e:
        logger.warning("Sleeper projections fetch failed (%s): %s", url, e)
        return []

    rows = [r for r in data if isinstance(r, dict) and isinstance(r.get("stats"), dict)] if isinstance(data, list) else []
    _cache[cache_key] = (time.monotonic(), rows)
    return rows


_SUFFIX_RE = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")


def normalize_name(name: Optional[str]) -> str:
    """'Aaron Jones Sr.' / 'aaron jones' / "D'Andre Swift" -> comparable key."""
    s = (name or "").lower().replace(".", "").replace("'", "").replace("’", "")
    s = _SUFFIX_RE.sub("", s)
    s = re.sub(r"[^a-z ]+", " ", s)
    return " ".join(s.split())


def score_projection(
    stats: Dict[str, Any],
    scoring_rules: Optional[Dict[str, Any]],
    yahoo_stat_values: Optional[Dict[int, float]] = None,
) -> Optional[float]:
    """This player's projected points under the league's real rules.
    `yahoo_stat_values` ({stat_id: points}, from yahoo_service.
    get_league_settings) adds the stats the canonical rules don't cover.
    None when Sleeper has no standard total for them (no projection)."""
    base = stats.get("pts_std")
    if base is None:
        return None
    total = float(base)

    for stat_id, (keys, sleeper_rate) in YAHOO_EXTRA_STATS.items():
        league_rate = (yahoo_stat_values or {}).get(stat_id)
        if league_rate is None or league_rate == sleeper_rate:
            continue
        count = sum(float(stats.get(k) or 0.0) for k in keys)
        total += count * (league_rate - sleeper_rate)

    if not scoring_rules:
        return round(total, 2)

    for (category, stat), sleeper_rate in SLEEPER_STANDARD_RATES.items():
        league_rate = (scoring_rules.get(category) or {}).get(stat)
        if league_rate is None or float(league_rate) == sleeper_rate:
            continue
        stat_key = _SLEEPER_KEY_MAP.get((category, stat))
        count = stats.get(stat_key) if stat_key else None
        if count is None and (category, stat) == ("passing", "incompletion"):
            # Not every projection row carries pass_inc; it's att - cmp.
            if stats.get("pass_att") is not None and stats.get("pass_cmp") is not None:
                count = float(stats["pass_att"]) - float(stats["pass_cmp"])
        if not count:
            continue
        total += float(count) * (float(league_rate) - sleeper_rate)
    return round(total, 2)


def _index(rows: List[Dict[str, Any]]):
    by_name_team: Dict[Tuple[str, str], Dict[str, Any]] = {}
    by_name: Dict[str, List[Dict[str, Any]]] = {}
    defense_by_team: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        player = r.get("player") or {}
        team = (r.get("team") or player.get("team") or "").upper()
        position = (player.get("position") or "").upper()
        if position == "DEF":
            if team:
                defense_by_team[team] = r
            continue
        name = normalize_name(f"{player.get('first_name', '')} {player.get('last_name', '')}")
        if not name:
            continue
        if team:
            by_name_team[(name, team)] = r
        by_name.setdefault(name, []).append(r)
    return by_name_team, by_name, defense_by_team


def attach_projections(
    lineup: List[Dict[str, Any]],
    rows: List[Dict[str, Any]],
    scoring_rules: Optional[Dict[str, Any]],
    yahoo_stat_values: Optional[Dict[int, float]] = None,
) -> List[str]:
    """Fill `projected_points` (and a missing `pro_opponent`) on each lineup
    player in place from the matching Sleeper row. Match is by normalized
    name + NFL team, falling back to name alone only when that name is
    unique in the feed; defenses match by team. Players with no match keep
    `projected_points = None`. Returns the unmatched players' names."""
    by_name_team, by_name, defense_by_team = _index(rows)
    unmatched: List[str] = []
    for p in lineup:
        team = (p.get("team") or "").upper()
        position = (p.get("position") or "").upper()
        if position in ("DEF", "DST", "D/ST"):
            row = defense_by_team.get(team)
        else:
            name = normalize_name(p.get("name"))
            row = by_name_team.get((name, team))
            if row is None and len(by_name.get(name, [])) == 1:
                row = by_name[name][0]

        points = score_projection(row["stats"], scoring_rules, yahoo_stat_values) if row else None
        if points is None:
            unmatched.append(p.get("name") or "Unknown")
            continue
        p["projected_points"] = points
        if not p.get("pro_opponent") and row.get("opponent"):
            p["pro_opponent"] = row["opponent"]
    return unmatched
