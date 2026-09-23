"""'This Week' flagship-screen assembly.

Bundles the real weekly matchup box score, both teams' records/standings,
and a deterministic lineup-optimizer pass into one payload for
GET /leagues/{id}/this-week.

ESPN and Yahoo both real today (see espn_service_enhanced /
yahoo_service + CLAUDE.md "Multi-platform league integration"). Sleeper
gets an honest `platform_supported: False` response rather than
fabricated numbers, matching the pattern in leagues.py::get_roster_analysis
-- Sleeper's API exposes no real per-week box score at all (unlike ESPN
and Yahoo, both of which do).

ESPN exposes a real per-player weekly projection (BoxPlayer.projected_
points); Yahoo's public API genuinely does not (confirmed live 2026-09-23
-- see yahoo_service.get_week_matchup's docstring). The YAHOO branch fills
that gap from Sleeper's real weekly projections, scored with the league's
own Yahoo scoring rules (see weekly_projections.py), and runs the same
optimizer/start-sit logic over only the players that actually matched --
an unmatched player is never treated as a 0-point projection. The
scoreboard's team totals and win probability stay Yahoo's own.
"""
import asyncio
from typing import Any, Dict, List, Optional

from app.models.user_league import UserLeague
from app.services.espn_service_enhanced import espn_service_enhanced
from app.services.yahoo_tokens import get_valid_yahoo_token
from app.services.weekly_projections import (
    PROJECTION_SOURCE,
    attach_projections,
    fetch_weekly_projections,
)
from app.services.yahoo_service import yahoo_service

# ESPN bench/IR labels plus Yahoo's ("BN", "IR+") -- without Yahoo's, every
# Yahoo bench player was treated as a starter.
BENCH_SLOTS = {"BE", "IR", "BENCH", "BN", "IR+"}
# Injured-reserve slots: not starters, and not startable bench options
# either -- moving a player off IR takes a roster move, not a lineup swap.
IR_SLOTS = {"IR", "IR+"}
# Flex slot labels that accept any RB/WR/TE: ESPN's and Yahoo's "W/R/T".
FLEX_SLOTS = {"RB/WR/TE", "FLEX", "OP", "W/R/T"}
FLEX_ELIGIBLE_POSITIONS = {"RB", "WR", "TE"}
HEALTHY_STATUSES = {"ACTIVE", "NORMAL", "HEALTHY", ""}


def _is_starter(player: Dict[str, Any]) -> bool:
    slot = (player.get("slot_position") or "").upper()
    return slot not in BENCH_SLOTS and slot != ""


def _slot_accepts(slot: Optional[str], player: Dict[str, Any]) -> bool:
    """Can `player` legally fill starting `slot`?"""
    if not slot:
        return False
    slot_u = slot.upper()
    pos = (player.get("position") or "").upper()
    eligible = {s.upper() for s in player.get("eligible_slots", []) if isinstance(s, str)}
    if slot_u in eligible:
        return True
    if slot_u == pos:
        return True
    if slot_u in FLEX_SLOTS and pos in FLEX_ELIGIBLE_POSITIONS:
        return True
    if slot_u == "WR/TE" and pos in {"WR", "TE"}:
        return True
    return False


def _is_risky(player: Dict[str, Any]) -> bool:
    """Real injury-designation risk: a non-healthy status on a player whose
    game hasn't been played yet this week. Never fabricated -- ESPN's own
    `injuryStatus` field, same one already badged in the UI.
    """
    status = (player.get("injury_status") or "").upper()
    return status not in HEALTHY_STATUSES and float(player.get("game_played") or 0) < 100


def _swap_confidence(delta: float, replacement: Dict[str, Any]) -> str:
    """How much to trust a suggested swap -- purely a function of the real
    projection gap plus the replacement's real injury status. A big
    projected gain from a questionable/doubtful player is exactly the case
    where a raw points-only optimizer (v1) misleads, so injury risk always
    overrides point magnitude here.
    """
    if _is_risky(replacement):
        return "risky"
    if delta >= 5:
        return "strong"
    if delta >= 2:
        return "moderate"
    return "lean"


def optimize_lineup(lineup: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Greedy, deterministic lineup optimizer.

    Walks the current starters weakest-first and, for each, looks for the
    highest-projected bench player who can legally fill that slot and beats
    the incumbent's weekly projection. Purely arithmetic on ESPN's own
    weekly projected points -- no AI, no fabricated inputs. Each suggested
    swap also carries a `confidence` tier (see `_swap_confidence`) so a
    big-looking point gain from an injury-flagged replacement doesn't read
    as equally trustworthy as a clean one -- v1 had no such signal.
    """
    starters = [p for p in lineup if _is_starter(p)]
    bench = [
        p
        for p in lineup
        if not _is_starter(p)
        and (p.get("slot_position") or "").upper() not in IR_SLOTS
        and not p.get("on_bye")
        # a bench player whose game already finished can't help this week
        and float(p.get("game_played") or 0) < 100
    ]

    bench_pool = list(bench)
    swaps: List[Dict[str, Any]] = []

    for starter in sorted(starters, key=lambda p: p.get("projected_points") or 0.0):
        s_proj = float(starter.get("projected_points") or 0.0)
        candidates = [
            b
            for b in bench_pool
            if _slot_accepts(starter.get("slot_position"), b)
            and float(b.get("projected_points") or 0.0) > s_proj + 0.1
        ]
        if not candidates:
            continue
        best = max(candidates, key=lambda b: b.get("projected_points") or 0.0)
        delta = round(float(best.get("projected_points") or 0.0) - s_proj, 1)
        swaps.append(
            {
                "slot": starter.get("slot_position"),
                "bench_out": {
                    "name": starter.get("name"),
                    "position": starter.get("position"),
                    "projected_points": starter.get("projected_points"),
                },
                "start_in": {
                    "name": best.get("name"),
                    "position": best.get("position"),
                    "team": best.get("team"),
                    "projected_points": best.get("projected_points"),
                },
                "delta": delta,
                "confidence": _swap_confidence(delta, best),
            }
        )
        bench_pool.remove(best)

    current_projected = round(sum(float(p.get("projected_points") or 0.0) for p in starters), 1)
    gained = round(sum(s["delta"] for s in swaps), 1)

    return {
        "current_projected": current_projected,
        "optimized_projected": round(current_projected + gained, 1),
        "points_gained": gained,
        "swaps": swaps,
    }


def _best_bench_alternative(slot: Optional[str], bench: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    candidates = [b for b in bench if _slot_accepts(slot, b)]
    if not candidates:
        return None
    return max(candidates, key=lambda b: b.get("projected_points") or 0.0)


def start_sit_confidence(lineup: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Per-starter start/sit confidence -- one real tier per current starter,
    not just the players the optimizer proposes swapping.

    Two real signals, no fabrication: (1) the projection gap to that
    starter's own best real bench alternative at the slot (a comfortable
    gap = confident start, a thin one = a real toss-up ESPN's numbers don't
    resolve), and (2) the starter's own real injury designation -- a
    questionable/doubtful starter whose game hasn't been played is flagged
    `risky` regardless of the point gap, since a start/sit call is exactly
    where injury risk matters most and v1 had no such signal at all.
    """
    starters = [p for p in lineup if _is_starter(p)]
    bench = [
        p
        for p in lineup
        if not _is_starter(p)
        and (p.get("slot_position") or "").upper() not in IR_SLOTS
        and not p.get("on_bye")
        and float(p.get("game_played") or 0) < 100
    ]

    calls: List[Dict[str, Any]] = []
    for starter in starters:
        s_proj = float(starter.get("projected_points") or 0.0)
        alt = _best_bench_alternative(starter.get("slot_position"), bench)
        risky = _is_risky(starter)

        if alt is None:
            margin = None
            tier = "risky" if risky else "locked"
        else:
            margin = round(s_proj - float(alt.get("projected_points") or 0.0), 1)
            if risky:
                tier = "risky"
            elif margin >= 5:
                tier = "comfortable"
            elif margin >= 1:
                tier = "moderate"
            else:
                tier = "toss_up"

        calls.append(
            {
                "name": starter.get("name"),
                "position": starter.get("position"),
                "slot": starter.get("slot_position"),
                "tier": tier,
                "margin": margin,
                "best_bench_alternative": alt.get("name") if alt else None,
            }
        )
    return calls


def _trend(player: Dict[str, Any]) -> Optional[str]:
    """Rough momentum read: this week's projection vs the player's own
    season pace. Deliberately coarse and labeled 'heuristic' in the UI --
    ESPN does not expose a projection confidence interval.
    """
    proj = player.get("projected_points")
    if proj is None:
        return None
    # box_scores only carries the weekly number; season pace isn't in this
    # payload, so trend is derived elsewhere when available. Kept as a hook.
    return None


async def build_this_week(league: UserLeague) -> Dict[str, Any]:
    league_info = {
        "id": league.id,
        "name": league.league_name,
        "platform": league.platform.value.upper(),
        "season": league.season,
        "scoring_format": league.scoring_format,
        "league_size": league.league_size,
    }

    if league_info["platform"] == "YAHOO":
        return await _build_yahoo_this_week(league, league_info)

    if league_info["platform"] != "ESPN":
        return {
            "league_info": league_info,
            "platform_supported": False,
            "detail": (
                f"The This Week screen is only available for ESPN and Yahoo "
                f"leagues today. {league_info['platform']} support is tracked "
                f"as a follow-up."
            ),
        }

    if not league.team_id:
        return {
            "league_info": league_info,
            "platform_supported": True,
            "detail": (
                "Your team isn't identified for this league yet. Set it from "
                "league settings to see your weekly matchup."
            ),
        }

    # The weekly box score is a fresh ESPN fetch; standings reads from the
    # already-loaded league object. Kick both off together.
    matchup, standings = await asyncio.gather(
        espn_service_enhanced.get_week_matchup(
            league_id=league.league_id,
            team_id=league.team_id,
            season=league.season,
            swid=league.espn_swid,
            espn_s2=league.espn_s2,
        ),
        espn_service_enhanced.get_standings(
            league_id=league.league_id,
            season=league.season,
            swid=league.espn_swid,
            espn_s2=league.espn_s2,
        ),
    )
    if "error" in matchup:
        return {
            "league_info": league_info,
            "platform_supported": True,
            "detail": (
                "Your ESPN connection is missing or has expired, or this week's "
                "matchup isn't posted yet. Reconnect ESPN and try again."
            ),
        }

    records: Dict[str, Dict[str, Any]] = {}
    if isinstance(standings, list) and standings and "error" not in standings[0]:
        for t in standings:
            records[str(t.get("team_id"))] = {
                "wins": t.get("wins"),
                "losses": t.get("losses"),
                "ties": t.get("ties"),
                "rank": t.get("rank"),
            }

    my = matchup["my_team"]
    opp = matchup["opponent"]
    my_rec = records.get(str(my.get("team_id")), {})
    opp_rec = records.get(str(opp.get("team_id")), {})

    my_proj = my.get("projected_score") or 0.0
    opp_proj = opp.get("projected_score") or 0.0
    projected_margin = round(my_proj - opp_proj, 1)

    lineup = matchup.get("my_lineup", [])
    opponent_lineup = matchup.get("opponent_lineup", [])
    optimization = optimize_lineup(lineup)
    start_sit = start_sit_confidence(lineup)

    # roll starter injuries up so the UI can badge them
    injury_flags = [
        {
            "name": p.get("name"),
            "position": p.get("position"),
            "status": p.get("injury_status"),
        }
        for p in lineup
        if _is_starter(p) and (p.get("injury_status") or "").upper() not in HEALTHY_STATUSES
    ]

    return {
        "league_info": league_info,
        "platform_supported": True,
        "week": matchup.get("week"),
        "matchup": {
            "my_team": {**my, **my_rec},
            "opponent": {**opp, **opp_rec},
            "projected_margin": projected_margin,
            "favored": "my_team" if projected_margin > 0 else ("opponent" if projected_margin < 0 else "even"),
        },
        "lineup": lineup,
        # The opponent's real lineup for this same matchup -- espn_api's
        # box_scores(week) call already returns both sides at once (see
        # get_week_matchup), it just wasn't surfaced here before. Powers
        # the side-by-side "my starters vs theirs" view.
        "opponent_lineup": opponent_lineup,
        "optimization": optimization,
        "starter_injuries": injury_flags,
        "start_sit": start_sit,
    }


async def _build_yahoo_this_week(league: UserLeague, league_info: Dict[str, Any]) -> Dict[str, Any]:
    """Yahoo's real "This Week": real opponent, real team-level projected
    totals + win probability, real lineup with real actual points-so-far.

    Per-player projections come from Sleeper's weekly feed, scored with
    this league's real Yahoo scoring rules (weekly_projections.py) --
    Yahoo has none of its own. If that feed is unavailable, `optimization`
    is `None` (never an empty-swaps "already optimal" result, which would
    be a false claim) and `projection_note` says why.
    """
    if not league.team_id:
        return {
            "league_info": league_info,
            "platform_supported": True,
            "detail": (
                "Your team isn't identified for this league yet. Please "
                "reconnect your Yahoo account to auto-detect it, or set it "
                "from league settings."
            ),
        }

    if not league.yahoo_access_token:
        return {
            "league_info": league_info,
            "platform_supported": True,
            "detail": "Your Yahoo connection is missing or has expired. Please reconnect your Yahoo account.",
        }
    # Renews an expired token first (yahoo_tokens.get_valid_yahoo_token);
    # None only when renewal genuinely failed.
    access_token = await get_valid_yahoo_token(league)
    if not access_token:
        return {
            "league_info": league_info,
            "platform_supported": True,
            "detail": "Your Yahoo connection has expired. Please reconnect your Yahoo account.",
        }
    team_key = yahoo_service.build_team_key(league.league_key, league.team_id)
    if not team_key:
        return {
            "league_info": league_info,
            "platform_supported": True,
            "detail": "Your team isn't identified for this league yet. Set it from league settings.",
        }

    yahoo_league_info = await yahoo_service.get_league_info(access_token, league.league_key)
    week = yahoo_league_info.get("current_week") if "error" not in yahoo_league_info else None
    try:
        week = int(week) if week is not None else None
    except (TypeError, ValueError):
        week = None
    if week is None:
        return {
            "league_info": league_info,
            "platform_supported": True,
            "detail": "This week's matchup isn't available yet.",
        }

    matchup = await yahoo_service.get_week_matchup(access_token, league.league_key, team_key, week)
    if "error" in matchup:
        return {
            "league_info": league_info,
            "platform_supported": True,
            "detail": (
                "Your Yahoo connection is missing or has expired, or this week's "
                "matchup isn't posted yet. Reconnect Yahoo and try again."
            ),
        }

    my = matchup["my_team"]
    opp = matchup["opponent"]
    projected_margin = round((my.get("projected_score") or 0.0) - (opp.get("projected_score") or 0.0), 1)

    lineup = matchup.get("my_lineup", [])
    opponent_lineup = matchup.get("opponent_lineup", [])

    projection_rows, yahoo_settings = await asyncio.gather(
        fetch_weekly_projections(league.season or yahoo_league_info.get("season") or 0, week),
        yahoo_service.get_league_settings(access_token, league.league_key),
    )
    scoring_rules = yahoo_settings.get("scoring_rules") if "error" not in yahoo_settings else None
    stat_values = yahoo_settings.get("stat_values") if "error" not in yahoo_settings else None

    optimization = None
    start_sit: List[Dict[str, Any]] = []
    projection_source = None
    if projection_rows:
        unmatched = _attach_yahoo_projections(lineup, projection_rows, scoring_rules, stat_values)
        _attach_yahoo_projections(opponent_lineup, projection_rows, scoring_rules, stat_values)
        # Only players with a real projection take part -- an unmatched
        # player treated as 0 would be "benched" by the optimizer for no
        # real reason.
        projected = [p for p in lineup if p.get("projected_points") is not None]
        optimization = optimize_lineup(projected)
        start_sit = start_sit_confidence(projected)
        projection_source = PROJECTION_SOURCE + (
            ", scored with your league's rules" if scoring_rules else ""
        )
        projection_note = (
            "Per-player projections are Sleeper's (RotoWire) weekly numbers "
            + ("scored with this league's real Yahoo scoring rules (K and DEF on standard scoring)"
               if scoring_rules else "on standard scoring (this league's rules couldn't be loaded)")
            + " -- Yahoo doesn't publish per-player projections. Matchup totals and win probability are Yahoo's own."
        )
        if unmatched:
            projection_note += (
                f" No projection found for {', '.join(unmatched)}, so "
                + ("they aren't" if len(unmatched) > 1 else "that player isn't")
                + " considered by the optimizer."
            )
    else:
        projection_note = (
            "Weekly player projections couldn't be loaded right now, so lineup "
            "optimization and start/sit confidence aren't available -- Yahoo "
            "doesn't publish per-player projections itself. Matchup totals and "
            "win probability are Yahoo's own."
        )

    injury_flags = [
        {
            "name": p.get("name"),
            "position": p.get("position"),
            "status": p.get("injury_status"),
        }
        for p in lineup
        if _is_starter(p) and (p.get("injury_status") or "").upper() not in HEALTHY_STATUSES
    ]

    return {
        "league_info": league_info,
        "platform_supported": True,
        "week": matchup.get("week"),
        "matchup": {
            "my_team": my,
            "opponent": opp,
            "projected_margin": projected_margin,
            "favored": "my_team" if projected_margin > 0 else ("opponent" if projected_margin < 0 else "even"),
            # Yahoo's own real server-computed win probability for this
            # matchup -- ESPN's branch above has no equivalent field, so
            # this is Yahoo-only, not a parity gap in the other direction.
            "win_probability": matchup.get("win_probability"),
        },
        "lineup": lineup,
        "opponent_lineup": opponent_lineup,
        "optimization": optimization,
        "starter_injuries": injury_flags,
        "start_sit": start_sit,
        "projection_source": projection_source,
        "projection_note": projection_note,
    }


def _attach_yahoo_projections(
    lineup: List[Dict[str, Any]],
    rows: List[Dict[str, Any]],
    scoring_rules: Optional[Dict[str, Any]],
    stat_values: Optional[Dict[int, float]],
) -> List[str]:
    """Bye-week players get a real 0 (they can't score) so the optimizer can
    still suggest replacing a starter on bye; everyone else is matched
    against the Sleeper feed. Returns unmatched names, leaving out IR-slotted
    players -- they can't be started anyway, so a missing projection for
    them changes nothing worth telling the user."""
    for p in lineup:
        if p.get("on_bye"):
            p["projected_points"] = 0.0
    unmatched = attach_projections([p for p in lineup if not p.get("on_bye")], rows, scoring_rules, stat_values)
    ir_names = {p.get("name") for p in lineup if (p.get("slot_position") or "").upper() in IR_SLOTS}
    return [n for n in unmatched if n not in ir_names]
