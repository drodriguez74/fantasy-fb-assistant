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

ESPN and Yahoo are NOT full parity with each other on this screen: ESPN
exposes a real per-player weekly PROJECTED points number
(BoxPlayer.projected_points); Yahoo's public API genuinely does not
(confirmed live 2026-09-23 -- see yahoo_service.get_week_matchup's
docstring). The optimizer (`optimize_lineup`) and start/sit confidence
(`start_sit_confidence`) both require a real per-player projection to
mean anything, so the YAHOO branch below skips both rather than run
them against all-None projections and produce a meaningless "optimal"
claim -- the matchup scoreboard, real lineup, real team-level projected
totals, and real win probability are all still real and shown.
"""
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.models.user_league import UserLeague
from app.services.espn_service_enhanced import espn_service_enhanced
from app.services.yahoo_service import yahoo_service

BENCH_SLOTS = {"BE", "IR", "BENCH"}
# ESPN flex slot labels that accept any RB/WR/TE.
FLEX_SLOTS = {"RB/WR/TE", "FLEX", "OP"}
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

    NOT real (Yahoo's public API genuinely doesn't expose it -- see
    yahoo_service.get_week_matchup's docstring): per-player projected
    points. `optimization` and `start_sit` are both honestly `None`
    rather than computed against fabricated/zeroed projections --
    LeagueDetailPage.tsx must render that as "not available for this
    platform", never as "already optimal" (a different, false claim).
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
    # yahoo_token_expires_at is a timezone-aware DB column; comparing it
    # against a naive datetime.utcnow() raises "can't compare
    # offset-naive and offset-aware datetimes" -- the exact same bug
    # class already fixed in league_management_service.py /
    # league_snapshots.py / user_service.py's account-lockout check.
    if (
        league.yahoo_token_expires_at
        and league.yahoo_token_expires_at < datetime.now(timezone.utc)
    ):
        return {
            "league_info": league_info,
            "platform_supported": True,
            "detail": "Your Yahoo connection has expired. Please reconnect your Yahoo account.",
        }

    access_token = league.yahoo_access_token
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
        # Honestly unavailable -- see this function's docstring. Not `{}`
        # or an empty-swaps dict, which would render as "already
        # optimal", a real (false) claim this data can't support.
        "optimization": None,
        "starter_injuries": injury_flags,
        "start_sit": [],
        "projection_note": (
            "Yahoo doesn't provide per-player projected points, so lineup "
            "optimization and start/sit confidence aren't available for "
            "this league -- real matchup totals and win probability are "
            "Yahoo's own."
        ),
    }
