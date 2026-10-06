"""Waiver and trade advice for a connected ESPN/Yahoo league, built on
league_value_model (lineup-impact valuation) over league_value_data (real
rosters, free agents and projections).

Response shapes stay compatible with what LeagueDetailPage already renders
(waiver: player/reason/priority/drop_candidate/value_delta/bid_tier; trade:
team_name/you_send/you_receive/reasoning) and add the numbers behind each
call: season and this-week lineup gains, value over replacement, both
sides' gains on a trade, and a per-position team-needs table.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.models.user_league import UserLeague
from app.services import league_value_model as model
from app.services.espn_service_enhanced import espn_service_enhanced
from app.services.league_value_data import LeagueDataError, load_league_value_data
from app.services.waiver_wire_service import WaiverWireService
from app.services.yahoo_service import yahoo_service
from app.services.yahoo_tokens import get_valid_yahoo_token

logger = logging.getLogger(__name__)

# Trending adds (Sleeper, last 24h) above which a player is likely to be
# claimed elsewhere soon -- worth acting on now rather than waiting.
HOT_TRENDING_ADDS = 5000


def _pos(p: Dict[str, Any]) -> str:
    return model.normalize_position(p.get("position"))


def _pts(v: Optional[float]) -> str:
    return f"{v:.0f}" if v is not None else "?"


def _my_team(data: Dict[str, Any]) -> Dict[str, Any]:
    team = next((t for t in data["teams"] if t["team_id"] == data["my_team_id"]), None)
    if not team:
        raise LeagueDataError("Your team wasn't found in this league's rosters. Check your team in league settings.")
    return team


async def _waiver_position(league: UserLeague) -> Optional[Dict[str, Any]]:
    try:
        platform = league.platform.value.upper()
        if platform == "ESPN":
            result = await espn_service_enhanced.get_waiver_position(
                league_id=league.league_id, team_id=league.team_id, season=league.season,
                swid=league.espn_swid, espn_s2=league.espn_s2,
            )
        elif platform == "YAHOO":
            token = await get_valid_yahoo_token(league)
            if not token:
                return None
            result = await yahoo_service.get_waiver_position(token, league.league_key, league.team_id)
        else:
            return None
        return result if isinstance(result, dict) and "error" not in result else None
    except Exception as e:  # noqa: BLE001 - bid tiers are additive, never block advice
        logger.warning(f"Waiver position lookup failed for league {league.id}: {e}")
        return None


def _priority_tier(rec: Dict[str, Any]) -> str:
    if rec["kind"] == "upgrade":
        if rec["season_gain"] >= 25:
            return "urgent"
        if rec["season_gain"] >= 12:
            return "high"
        return "medium"
    return "low"


_TIER_SCORE = {"urgent": 3, "high": 3, "medium": 2, "low": 1}


def _waiver_reason(rec: Dict[str, Any], week: Optional[int]) -> str:
    p, drop = rec["player"], rec["drop"]
    replaced = rec.get("replaces") or []
    parts: List[str] = []
    if rec["kind"] == "upgrade":
        if replaced or rec.get("drop_was_starter"):
            r = replaced[0] if replaced else drop
            verb = "Starts over" if replaced else "Replaces your starter"
            parts.append(
                f"{verb} {r['name']} ({_pos(r)}, {_pts(r['season'])} proj): "
                f"+{rec['season_gain']:.1f} projected season points for your team."
            )
        else:
            parts.append(
                f"Better depth than {drop['name']} at no lineup cost: +{rec['season_gain']:.1f} "
                f"projected season points of bench value."
            )
        if rec["week_gain"] >= model.MIN_WEEK_GAIN:
            parts.append(f"Also +{rec['week_gain']:.1f} in this week's lineup.")
    elif rec["kind"] == "streamer":
        who = f" over {replaced[0]['name']}" if replaced else ""
        parts.append(
            f"One-week play{who}: projects {p['week']:.1f} in week {week or 'this week'}, "
            f"+{rec['week_gain']:.1f} for this week's lineup. Not a long-term hold."
        )
    else:
        need = rec.get("need") or {}
        parts.append(
            f"Best available {need.get('position', _pos(p))} ({_pts(p['season'])} proj). Your starters there "
            f"rank {need.get('rank')} of {need.get('teams')}, but no free agent is a clear upgrade yet "
            f"({rec['season_gain']:+.1f} if added) -- worth monitoring."
        )
    trending = p.get("trending_adds") or 0
    if trending >= HOT_TRENDING_ADDS and rec["kind"] != "watch":
        parts.append(f"{trending:,} adds on Sleeper in the last 24h -- likely to be claimed soon.")
    return " ".join(parts)


def _player_out(p: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": p["name"],
        "position": {"value": _pos(p)},
        "team": p.get("team"),
        "projected_points": round(p["season"], 1),
        "week_projection": round(p["week"], 1),
        "ownership_percentage": p.get("ownership"),
        "trending_adds": p.get("trending_adds") or 0,
        "espn_player_id": p.get("espn_player_id"),
    }


def _my_defense(players: List[Dict[str, Any]]) -> Optional[str]:
    """NFL team abbreviation of this roster's defense (a starting one if
    there are several) -- lets the DEF streaming view compare against it
    without the user typing it in."""
    defenses = [p for p in players if _pos(p) == "DEF" and p.get("team")]
    defenses.sort(key=lambda p: p.get("slot") in ("BE", "BN", "IR", None))
    return str(defenses[0]["team"]).upper() if defenses else None


def _needs_out(needs: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {n["position"]: n["rank"] for n in needs}


async def build_waiver_advice(league: UserLeague, limit: int = 10) -> Dict[str, Any]:
    data = await load_league_value_data(league)
    mine = _my_team(data)["players"]
    starters = data["starters"]
    levels = model.replacement_levels(data["free_agents"])
    needs = model.team_needs(mine, data["teams"], starters)

    recs = model.waiver_targets(mine, data["free_agents"], starters, levels, limit=limit)
    showing_watch = not recs
    if showing_watch:
        recs = model.watch_list(mine, data["free_agents"], starters, needs, levels)

    waiver_position = await _waiver_position(league) if not showing_watch else None

    out = []
    for rec in recs:
        tier = _priority_tier(rec)
        drop = rec["drop"]
        out.append({
            "player": _player_out(rec["player"]),
            "kind": rec["kind"],
            "season_gain": rec["season_gain"],
            "week_gain": rec["week_gain"],
            "value_over_replacement": rec["vor"],
            "reason": _waiver_reason(rec, data.get("current_week")),
            "priority": _TIER_SCORE[tier],
            "priority_tier": tier,
            "drop_candidate": {
                "name": drop["name"],
                "position": _pos(drop),
                "projected_points": round(drop["season"], 1),
                "position_matched": _pos(drop) == _pos(rec["player"]),
            } if drop else None,
            # Team-value change for the season (lineup + depth), not a raw
            # add-minus-drop points difference.
            "value_delta": rec["season_gain"] if rec["kind"] != "streamer" else rec["week_gain"],
            "bid_tier": WaiverWireService.compute_bid_tier(tier, waiver_position) if rec["kind"] != "watch" else None,
        })

    return {
        "recommendations": out,
        "position_needs": _needs_out(needs),
        "team_needs": needs,
        "total_available": len(out) if not showing_watch else 0,
        "watch_only": showing_watch,
        "current_week": data.get("current_week"),
        "my_defense": _my_defense(mine),
        "basis": (
            f"Every free agent in your league scored by what he adds to your best starting lineup "
            f"(and bench depth above replacement) after the best possible drop. Projections: "
            f"{data['projection_source']}."
        ),
        "updated_at": datetime.utcnow().isoformat(),
    }


async def build_streaming_advice(league: UserLeague, limit: int = 5) -> Dict[str, Any]:
    """DEF and K streaming boards for this league's real free agents, by
    this week's projection against the user's own starter."""
    data = await load_league_value_data(league)
    mine = _my_team(data)["players"]
    boards = []
    for pos in ("DEF", "K"):
        if not any(model.normalize_position(k) == pos and n for k, n in data["starters"].items()):
            continue  # league doesn't start one
        board = model.streaming_options(mine, data["free_agents"], pos, limit=limit)
        current = board["current"]
        boards.append({
            "position": pos,
            "current": _player_out(current) if current else None,
            "options": [{"player": _player_out(o["player"]), "week_edge": o["week_edge"]} for o in board["options"]],
        })
    return {
        "current_week": data.get("current_week"),
        "boards": boards,
        "projection_source": data["projection_source"],
        "updated_at": datetime.utcnow().isoformat(),
    }


def _names(players: List[Dict[str, Any]]) -> str:
    return " + ".join(f"{p['name']} ({_pos(p)})" for p in players)


def _trade_reason(c: Dict[str, Any]) -> str:
    r = c["receive"]
    mine_out = c.get("my_benched") or []
    theirs_out = c.get("their_benched") or []
    sent_starters = c.get("sent_starters") or []
    me = f"{r['name']} ({_pos(r)}, {_pts(r['season'])} proj) "
    if mine_out:
        me += f"starts for you over {mine_out[0]['name']}"
    elif sent_starters:
        me += f"takes {sent_starters[0]['name']}'s lineup spot"
    else:
        me += "joins your lineup"
    me += f" -- your team +{c['my_gain']:.0f} projected season points."
    them = f"{c['team_name']} gets {_names(c['send'])}"
    verb = "starts" if len(c["send"]) == 1 else "start"
    them += f", who {verb} over their {theirs_out[0]['name']}" if theirs_out else ""
    them += f" -- their team +{c['their_gain']:.0f}, so it's a deal they have a reason to take."
    return f"{me} {them}"


async def build_trade_advice(league: UserLeague, limit: int = 5) -> Dict[str, Any]:
    data = await load_league_value_data(league)
    _my_team(data)
    starters = data["starters"]
    levels = model.replacement_levels(data["free_agents"])
    mine = _my_team(data)["players"]
    needs = model.team_needs(mine, data["teams"], starters)

    picks = model.trade_targets(data["my_team_id"], data["teams"], starters, levels, limit=limit)

    def ref(p: Dict[str, Any]) -> Dict[str, Any]:
        return {"name": p["name"], "position": _pos(p), "team": p.get("team"), "projected_points": round(p["season"], 1)}

    suggestions = []
    for c in picks:
        send = [ref(p) for p in c["send"]]
        suggestions.append({
            "team_id": c["team_id"],
            "team_name": c["team_name"],
            "you_send": send[0],
            "you_send_players": send,
            "you_receive": ref(c["receive"]),
            "my_gain": c["my_gain"],
            "their_gain": c["their_gain"],
            "receive_vor": c["receive_vor"],
            "send_vor": c["send_vor"],
            "reasoning": _trade_reason(c),
        })

    return {
        "suggestions": suggestions,
        "team_needs": needs,
        "trade_deadline": data.get("trade_deadline") or "Not set",
        "updated_at": datetime.utcnow().isoformat(),
        "basis": (
            "Real players on real rosters. A deal is suggested only when it improves both teams' best "
            f"starting lineups (plus bench depth above replacement). Projections: {data['projection_source']}."
        ),
    }
