"""League value model: waiver and trade recommendations judged by what they
do to real starting lineups, not by raw points or league-wide buzz.

Why this exists. The earlier engines had two analytic flaws:

- Waivers ranked candidates by Sleeper's global trending-add count. Demand
  across every Sleeper league says nothing about *this* roster -- on a real
  roster, 8 of the top 10 trending adds projected below the weakest bench
  player already there.
- Trades compared raw projected points across positions, so a 170-pt WR
  looked like a fair swap for a 140-pt kicker. Raw points ignore scarcity:
  a replacement kicker is free on waivers, a replacement WR1 is not.

The fix is the standard fantasy-analytics one: a player's value to a team is
the change he makes to that team's best possible starting lineup.

- `best_lineup` fills the league's real starter slots optimally (dedicated
  slots first, then FLEX from what's left -- greedy is exact for this slot
  structure).
- A waiver add's value is the lineup gain after the best possible drop.
- A trade makes sense when BOTH teams' best lineups improve: my surplus
  meets their need and vice versa. That's also what makes it acceptable.
- Replacement level per position is the best free agent there -- the
  player you'd actually get for nothing -- so value over replacement (VOR)
  reflects this league's real waiver pool, not a generic rank cutoff.

Everything here is pure arithmetic on the players passed in; platform
adapters (league_value_data.py) supply real rosters, free agents, starter
slots and projections. Two horizons are scored: `season` (projected season
points -- the long-run value) and `week` (this week's projection, zero on a
bye -- the streaming/bye-cover value).
"""
from itertools import combinations
from typing import Any, Dict, Iterable, List, Optional, Tuple

FLEX_POSITIONS = ("RB", "WR", "TE")
SUPERFLEX_POSITIONS = ("QB", "RB", "WR", "TE")
SKILL_POSITIONS = ("QB", "RB", "WR", "TE")

# Long-term absences: out of the lineup on either horizon. A player in an IR
# slot is treated the same way.
LONG_TERM_STATUSES = {"IR", "INJURY_RESERVE", "PUP", "PUP-R", "PUP-P", "SUS", "SUSPENSION", "NA"}
# Short-term: out for THIS week only -- still full value over the season.
THIS_WEEK_STATUSES = {"O", "OUT", "D", "DOUBTFUL"}
IR_SLOTS = {"IR", "IR+"}

# Minimum gains worth surfacing. Season points: ~0.3 pts/game over a
# 17-game season; below that a move is noise within projection error.
MIN_SEASON_GAIN = 5.0
MIN_WEEK_GAIN = 2.0
# Don't trade for a player barely better than the best free agent at his
# position -- the free agent costs nothing.
MIN_RECEIVE_VOR = 5.0
# A trade partner needs a real reason to accept: their gain must be at least
# this share of mine (and at least MIN_THEIR_GAIN). Filters out lopsided
# asks that would just be rejected, without ranking by the smaller gain --
# that favors deals where I overpay.
ACCEPTANCE_RATIO = 0.25
MIN_THEIR_GAIN = 2.0
# Up to two different offers per trade partner -- alternatives, not
# five variations on one manager.
MAX_PER_PARTNER = 2

# Bench depth is worth something (bye weeks, injuries, trade capital), but
# only above replacement -- a bench player no better than the best free
# agent is worth nothing, since you could add that free agent any time.
# Common fantasy-analytics weighting: ~20% of VOR for the top few bench
# players. Season horizon only; this week's bench scores nothing.
DEPTH_WEIGHT = 0.2
DEPTH_SLOTS = 4


def normalize_position(pos: Optional[str]) -> str:
    p = (pos or "").upper()
    return {"D/ST": "DEF", "DST": "DEF", "PK": "K"}.get(p, p)


def is_unavailable(player: Dict[str, Any], horizon: str = "season") -> bool:
    if (player.get("slot") or "").upper() in IR_SLOTS:
        return True
    status = (player.get("injury_status") or "").upper()
    if status in LONG_TERM_STATUSES:
        return True
    return horizon == "week" and status in THIS_WEEK_STATUSES


def _value(player: Dict[str, Any], horizon: str) -> float:
    v = player.get("season" if horizon == "season" else "week")
    return float(v or 0.0)


def _slot_plan(starters: Dict[str, int]) -> Tuple[Dict[str, int], int, int]:
    """(dedicated slots by position, FLEX count, SUPERFLEX count)."""
    dedicated: Dict[str, int] = {}
    flex = 0
    superflex = 0
    for slot, count in (starters or {}).items():
        s = normalize_position(slot)
        if s in ("FLEX", "W/R/T", "RB/WR/TE"):
            flex += int(count)
        elif s in ("OP", "SUPERFLEX", "Q/W/R/T"):
            superflex += int(count)
        elif s in ("W/R", "RB/WR"):
            flex += int(count)  # close enough: RB/WR flex, TE rarely wins it
        elif s in ("W/T", "WR/TE"):
            flex += int(count)
        else:
            dedicated[s] = dedicated.get(s, 0) + int(count)
    return dedicated, flex, superflex


def best_lineup(
    players: Iterable[Dict[str, Any]], starters: Dict[str, int], horizon: str = "season"
) -> Tuple[float, List[Dict[str, Any]]]:
    """Highest-projecting legal starting lineup from `players` (unavailable
    players excluded). Returns (total, chosen starters)."""
    dedicated, flex, superflex = _slot_plan(starters)
    pool = [p for p in players if not is_unavailable(p, horizon)]
    by_pos: Dict[str, List[Dict[str, Any]]] = {}
    for p in pool:
        by_pos.setdefault(normalize_position(p.get("position")), []).append(p)
    for lst in by_pos.values():
        lst.sort(key=lambda p: _value(p, horizon), reverse=True)

    chosen: List[Dict[str, Any]] = []
    leftovers: List[Dict[str, Any]] = []
    for pos, lst in by_pos.items():
        n = dedicated.get(pos, 0)
        chosen.extend(lst[:n])
        leftovers.extend(lst[n:])

    leftovers.sort(key=lambda p: _value(p, horizon), reverse=True)
    for _ in range(flex):
        pick = next((p for p in leftovers if normalize_position(p.get("position")) in FLEX_POSITIONS), None)
        if pick is None:
            break
        chosen.append(pick)
        leftovers.remove(pick)
    for _ in range(superflex):
        pick = next((p for p in leftovers if normalize_position(p.get("position")) in SUPERFLEX_POSITIONS), None)
        if pick is None:
            break
        chosen.append(pick)
        leftovers.remove(pick)

    return round(sum(_value(p, horizon) for p in chosen), 2), chosen


def replacement_levels(free_agents: Iterable[Dict[str, Any]], horizon: str = "season") -> Dict[str, float]:
    """Best available free agent's projection at each position -- the
    real, zero-cost replacement in this league."""
    levels: Dict[str, float] = {}
    for p in free_agents:
        if is_unavailable(p):
            continue
        pos = normalize_position(p.get("position"))
        levels[pos] = max(levels.get(pos, 0.0), _value(p, horizon))
    return levels


def vor(player: Dict[str, Any], levels: Dict[str, float], horizon: str = "season") -> float:
    return round(_value(player, horizon) - levels.get(normalize_position(player.get("position")), 0.0), 1)


def team_value(
    players: List[Dict[str, Any]], starters: Dict[str, int], levels: Dict[str, float], horizon: str = "season"
) -> float:
    """Best-lineup points plus (season horizon) weighted bench depth above
    replacement. The quantity waiver and trade gains are measured in."""
    total, chosen = best_lineup(players, starters, horizon)
    if horizon != "season":
        return total
    chosen_keys = {_key(p) for p in chosen}
    bench_vor = sorted(
        (max(0.0, vor(p, levels)) for p in players if _key(p) not in chosen_keys and not is_unavailable(p)),
        reverse=True,
    )
    return round(total + DEPTH_WEIGHT * sum(bench_vor[:DEPTH_SLOTS]), 2)


def _key(p: Dict[str, Any]) -> Any:
    return p.get("id") or p.get("name")


def _without(players: List[Dict[str, Any]], remove: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    keys = {_key(p) for p in remove}
    return [p for p in players if _key(p) not in keys]


def _displaced(
    before: List[Dict[str, Any]], after: List[Dict[str, Any]], starters: Dict[str, int],
    horizon: str, exclude: Iterable[Dict[str, Any]] = (),
) -> List[Dict[str, Any]]:
    """Players in the `before` best lineup who aren't in the `after` one
    (excluding ones who simply left the roster) -- who a move benches."""
    _, b = best_lineup(before, starters, horizon)
    _, a = best_lineup(after, starters, horizon)
    after_keys = {_key(p) for p in a}
    gone = {_key(p) for p in exclude}
    return [p for p in b if _key(p) not in after_keys and _key(p) not in gone]


# ---------------------------------------------------------------------------
# Team needs
# ---------------------------------------------------------------------------

def team_needs(
    my_players: List[Dict[str, Any]],
    all_teams: List[Dict[str, Any]],
    starters: Dict[str, int],
) -> List[Dict[str, Any]]:
    """Where my lineup is weakest relative to the league. For each position
    with a dedicated starter slot, compares my starters' average season
    projection with every team's starters at that position and ranks mine
    (1 = best). Weakest first."""
    dedicated, _, _ = _slot_plan(starters)
    lineups = {str(t["team_id"]): best_lineup(t["players"], starters)[1] for t in all_teams}
    _, mine = best_lineup(my_players, starters)

    out = []
    for pos in dedicated:
        def avg(lineup: List[Dict[str, Any]]) -> float:
            vals = [_value(p, "season") for p in lineup if normalize_position(p.get("position")) == pos]
            return sum(vals) / len(vals) if vals else 0.0

        league = sorted((avg(l) for l in lineups.values()), reverse=True)
        my_avg = avg(mine)
        rank = 1 + sum(1 for v in league if v > my_avg + 1e-6)
        out.append({
            "position": pos,
            "my_starter_avg": round(my_avg, 1),
            "league_median": round(league[len(league) // 2], 1) if league else None,
            "rank": rank,
            "teams": len(league),
        })
    out.sort(key=lambda n: n["rank"], reverse=True)
    return out


# ---------------------------------------------------------------------------
# Waivers
# ---------------------------------------------------------------------------

def _best_drop(
    roster: List[Dict[str, Any]], add: Dict[str, Any], starters: Dict[str, int], levels: Dict[str, float]
) -> Tuple[Optional[Dict[str, Any]], float]:
    """Drop that leaves the most team value (lineup + bench depth) after
    adding `add`. Never drops an IR-slotted player (IR spots don't free a
    roster spot). Returns (drop, team value after the swap)."""
    with_add = roster + [add]
    best: Tuple[Optional[Dict[str, Any]], float] = (None, float("-inf"))
    for cand in roster:
        if (cand.get("slot") or "").upper() in IR_SLOTS:
            continue
        total = team_value(_without(with_add, [cand]), starters, levels)
        # Tie-break toward dropping the lower season value (keeps depth).
        if total > best[1] + 1e-6 or (
            abs(total - best[1]) <= 1e-6 and best[0] is not None and _value(cand, "season") < _value(best[0], "season")
        ):
            best = (cand, total)
    return best


def waiver_targets(
    my_roster: List[Dict[str, Any]],
    free_agents: List[Dict[str, Any]],
    starters: Dict[str, int],
    levels: Dict[str, float],
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Real free agents ranked by what they add to MY team (lineup plus
    weighted bench depth -- see team_value).

    Two horizons: `season_gain` (long-run lineup improvement after the best
    drop) and `week_gain` (this week's lineup, where byes and injuries make
    a streamer worth more). A candidate qualifies on either. Players who
    are Out/IR are skipped -- they can't help the lineup now.
    """
    base_season = team_value(my_roster, starters, levels)
    base_week, _ = best_lineup(my_roster, starters, "week")

    # Cheap prefilter: only candidates who'd beat someone on the roster at
    # their position group on either horizon can possibly help.
    def worst_at(pos: str, horizon: str) -> float:
        group = FLEX_POSITIONS if pos in FLEX_POSITIONS else (pos,)
        vals = [_value(p, horizon) for p in my_roster if normalize_position(p.get("position")) in group and not is_unavailable(p, horizon)]
        return min(vals) if vals else 0.0

    results = []
    for fa in free_agents:
        if is_unavailable(fa):
            continue
        pos = normalize_position(fa.get("position"))
        if _value(fa, "season") <= worst_at(pos, "season") and _value(fa, "week") <= worst_at(pos, "week"):
            continue

        drop, season_total = _best_drop(my_roster, fa, starters, levels)
        if drop is None:
            continue
        season_gain = round(season_total - base_season, 1)
        week_total, _ = best_lineup(_without(my_roster + [fa], [drop]), starters, "week")
        week_gain = round(week_total - base_week, 1)

        if season_gain < MIN_SEASON_GAIN and week_gain < MIN_WEEK_GAIN:
            continue

        kind = "upgrade" if season_gain >= MIN_SEASON_GAIN else "streamer"
        after = _without(my_roster + [fa], [drop])
        horizon = "season" if kind == "upgrade" else "week"
        results.append({
            "player": fa,
            "drop": drop,
            "season_gain": season_gain,
            "week_gain": week_gain,
            "kind": kind,
            "vor": vor(fa, levels),
            "replaces": _displaced(my_roster, after, starters, horizon, exclude=[drop]),
            "drop_was_starter": _key(drop) in {_key(p) for p in best_lineup(my_roster, starters, horizon)[1]},
        })

    # Long-run upgrades first (by season gain), then streamers (by week gain).
    results.sort(key=lambda r: (r["kind"] != "upgrade", -r["season_gain"] if r["kind"] == "upgrade" else -r["week_gain"]))

    # Alternatives, each with its own best drop -- two adds may name the
    # same drop; they're options to choose between, not a sequence.
    return results[:limit]


def streaming_options(
    my_roster: List[Dict[str, Any]],
    free_agents: List[Dict[str, Any]],
    position: str,
    limit: int = 5,
) -> Dict[str, Any]:
    """One-week streaming board for a single-starter spot (DEF, K): my best
    available player there this week vs the free agents projecting highest
    this week, each with its edge over mine. Unlike waiver_targets there's
    no minimum gain -- this is the menu, so a "keep yours" answer shows as
    every edge being <= 0. Out/IR and bye-week (0 projection) free agents
    are left out; a bye-week starter of mine shows with 0 so every option
    reads as an edge."""
    pos = normalize_position(position)
    mine = [
        p for p in my_roster
        if normalize_position(p.get("position")) == pos and not is_unavailable(p, "week")
    ]
    current = max(mine, key=lambda p: _value(p, "week"), default=None)
    base = _value(current, "week") if current else 0.0
    options = sorted(
        (
            fa for fa in free_agents
            if normalize_position(fa.get("position")) == pos
            and not is_unavailable(fa, "week")
            and _value(fa, "week") > 0
        ),
        key=lambda fa: _value(fa, "week"),
        reverse=True,
    )[:limit]
    return {
        "position": pos,
        "current": current,
        "options": [{"player": fa, "week_edge": round(_value(fa, "week") - base, 1)} for fa in options],
    }


def watch_list(
    my_roster: List[Dict[str, Any]],
    free_agents: List[Dict[str, Any]],
    starters: Dict[str, int],
    needs: List[Dict[str, Any]],
    levels: Dict[str, float],
    positions: int = 2,
) -> List[Dict[str, Any]]:
    """When no free agent clears the upgrade bar: the best available player
    at each of my weakest positions, with his honest (small or negative)
    gain -- who to monitor, not who to claim."""
    base = team_value(my_roster, starters, levels)
    out = []
    for need in needs[:positions]:
        pos = need["position"]
        pool = [p for p in free_agents if normalize_position(p.get("position")) == pos and not is_unavailable(p)]
        if not pool:
            continue
        best = max(pool, key=lambda p: _value(p, "season"))
        drop, total = _best_drop(my_roster, best, starters, levels)
        out.append({
            "player": best,
            "drop": drop,
            "season_gain": round(total - base, 1) if drop else 0.0,
            "week_gain": 0.0,
            "kind": "watch",
            "vor": vor(best, levels),
            "replaces": [],
            "need": need,
        })
    return out


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------

def trade_targets(
    my_team_id: Any,
    teams: List[Dict[str, Any]],
    starters: Dict[str, int],
    levels: Dict[str, float],
    limit: int = 5,
    max_send: int = 2,
) -> List[Dict[str, Any]]:
    """Trades that improve BOTH teams' best season lineups.

    Searches every 1-for-1 and (when max_send >= 2) 2-for-1 deal with every
    other team: I send one or two players, receive one. A deal qualifies
    when my team gains at least MIN_SEASON_GAIN and theirs gains enough to
    accept (ACCEPTANCE_RATIO of my gain, at least MIN_THEIR_GAIN) -- a
    trade that costs the other manager isn't one they'd take, however good
    it looks for me. Ranked by my gain, with at
    most one suggestion per player I'd receive and per player I'd send, and
    MAX_PER_PARTNER per trade partner, so the list isn't five versions of
    the same idea.

    Gains are in team value (lineup + weighted bench depth above
    replacement), so giving up a useful backup isn't free. A player barely
    better than the best free agent at his position (VOR < MIN_RECEIVE_VOR)
    is never a trade target -- add the free agent instead.

    Players who are Out/IR aren't offered or requested: their value to
    either lineup right now is nil and neither side can evaluate them from
    projections alone.
    """
    my_team = next((t for t in teams if str(t.get("team_id")) == str(my_team_id)), None)
    if not my_team:
        return []
    mine = my_team["players"]
    my_base = team_value(mine, starters, levels)
    my_tradeable = [p for p in mine if not is_unavailable(p)]

    candidates = []
    for team in teams:
        if team is my_team:
            continue
        theirs = team["players"]
        their_base = team_value(theirs, starters, levels)

        # Upper bounds for pruning: adding a player without giving anything
        # up is the most a deal can gain. A player I'd receive who wouldn't
        # improve my lineup even for free can't be part of a good trade;
        # likewise a package whose players wouldn't improve theirs for free.
        their_free_gain = {
            _key(p): team_value(theirs + [p], starters, levels) - their_base for p in my_tradeable
        }
        useful_to_them = [p for p in my_tradeable if their_free_gain[_key(p)] > 0.5]
        if not useful_to_them:
            continue
        send_options: List[Tuple[Dict[str, Any], ...]] = [(p,) for p in useful_to_them]
        if max_send >= 2:
            send_options += [
                pair for pair in combinations(my_tradeable, 2)
                if any(their_free_gain[_key(p)] > 0.5 for p in pair)
            ]

        for receive in theirs:
            if is_unavailable(receive) or vor(receive, levels) < MIN_RECEIVE_VOR:
                continue
            if team_value(mine + [receive], starters, levels) - my_base < MIN_SEASON_GAIN:
                continue
            for send in send_options:
                my_after = team_value(_without(mine, send) + [receive], starters, levels)
                my_gain = my_after - my_base
                if my_gain < MIN_SEASON_GAIN:
                    continue
                their_after = team_value(_without(theirs, [receive]) + list(send), starters, levels)
                their_gain = their_after - their_base
                if their_gain < max(MIN_THEIR_GAIN, ACCEPTANCE_RATIO * my_gain):
                    continue
                candidates.append({
                    "team_id": team.get("team_id"),
                    "team_name": team.get("team_name"),
                    "send": list(send),
                    "receive": receive,
                    "my_gain": round(my_gain, 1),
                    "their_gain": round(their_gain, 1),
                    "_theirs": theirs,
                })

    # Best for me first (among deals they'd plausibly accept), simpler
    # 1-for-1 deals ahead of 2-for-1 at equal gain.
    candidates.sort(key=lambda c: (-c["my_gain"], len(c["send"])))

    picked: List[Dict[str, Any]] = []
    used_receive, used_send = set(), set()
    per_team: Dict[Any, int] = {}
    for c in candidates:
        r_key = _key(c["receive"])
        s_keys = {_key(p) for p in c["send"]}
        if r_key in used_receive or s_keys & used_send or per_team.get(c["team_id"], 0) >= MAX_PER_PARTNER:
            continue
        used_receive.add(r_key)
        used_send |= s_keys
        per_team[c["team_id"]] = per_team.get(c["team_id"], 0) + 1
        c["receive_vor"] = vor(c["receive"], levels)
        c["send_vor"] = round(sum(vor(p, levels) for p in c["send"]), 1)
        theirs = c.pop("_theirs")
        c["my_benched"] = _displaced(mine, _without(mine, c["send"]) + [c["receive"]], starters, "season", exclude=c["send"])
        my_lineup = {_key(p) for p in best_lineup(mine, starters)[1]}
        c["sent_starters"] = [p for p in c["send"] if _key(p) in my_lineup]
        c["their_benched"] = _displaced(theirs, _without(theirs, [c["receive"]]) + c["send"], starters, "season", exclude=[c["receive"]])
        picked.append(c)
        if len(picked) >= limit:
            break
    return picked
