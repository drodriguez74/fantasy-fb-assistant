"""Consensus ADP (average draft position) ranking.

This app blends up to three real, independent ranking signals: Sleeper's
public player pool (`search_rank`, available for essentially every real NFL
player -- the baseline/default source), ESPN's `percent_owned` for a
connected league's available-player pool (only present when a session has a
live ESPN league), and FantasyPros' real Consensus Rankings/ADP API
(`rank_ecr`, "expert consensus rank" aggregated across 130+ experts -- only
present when a FANTASYPROS_API_KEY is configured; see fantasypros_service.py
for the real endpoint/auth/response shape this was built against). Every
ranking surface in this codebase (the Draft positional-rankings endpoint, the
Players list, a live draft session) previously used exactly one signal in
isolation; nothing here blended them until this service existed.

Blending method
----------------
A player's raw Sleeper rank (1..N, lower is better), raw ESPN
`percent_owned` (0..100, higher is better), and raw FantasyPros `rank_ecr`
(1..N, lower is better) all live on incompatible scales -- averaging them
directly would let whichever source happens to have the wider/denser numeric
range dominate the result for no principled reason (a Sleeper rank of 12, an
ESPN ownership of 94.2, and a FantasyPros rank_ecr of 8 are not "close" or
"far" from each other in any meaningful sense as raw numbers).

Instead, every source is first converted to a **percentile rank within its
own population** (0..100, 100 = best), which is scale-free and directly
comparable across sources regardless of how many players are in each pool or
how the raw values are distributed. Ties within a source share the average
percentile of the tied group (the standard "fractional rank" tie-break) --
this matters in particular for ESPN's `percent_owned`, where a long tail of
truly unrostered players commonly share the exact same 0.0.

When two or three sources are available for a player, the consensus score is
the unweighted mean of whichever percentiles are present. FantasyPros' own
published methodology for "expert consensus rankings" -- the industry-
standard precedent for what "consensus ADP" means, and the actual API this
service now also draws from directly -- is likewise an unweighted average
across ranked sources; equal weighting is used here for the same reason:
none of Sleeper's userbase, a single connected ESPN league's ownership
numbers, or FantasyPros' own expert panel has a principled claim to being
*more* authoritative than the others, so picking an arbitrary weighting
would be less honest than an even one, not more precise.

When only one source is available for a player -- the common case, since
most players in a Sleeper-only session with no FantasyPros key configured
will only ever carry one signal -- the consensus score degrades to that
single source's percentile (or the mean of however many *are* present)
rather than being averaged against a missing value treated as zero. Treating
"no ESPN/FantasyPros data for this player" as "that source rates this player
at rock bottom" would systematically and wrongly tank the rank of every
player outside whatever narrow pool a given call happens to have that
source's data for. `source_count` on every result makes this degradation
visible to callers instead of silently blending it away -- it now ranges
0..3, not just 0..2, and every caller that surfaces it (e.g.
DataConfidenceBadge on PlayersPage) reads it dynamically rather than
assuming a two-source ceiling.
"""

from typing import Any, Dict, List, Optional, Tuple
import re


# Sleeper's own sentinel for "this player has no meaningful search rank"
# (see draft.py's `_UNRANKED_SENTINEL` / positional-rankings endpoint, and
# players.py's identical constant). A player carrying this value -- or no
# value at all -- has no real Sleeper signal, full stop; it must never be
# treated as a real (maximally bad) rank when computing a percentile, or it
# would silently drag every genuinely-unranked player's consensus score to
# the very bottom of the *scored* population instead of correctly being
# excluded from that population.
SLEEPER_UNRANKED_SENTINEL = 9999999

_GENERATIONAL_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
_NAME_PUNCTUATION_RE = re.compile(r"[.'’\-]")


def normalize_player_name(name: Optional[str]) -> str:
    """Normalize a player's full name for cross-source matching.

    Lowercases, strips punctuation, and drops a trailing generational suffix
    so e.g. Sleeper's "Michael Pittman Jr." matches ESPN's "Michael Pittman"
    (or vice versa -- either source may or may not include the suffix).
    """
    if not name:
        return ""
    cleaned = _NAME_PUNCTUATION_RE.sub("", name.lower()).strip()
    tokens = [t for t in cleaned.split() if t]
    while tokens and tokens[-1] in _GENERATIONAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def _percentile_map(items: List[Tuple[Any, float]], reverse: bool) -> Dict[Any, float]:
    """Given (identity, raw_value) pairs, return {identity: percentile}.

    Percentile is 0..100 where 100 is always "best" regardless of whether a
    higher or lower raw value is better:
      - reverse=False: lower raw_value is better (e.g. Sleeper rank).
      - reverse=True: higher raw_value is better (e.g. ESPN percent_owned).

    Ties in raw_value share the average percentile of the tied group
    (fractional/"average" ranking, the standard approach for percentile
    ranks with duplicate values). A population of one maps to 100 -- there's
    nothing to compare it against, so it's the best available signal for
    itself, not an undefined/zero score.
    """
    n = len(items)
    if n == 0:
        return {}
    if n == 1:
        return {items[0][0]: 100.0}

    ordered = sorted(items, key=lambda pair: pair[1])
    result: Dict[Any, float] = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and ordered[j + 1][1] == ordered[i][1]:
            j += 1
        avg_index = (i + j) / 2  # 0-based average position among ascending values
        fraction = avg_index / (n - 1)
        percentile = fraction * 100 if reverse else (1 - fraction) * 100
        for k in range(i, j + 1):
            result[ordered[k][0]] = percentile
        i = j + 1
    return result


def _blend(*percentiles: Optional[float]) -> float:
    parts = [p for p in percentiles if p is not None]
    if not parts:
        return 0.0
    return sum(parts) / len(parts)


class ConsensusRankingService:
    """Computes a real, inspectable consensus rank from whichever of
    Sleeper's search_rank, ESPN's percent_owned, and FantasyPros' rank_ecr
    are actually available for a given batch of players. See module
    docstring for the blending method and why it's an unweighted percentile
    average, not a raw one.
    """

    def rank_players(
        self,
        players: List[Dict[str, Any]],
        other_source_players: Optional[List[Dict[str, Any]]] = None,
        fantasypros_players: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Return a new list (same dicts, shallow-copied, plus a
        `consensus` key) sorted best-first by consensus rank.

        `players` is the baseline population: each entry is percentile-
        ranked against the others in this same list using whichever signal
        it directly carries (`search_rank` if present -> Sleeper source,
        `percent_owned` if present -> ESPN source; a dict could in
        principle carry both if a caller pre-merges sources, in which case
        both are used directly with no name matching needed).

        `other_source_players`, if given, is the *other* source's player
        pool for the same context (e.g. Sleeper's full player list supplied
        alongside an ESPN league's available-players list) -- each player in
        `players` is cross-referenced against it by normalized full name,
        percentile-ranked within that pool, and blended in. Players with no
        match in `other_source_players` simply keep whatever single source
        they already had; they are not penalized for the miss.

        `fantasypros_players`, if given, is FantasyPros' own consensus-
        rankings player list (see fantasypros_service.get_consensus_rankings_players
        -- each entry a `{"player_name": ..., "rank_ecr": float, ...}` dict).
        Unlike Sleeper/ESPN, this is never embedded directly on `players`
        (it's always a separate real API call) -- it's percentile-ranked
        within its own population and matched onto `players` by normalized
        name, exactly like the `other_source_players` cross-reference above.
        Omitted or empty (no FANTASYPROS_API_KEY configured, or the request
        failed) degrades cleanly to whichever of Sleeper/ESPN are present,
        identical to how a missing ESPN source already degrades today.
        """
        own_sleeper_pct = self._percentiles_by_index(players, "search_rank", reverse=False)
        own_espn_pct = self._percentiles_by_index(players, "percent_owned", reverse=True)

        other_sleeper_by_name: Dict[str, Tuple[float, Any]] = {}
        other_espn_by_name: Dict[str, Tuple[float, Any]] = {}
        if other_source_players:
            other_sleeper_by_name = self._percentiles_by_name(
                other_source_players, "search_rank", reverse=False
            )
            other_espn_by_name = self._percentiles_by_name(
                other_source_players, "percent_owned", reverse=True
            )

        fantasypros_by_name: Dict[str, Tuple[float, Any]] = {}
        if fantasypros_players:
            fantasypros_by_name = self._percentiles_by_name(
                fantasypros_players, "rank_ecr", reverse=False
            )

        enriched: List[Dict[str, Any]] = []
        for idx, player in enumerate(players):
            sleeper_pct = own_sleeper_pct.get(idx)
            espn_pct = own_espn_pct.get(idx)
            fantasypros_pct = None
            sources: Dict[str, Any] = {}

            if sleeper_pct is not None:
                sources["sleeper_rank"] = player.get("search_rank")
            if espn_pct is not None:
                sources["espn_ownership_pct"] = round(player.get("percent_owned", 0.0), 1)

            if other_source_players or fantasypros_players:
                name = normalize_player_name(player.get("full_name") or player.get("name"))
                if name:
                    if other_source_players:
                        if sleeper_pct is None and name in other_sleeper_by_name:
                            sleeper_pct, raw_rank = other_sleeper_by_name[name]
                            sources["sleeper_rank"] = raw_rank
                        if espn_pct is None and name in other_espn_by_name:
                            espn_pct, raw_pct = other_espn_by_name[name]
                            sources["espn_ownership_pct"] = round(raw_pct, 1) if raw_pct is not None else None
                    if fantasypros_players and name in fantasypros_by_name:
                        fantasypros_pct, raw_ecr = fantasypros_by_name[name]
                        sources["fantasypros_rank_ecr"] = raw_ecr

            source_count = (
                (1 if sleeper_pct is not None else 0)
                + (1 if espn_pct is not None else 0)
                + (1 if fantasypros_pct is not None else 0)
            )
            consensus_score = _blend(sleeper_pct, espn_pct, fantasypros_pct)

            new_player = dict(player)
            new_player["consensus"] = {
                "consensus_score": round(consensus_score, 2),
                "sources": sources,
                "source_count": source_count,
            }
            enriched.append(new_player)

        # Best first. Zero-source players (no real signal from either
        # source, not even a name match) sort after every scored player
        # regardless of their placeholder 0.0 score -- a missing signal is
        # not the same thing as a real worst-in-population score.
        enriched.sort(
            key=lambda p: (p["consensus"]["source_count"] == 0, -p["consensus"]["consensus_score"])
        )
        for rank, player in enumerate(enriched, start=1):
            player["consensus"]["consensus_rank"] = rank

        return enriched

    @staticmethod
    def _percentiles_by_index(
        players: List[Dict[str, Any]], field: str, reverse: bool
    ) -> Dict[int, float]:
        items = []
        for idx, player in enumerate(players):
            value = player.get(field)
            if value is None:
                continue
            if field == "search_rank" and value >= SLEEPER_UNRANKED_SENTINEL:
                continue
            items.append((idx, value))
        return _percentile_map(items, reverse=reverse)

    @staticmethod
    def _percentiles_by_name(
        players: List[Dict[str, Any]], field: str, reverse: bool
    ) -> Dict[str, Tuple[float, Any]]:
        """Percentile-rank `players` by `field` within its own population,
        keyed by normalized full name rather than list index (used for
        cross-source matching against a *different* list than the one being
        output). Returns {name: (percentile, raw_value)}.
        """
        items = []
        name_by_index: Dict[int, str] = {}
        for idx, player in enumerate(players):
            value = player.get(field)
            if value is None:
                continue
            if field == "search_rank" and value >= SLEEPER_UNRANKED_SENTINEL:
                continue
            # "full_name"/"name" cover Sleeper/ESPN-shaped dicts; "player_name"
            # is FantasyPros' own field (see fantasypros_service.py).
            name = normalize_player_name(
                player.get("full_name") or player.get("name") or player.get("player_name")
            )
            if not name:
                continue
            name_by_index[idx] = name
            items.append((idx, value))

        pct_by_index = _percentile_map(items, reverse=reverse)
        result: Dict[str, Tuple[float, Any]] = {}
        for idx, pct in pct_by_index.items():
            name = name_by_index[idx]
            # Duplicate normalized names are rare (real player pools don't
            # usually collide) but not impossible; keep whichever entry
            # scores better rather than picking arbitrarily.
            if name not in result or pct > result[name][0]:
                result[name] = (pct, players[idx].get(field))
        return result


consensus_ranking_service = ConsensusRankingService()
