"""
Waiver Wire Intelligence Service

Provides smart waiver wire recommendations, trend analysis, and weekly player evaluations.
"""

import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import logging
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, func

from app.models.player import Player, Position
from app.models.waiver_wire import (
    WaiverWireRecommendation, WaiverWireTrend, PlayerEvaluation, WaiverWireAlert,
    RecommendationType, Priority
)
from app.models.historical_performance import PlayerHistoricalPerformance
from app.services.sleeper_service import SleeperService
from app.services.matchup_analysis_service import MatchupAnalysisService

logger = logging.getLogger(__name__)


def _is_rosterable_player(player_data: Dict[str, Any]) -> bool:
    """Determine whether a Sleeper player record represents someone currently
    on an active NFL roster (i.e. not retired/free agent/practice squad cut).

    Mirrors the fix applied to the Draft Assistant's positional-rankings
    endpoint for this same underlying data source: Sleeper's `status` field
    alone is unreliable (long-retired players like Frank Gore or Adrian
    Peterson are still tagged `status: "Active"`), but they also carry
    `team: null` once they're off an NFL roster, so require both.
    """
    return bool(player_data.get("team")) and player_data.get("status") == "Active"


def _player_full_name(player_data: Dict[str, Any]) -> str:
    """Same full-name derivation used throughout this module -- extracted
    so the real-availability filter below can check a name before the
    per-recommendation loop computes its own copy.
    """
    return player_data.get("full_name") or " ".join(
        filter(None, [player_data.get("first_name"), player_data.get("last_name")])
    ) or "Unknown Player"


# Fantasy-relevant positions we're willing to recommend off the waiver wire.
_WAIVER_ELIGIBLE_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF"}

# Same fallback used elsewhere in this codebase (roster_grading.py,
# post_draft_analysis_service.py) when no real per-league starter
# requirements are available.
_FALLBACK_STARTERS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1}


class WaiverWireService:
    """Intelligent waiver wire analysis and recommendations"""
    
    def __init__(self, db: Session):
        self.db = db
        self.sleeper_service = SleeperService()
        self.matchup_service = MatchupAnalysisService(db)
        
        # Scoring weights for different factors
        self.weights = {
            'recent_performance': 0.20,
            'upcoming_matchups': 0.25,  # Increased weight for matchups
            'opportunity_trend': 0.20,
            'ownership_level': 0.15,
            'injury_context': 0.10,
            'target_share_trend': 0.10
        }
    
    async def generate_weekly_recommendations(
        self, 
        week: int, 
        season: int = 2024,
        max_recommendations: int = 50
    ) -> List[Dict[str, Any]]:
        """Generate comprehensive waiver wire recommendations for the week"""
        try:
            logger.info(f"Generating waiver recommendations for Week {week}, {season}")
            
            # Get all players with recent data
            recent_cutoff = datetime.now() - timedelta(days=14)
            candidates = self.db.query(Player).filter(
                Player.updated_at >= recent_cutoff,
                Player.ownership_percentage < 80.0  # Focus on available players
            ).all()
            
            recommendations = []
            
            for player in candidates:
                try:
                    # Calculate recommendation score
                    rec_data = await self._evaluate_player_for_waiver(player, week, season)
                    
                    if rec_data and rec_data['score'] > 0.3:  # Minimum threshold
                        recommendations.append(rec_data)
                        
                except Exception as e:
                    logger.warning(f"Error evaluating {player.name}: {str(e)}")
                    continue
            
            # Sort by score and priority
            recommendations.sort(key=lambda x: (x['priority_weight'], x['score']), reverse=True)
            
            # Save top recommendations to database
            await self._save_recommendations(recommendations[:max_recommendations], week, season)
            
            return recommendations[:max_recommendations]
            
        except Exception as e:
            logger.error(f"Error generating waiver recommendations: {str(e)}")
            return []
    
    async def get_live_trending_recommendations(
        self,
        position: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 20,
        user_roster: Optional[List[Dict[str, Any]]] = None,
        league_settings: Optional[Dict[str, Any]] = None,
        available_player_names: Optional[set] = None,
    ) -> List[Dict[str, Any]]:
        """Real waiver-add recommendations sourced from Sleeper's live
        trending-add feed (players actually being added across real fantasy
        leagues in the last 24 hours).

        `generate_weekly_recommendations` above sources candidates from the
        local `Player` table, requiring `updated_at` within the last 14 days.
        That table has no ingestion pipeline behind it -- it's essentially
        empty/stale in a fresh deployment (14 rows total, none updated
        recently), so that path returns nothing for any real user, which is
        why the Recommendations tab shows "No recommendations found" even
        with the widest possible filters. This method draws instead from the
        same live Sleeper source already used successfully elsewhere in the
        app (Draft Assistant trending candidates / positional rankings).

        `user_roster`/`league_settings` are both optional and backward
        compatible -- when neither is supplied, ranking is unweighted, exactly
        as before. When both are supplied, real per-league starter
        requirements (via DraftAssistantService._effective_position_requirements,
        the same FLEX-aware helper roster_grading.py/post_draft_analysis_service.py
        already use) are used to boost/penalize candidates at a position the
        user's real roster actually needs/is overstocked at.

        `available_player_names`: real, lower-cased free-agent names for
        this specific connected league (from the platform's own free-agent
        API -- e.g. espn_service_enhanced.get_available_players,
        yahoo_service.get_available_players, or "not on any of this
        league's real rosters" for Sleeper), optional. Sleeper's global
        trending-add feed has no idea which players are actually free
        agents in any one specific league -- a player trending across
        Sleeper broadly can easily already be rostered by someone else in
        THIS league (confirmed live: MarShawn Lloyd was recommended for a
        real ESPN league despite being rostered by another team in it, not
        a free agent at all). When omitted, behavior is unchanged
        (unfiltered by real per-league availability) -- callers with real
        league context should pass this whenever they have it.
        """
        try:
            # Over-fetch: some trending adds will be filtered out by the
            # active-roster check or an optional position filter.
            pool_size = max(limit * 5, 100)
            trending = await self.sleeper_service.get_trending_players("add", 24, pool_size)

            if trending and isinstance(trending[0], dict) and "error" in trending[0]:
                logger.error(f"Sleeper trending-add lookup failed: {trending[0]['error']}")
                return []

            all_players = await self.sleeper_service.get_all_players()
            if isinstance(all_players, dict) and "error" in all_players:
                logger.error(f"Sleeper player lookup failed: {all_players['error']}")
                return []

            target_position = position.upper() if position else None

            # Real roster-need weighting: only computed when the caller
            # actually supplied both a roster and league settings, so
            # existing callers that pass neither stay unweighted.
            position_requirements: Optional[Dict[str, int]] = None
            roster_position_counts: Dict[str, int] = {}
            if user_roster is not None and league_settings is not None:
                for entry in user_roster:
                    pos = (entry.get("position") or "").upper()
                    if pos:
                        roster_position_counts[pos] = roster_position_counts.get(pos, 0) + 1

                raw_starters = dict(league_settings.get("starters") or {}) or dict(_FALLBACK_STARTERS)

                from app.services.roster_requirements import effective_position_requirements
                position_requirements = effective_position_requirements(
                    roster_position_counts, {"starters": raw_starters}
                )

            # Real bye-week awareness: current NFL week, computed the same
            # way matchup_analysis_service does everywhere else in this app.
            try:
                current_week = self.matchup_service.get_current_week()
            except Exception as e:
                logger.warning(f"Could not determine current NFL week for bye-week check: {str(e)}")
                current_week = None

            # Honest scoring-format context: pass through the league's real
            # scoring format if the caller supplied one, without pretending
            # it drove the whole ranking.
            league_scoring_context = None
            is_high_ppr = False
            team_count = league_settings.get("team_count") if league_settings else None
            if league_settings:
                scoring_format = league_settings.get("scoring_format")
                ppr_value = league_settings.get("points_per_reception")
                if scoring_format or ppr_value is not None:
                    league_scoring_context = {
                        "scoring_format": scoring_format,
                        "points_per_reception": ppr_value,
                    }
                if isinstance(ppr_value, (int, float)):
                    is_high_ppr = ppr_value >= 0.75
                elif isinstance(scoring_format, str):
                    is_high_ppr = "ppr" in scoring_format.lower() and "half" not in scoring_format.lower()

            candidates = []
            for entry in trending:
                sleeper_id = entry.get("player_id")
                add_count = entry.get("count", 0)
                player_data = all_players.get(sleeper_id)

                if not player_data or not _is_rosterable_player(player_data):
                    continue

                player_position = player_data.get("position")
                if player_position not in _WAIVER_ELIGIBLE_POSITIONS:
                    continue
                if target_position and player_position != target_position:
                    continue

                # Real per-league availability check -- see this method's
                # docstring. Skip (not just deprioritize) a Sleeper-trending
                # player who isn't actually a free agent in this specific
                # league; recommending an already-rostered player is a real
                # correctness bug, not a ranking nuance.
                if available_player_names is not None:
                    if _player_full_name(player_data).lower() not in available_player_names:
                        continue

                candidates.append((sleeper_id, player_data, add_count))

            if not candidates:
                return []

            # Sleeper returns trending entries pre-sorted by count, but sort
            # explicitly since filtering doesn't guarantee order is preserved
            # in every runtime.
            candidates.sort(key=lambda c: c[2], reverse=True)

            max_add_count = candidates[0][2] or 1
            total = len(candidates)

            recommendations = []
            for rank, (sleeper_id, player_data, add_count) in enumerate(candidates):
                # Real per-candidate position -- Python for-loop variables
                # aren't scoped, so without reassigning this here, the
                # roster-need weighting below silently used whatever
                # position the LAST entry in the candidate-building loop
                # above happened to have, for every single recommendation
                # in this loop. That's a real, confirmed bug: every
                # candidate regardless of actual position was getting the
                # same "Your roster is already deep at WR" reason text.
                player_position = player_data.get("position")
                rec_priority = self._priority_from_rank(rank, total)

                if priority and rec_priority != priority.lower():
                    continue

                try:
                    player_id = int(sleeper_id)
                except (TypeError, ValueError):
                    player_id = sleeper_id

                name = player_data.get("full_name") or " ".join(
                    filter(None, [player_data.get("first_name"), player_data.get("last_name")])
                ) or "Unknown Player"

                # Confidence is a real, deterministic function of the actual
                # Sleeper add-count data (this player's adds relative to the
                # single most-added player in today's pool) -- not a flat or
                # templated value.
                confidence = add_count / max_add_count
                reason_parts = [
                    f"Trending add: {add_count:,} adds across Sleeper fantasy "
                    f"leagues in the last 24 hours."
                ]

                # Real roster-need weighting. league_label mentions the
                # league's real, connected team count (UserLeague.league_size,
                # threaded through via league_settings["team_count"]) when
                # known -- roster depth reads very differently in a 12-team
                # league (thin free-agent pool, holding bench depth matters
                # more) than an 8-team league (deep pool, less reason to
                # hoard), so the reason text should say which one this is
                # rather than talking about "your roster" in the abstract.
                league_label = f"your {team_count}-team league" if team_count else "your league"
                roster_need = None
                if position_requirements is not None:
                    required = position_requirements.get(player_position, 0)
                    actual = roster_position_counts.get(player_position, 0)
                    if required > 0 and actual < required:
                        roster_need = "needs_attention"
                        confidence *= 1.3
                        reason_parts.append(
                            f"In {league_label}, your roster currently has {actual}/{required} required {player_position}s."
                        )
                    elif actual > required + 1:
                        roster_need = "overstocked"
                        confidence *= 0.7
                        reason_parts.append(
                            f"In {league_label}, your roster is already deep at {player_position} ({actual} rostered)."
                        )

                # Real bye-week awareness: try to find a local Player row for
                # this Sleeper player (by sleeper_id) to check its real
                # bye_week. Best-effort -- the local Player table is sparse,
                # so this only fires when a real match exists.
                bye_week_flag = False
                local_bye_week = None
                try:
                    local_player = self.db.query(Player).filter(
                        Player.sleeper_id == str(sleeper_id)
                    ).first()
                except Exception:
                    local_player = None

                if local_player and local_player.bye_week:
                    local_bye_week = local_player.bye_week
                    if current_week is not None and local_bye_week == current_week:
                        bye_week_flag = True
                        confidence *= 0.5
                        reason_parts.append(
                            f"On bye in Week {current_week} -- cannot play this week."
                        )

                # Mild, honest pass-catcher reweighting: only applied when we
                # have a real local target_share for this player AND the
                # league's real scoring format is PPR/high-PPR. No fabricated
                # per-player point precision -- this nudges an already-real
                # signal (target_share), it doesn't invent one.
                pass_catcher_boost = False
                if (
                    is_high_ppr
                    and local_player
                    and player_position in ("RB", "WR")
                    and local_player.target_share
                    and local_player.target_share >= 15.0
                ):
                    pass_catcher_boost = True
                    confidence *= 1.1
                    reason_parts.append(
                        f"Strong target share ({local_player.target_share:.1f}%) in a PPR league."
                    )

                recommendations.append({
                    'player_id': player_id,
                    'player_name': name,
                    'position': player_data.get('position'),
                    'team': player_data.get('team'),
                    'recommendation_type': RecommendationType.ADD.value,
                    'priority': rec_priority,
                    'confidence_score': round(confidence, 3),
                    'reason': " ".join(reason_parts),
                    'projected_points': None,
                    'ownership_percentage': None,
                    'trend_direction': 'up',
                    'add_count_24h': add_count,
                    'roster_need': roster_need,
                    'bye_week': local_bye_week,
                    'bye_week_flag': bye_week_flag,
                    'pass_catcher_boost': pass_catcher_boost,
                    'league_scoring_context': league_scoring_context,
                })

            # When roster-need weighting is active, re-rank by the real
            # weighted confidence score rather than raw add-count order, so
            # personalization actually changes which players surface (not
            # just a cosmetic number) -- otherwise a boosted RB could still
            # be cut off by `limit` before it's ever shown.
            if position_requirements is not None:
                recommendations.sort(key=lambda r: r['confidence_score'], reverse=True)

            return recommendations[:limit]

        except Exception as e:
            logger.error(f"Error getting live trending waiver recommendations: {str(e)}")
            return []

    async def get_live_trending_players(
        self,
        trend_direction: str = "up",
        position: Optional[str] = None,
        limit: int = 15
    ) -> List[Dict[str, Any]]:
        """Real "who's trending on the waiver wire" view, sourced directly
        from Sleeper's live trending add/drop feed.

        This backs GET /waiver-wire/trending. That endpoint used to query
        WaiverWireTrend, a table nothing in this codebase has ever written
        to -- always empty in practice, and its schema (ownership_change,
        pickup_rate, drop_rate, recent_performance, upcoming_matchup_rating)
        would require real per-week ownership deltas this app has no
        ingestion pipeline for. Building that real historical ingestion
        isn't viable as a small extension either: WaiverWireTrend.player_id
        is a FK to the local `Player` table, which holds only a handful of
        seeded rows, while Sleeper's live trending players are drawn from
        its full ~11k player universe -- nearly every trending player has no
        local Player row a snapshot could attach to.

        Rather than keep serving fabricated stats from a table nothing
        populates, this reshapes the same real, live Sleeper trending feed
        `get_live_trending_recommendations` already uses -- for *both* "add"
        and "drop" trend types, which is real information that method
        doesn't expose (it only ever looks at "add"). This is an honest live
        snapshot of the last 24 hours, not a historical time series.
        """
        try:
            if trend_direction == "up":
                trend_types = [("add", "up")]
            elif trend_direction == "down":
                trend_types = [("drop", "down")]
            else:
                trend_types = [("add", "up"), ("drop", "down")]

            target_position = position.upper() if position else None
            pool_size = max(limit * 5, 100)

            all_players = await self.sleeper_service.get_all_players()
            if isinstance(all_players, dict) and "error" in all_players:
                logger.error(f"Sleeper player lookup failed: {all_players['error']}")
                return []

            results = []
            for trend_type, direction_label in trend_types:
                trending = await self.sleeper_service.get_trending_players(trend_type, 24, pool_size)
                if trending and isinstance(trending[0], dict) and "error" in trending[0]:
                    logger.error(f"Sleeper trending-{trend_type} lookup failed: {trending[0]['error']}")
                    continue

                for entry in trending:
                    sleeper_id = entry.get("player_id")
                    count = entry.get("count", 0)
                    player_data = all_players.get(sleeper_id)

                    if not player_data or not _is_rosterable_player(player_data):
                        continue

                    player_position = player_data.get("position")
                    if player_position not in _WAIVER_ELIGIBLE_POSITIONS:
                        continue
                    if target_position and player_position != target_position:
                        continue

                    try:
                        player_id = int(sleeper_id)
                    except (TypeError, ValueError):
                        player_id = sleeper_id

                    name = player_data.get("full_name") or " ".join(
                        filter(None, [player_data.get("first_name"), player_data.get("last_name")])
                    ) or "Unknown Player"

                    results.append({
                        'player_id': player_id,
                        'player_name': name,
                        'position': player_position,
                        'team': player_data.get('team'),
                        'trend_direction': direction_label,
                        'count_24h': count,
                        'reason': (
                            f"{count:,} {'adds' if direction_label == 'up' else 'drops'} "
                            f"across Sleeper fantasy leagues in the last 24 hours."
                        ),
                    })

            # Real signal, ranked by the magnitude of the actual 24h count.
            results.sort(key=lambda r: r['count_24h'], reverse=True)
            return results[:limit]

        except Exception as e:
            logger.error(f"Error getting live trending players: {str(e)}")
            return []

    @staticmethod
    def _priority_from_rank(rank: int, total: int) -> str:
        """Bucket a player into a priority tier based on where their real
        Sleeper add-count ranks within today's live trending pool (top 10% =
        urgent, next 20% = high, next 30% = medium, next 25% = low, rest =
        watch). Percentile-based rather than a fixed count threshold, since
        raw add volumes shift a lot with the time of year.
        """
        percentile = rank / total
        if percentile < 0.10:
            return Priority.URGENT.value
        elif percentile < 0.30:
            return Priority.HIGH.value
        elif percentile < 0.60:
            return Priority.MEDIUM.value
        elif percentile < 0.85:
            return Priority.LOW.value
        else:
            return Priority.WATCH.value

    async def _evaluate_player_for_waiver(
        self, 
        player: Player, 
        week: int, 
        season: int
    ) -> Optional[Dict[str, Any]]:
        """Evaluate a single player for waiver wire potential"""

        # Real historical-performance query, mirroring _calculate_drop_score's
        # exact pattern -- this local historical data is known to be sparse,
        # so `recent_performances` will genuinely come back empty for most
        # players (that's expected and handled honestly below, not treated
        # as a bug).
        recent_performances = self.db.query(PlayerHistoricalPerformance).filter(
            and_(
                PlayerHistoricalPerformance.player_id == player.id,
                PlayerHistoricalPerformance.season == season,
                PlayerHistoricalPerformance.week >= max(1, week - 4)
            )
        ).order_by(PlayerHistoricalPerformance.week.desc()).all()

        # Skip players with very high ownership (not waiver eligible)
        if player.ownership_percentage and player.ownership_percentage > 80.0:
            return None

        # Calculate component scores. performance/opportunity/trend can come
        # back None ("insufficient data") rather than a fabricated flat 0.5
        # when there's genuinely nothing real to compute from -- see each
        # function's docstring.
        performance_score = self._calculate_performance_score(recent_performances)
        opportunity_score = self._calculate_opportunity_score(player, recent_performances)
        matchup_score = await self._calculate_matchup_score(player, week, season)
        ownership_score = self._calculate_ownership_score(player)
        trend_score = self._calculate_trend_score(recent_performances)

        # Composite score: drop any component that came back None and
        # renormalize the remaining weights over what's left, the same
        # pattern grading.combined_grade uses (missing data shrinks the
        # basis for the score, it never gets silently treated as 0 or a
        # fabricated default). matchup_score/ownership_score are always
        # real (they don't depend on recent_performances), so they're
        # always included.
        weighted_components: Dict[str, Tuple[float, float]] = {
            'upcoming_matchups': (matchup_score, self.weights['upcoming_matchups']),
            'ownership_level': (ownership_score, self.weights['ownership_level']),
        }
        if performance_score is not None:
            weighted_components['recent_performance'] = (performance_score, self.weights['recent_performance'])
        if opportunity_score is not None:
            weighted_components['opportunity_trend'] = (opportunity_score, self.weights['opportunity_trend'])
        if trend_score is not None:
            weighted_components['target_share_trend'] = (trend_score, self.weights['target_share_trend'])

        total_weight = sum(w for _, w in weighted_components.values()) or 1.0
        total_score = sum(s * w for s, w in weighted_components.values()) / total_weight

        # Data-confidence indicator (mirrors the frontend's three-state
        # DataConfidenceBadge: computed / heuristic / insufficient) so a
        # caller can render honestly rather than the response implying full
        # personalization when the underlying historical data was thin.
        history_backed = [performance_score, opportunity_score, trend_score]
        present_count = sum(1 for c in history_backed if c is not None)
        if present_count == len(history_backed):
            data_confidence = "computed"
        elif present_count == 0:
            data_confidence = "insufficient"
        else:
            data_confidence = "heuristic"

        # Determine recommendation type and priority
        rec_type, priority = self._determine_recommendation_type(
            total_score, player, recent_performances
        )

        if rec_type == RecommendationType.AVOID:
            return None

        # Generate reasoning
        reason = self._generate_recommendation_reason(
            player, recent_performances, performance_score,
            opportunity_score, matchup_score
        )

        return {
            'player_id': player.id,
            'player_name': player.name,
            'position': player.position.value,
            'team': player.team,
            'recommendation_type': rec_type.value,
            'priority': priority.value,
            'priority_weight': self._get_priority_weight(priority),
            'score': total_score,
            'confidence': min(1.0, total_score * 1.2),
            'data_confidence': data_confidence,
            'reason': reason,
            'projected_points': self._calculate_projected_points(recent_performances),
            'ownership_percentage': player.ownership_percentage or 0.0,
            'trend_direction': self._get_trend_direction(trend_score) if trend_score is not None else 'unknown',
            'component_scores': {
                'performance': performance_score,
                'opportunity': opportunity_score,
                'matchup': matchup_score,
                'ownership': ownership_score,
                'trend': trend_score
            }
        }
    
    def _calculate_performance_score(self, performances: List[PlayerHistoricalPerformance]) -> Optional[float]:
        """Score based on recent fantasy performance.

        Returns None ("insufficient data") when there's no real historical
        performance to compute from, rather than a fabricated flat 0.5 --
        the caller drops this component and renormalizes the remaining
        weights (see grading.combined_grade's same pattern).
        """
        if not performances:
            return None

        # Weight recent games more heavily
        weights = [1.0, 0.8, 0.6, 0.4][:len(performances)]
        points = [p.fantasy_points_ppr or 0 for p in performances]
        
        if not points:
            return 0.0
        
        weighted_avg = sum(p * w for p, w in zip(points, weights)) / sum(weights)
        
        # Normalize based on position expectations
        position_benchmarks = {
            Position.QB: 18.0,
            Position.RB: 12.0,
            Position.WR: 10.0,
            Position.TE: 8.0
        }
        
        benchmark = position_benchmarks.get(performances[0].player.position, 10.0)
        return min(1.0, weighted_avg / benchmark)
    
    def _calculate_opportunity_score(
        self,
        player: Player,
        performances: List[PlayerHistoricalPerformance]
    ) -> Optional[float]:
        """Score based on opportunity metrics (targets, carries, snaps).

        Returns None ("insufficient data") when there's neither historical
        performance data nor any real current opportunity field
        (target_share/snap_count_percentage) to compute from -- reporting a
        flat 0.0 in that case would look like a real "no opportunity"
        signal when the truth is simply "unknown."
        """
        if not performances:
            if player.target_share is None and player.snap_count_percentage is None:
                return None
            # Use current player data when no historical data
            score = 0.0
            if player.target_share:
                score += min(1.0, player.target_share / 20.0) * 0.5
            if player.snap_count_percentage:
                score += min(1.0, player.snap_count_percentage / 80.0) * 0.5
            return score

        # Recent snap percentage trend
        snap_percentages = [p.snap_percentage for p in performances if p.snap_percentage]
        if snap_percentages and len(snap_percentages) >= 2:
            snap_trend = (snap_percentages[0] - snap_percentages[-1]) / len(snap_percentages)
        else:
            snap_trend = 0
        
        # Target share for pass catchers
        target_shares = [p.target_share for p in performances if p.target_share]
        if target_shares and len(target_shares) >= 2:
            target_trend = (target_shares[0] - target_shares[-1]) / len(target_shares)
        else:
            target_trend = 0
        
        # Current opportunity level
        current_snap = player.snap_count_percentage or 0
        current_target = player.target_share or 0
        
        # Composite opportunity score
        opportunity_base = min(1.0, (current_snap / 70.0 + current_target / 20.0) / 2)
        opportunity_trend = max(-0.3, min(0.3, (snap_trend + target_trend) / 20.0))
        
        return max(0.0, min(1.0, opportunity_base + opportunity_trend))
    
    async def _calculate_matchup_score(self, player: Player, week: int, season: int) -> float:
        """Score based on upcoming matchup difficulty using live defensive rankings"""
        try:
            position = player.position.value if player.position else "UNKNOWN"
            
            # Get upcoming matchup analysis
            matchup_analysis = self.matchup_service.analyze_player_upcoming_matchups(player, weeks_ahead=2)
            
            if "error" in matchup_analysis or not matchup_analysis.get("upcoming_matchups"):
                # Fallback to basic position scoring
                position_matchup_base = {
                    "QB": 0.6,
                    "RB": 0.5, 
                    "WR": 0.7,
                    "TE": 0.6,
                    "K": 0.4,
                    "DEF": 0.5
                }
                return position_matchup_base.get(position, 0.5)
            
            # Convert matchup rating (1-10 scale) to score (0-1 scale)
            avg_matchup_rating = matchup_analysis.get("average_matchup_rating", 5.0)
            matchup_score = (avg_matchup_rating - 1) / 9  # Convert 1-10 to 0-1
            
            # Cap the score between 0 and 1
            return max(0.0, min(1.0, matchup_score))
            
        except Exception as e:
            logger.error(f"Error calculating matchup score for {player.name}: {str(e)}")
            # Fallback scoring
            position_matchup_base = {
                "QB": 0.6, "RB": 0.5, "WR": 0.7, "TE": 0.6, "K": 0.4, "DEF": 0.5
            }
            position = player.position.value if player.position else "UNKNOWN"
            return position_matchup_base.get(position, 0.5)
    
    def _calculate_ownership_score(self, player: Player) -> float:
        """Higher score for lower-owned players (more available)"""
        ownership = player.ownership_percentage or 0
        if ownership >= 80:
            return 0.0  # Too widely owned
        elif ownership >= 60:
            return 0.2
        elif ownership >= 40:
            return 0.5
        elif ownership >= 20:
            return 0.8
        else:
            return 1.0  # Low ownership = high availability
    
    def _calculate_trend_score(self, performances: List[PlayerHistoricalPerformance]) -> Optional[float]:
        """Score based on trending direction.

        Returns None ("insufficient data") when there aren't at least two
        real historical data points to fit a trend from, rather than a
        fabricated flat 0.5.
        """
        if len(performances) < 2:
            return None

        points = [p.fantasy_points_ppr or 0 for p in performances]
        if len(points) < 2:
            return None

        # Simple linear trend
        trend = np.polyfit(range(len(points)), points[::-1], 1)[0]
        
        # Normalize trend score
        if trend > 2:
            return 1.0
        elif trend > 0:
            return 0.5 + (trend / 4.0)
        elif trend > -2:
            return 0.5 + (trend / 4.0)
        else:
            return 0.0
    
    def _determine_recommendation_type(
        self, 
        score: float, 
        player: Player, 
        performances: List[PlayerHistoricalPerformance]
    ) -> Tuple[RecommendationType, Priority]:
        """Determine recommendation type and priority based on score and context"""
        
        # Check for injury replacement situations
        if player.trending_direction == "UP" and score > 0.7:
            return RecommendationType.ADD, Priority.URGENT
        
        # High scoring players
        if score >= 0.8:
            return RecommendationType.ADD, Priority.HIGH
        elif score >= 0.6:
            return RecommendationType.ADD, Priority.MEDIUM
        elif score >= 0.4:
            return RecommendationType.ADD, Priority.LOW
        
        # Stash candidates (young players with upside)
        if player.is_rookie and score >= 0.3:
            return RecommendationType.STASH, Priority.LOW
        
        # Watch list
        if score >= 0.3:
            return RecommendationType.ADD, Priority.WATCH
        
        return RecommendationType.AVOID, Priority.LOW
    
    def _generate_recommendation_reason(
        self,
        player: Player,
        performances: List[PlayerHistoricalPerformance],
        performance_score: Optional[float],
        opportunity_score: Optional[float],
        matchup_score: float
    ) -> str:
        """Generate human-readable reason for recommendation"""

        reasons = []

        # Performance-based reasons
        if performance_score is not None and performance_score > 0.7:
            recent_avg = np.mean([p.fantasy_points_ppr or 0 for p in performances[:3]])
            reasons.append(f"Strong recent performance ({recent_avg:.1f} PPR avg)")
        elif performance_score is None:
            reasons.append("Insufficient recent performance data")

        # Opportunity reasons
        if opportunity_score is not None and opportunity_score > 0.6:
            if player.snap_count_percentage and player.snap_count_percentage > 60:
                reasons.append(f"High snap share ({player.snap_count_percentage:.0f}%)")
            if player.target_share and player.target_share > 15:
                reasons.append(f"Strong target share ({player.target_share:.1f}%)")
        
        # Trending reasons
        if player.trending_direction == "UP":
            reasons.append("Trending upward in leagues")
        
        # Matchup reasons
        if matchup_score > 0.7:
            reasons.append("Favorable upcoming matchups")
        
        # Injury/situation reasons
        if player.trending_count and player.trending_count > 1000:
            reasons.append("High waiver activity suggests opportunity")
        
        if not reasons:
            reasons.append("Solid waiver wire option with upside")
        
        return ". ".join(reasons) + "."
    
    def _calculate_projected_points(self, performances: List[PlayerHistoricalPerformance]) -> float:
        """Project next week's points based on recent performance"""
        if not performances:
            return 0.0
        
        # Weight recent games more heavily for projection
        weights = [1.0, 0.8, 0.6][:len(performances)]
        points = [p.fantasy_points_ppr or 0 for p in performances]
        
        if not points:
            return 0.0
        
        return sum(p * w for p, w in zip(points, weights)) / sum(weights)
    
    def _get_trend_direction(self, trend_score: float) -> str:
        """Convert trend score to direction string"""
        if trend_score > 0.6:
            return "up"
        elif trend_score < 0.4:
            return "down"
        else:
            return "stable"
    
    def _get_priority_weight(self, priority: Priority) -> int:
        """Convert priority to numeric weight for sorting"""
        weights = {
            Priority.URGENT: 5,
            Priority.HIGH: 4,
            Priority.MEDIUM: 3,
            Priority.LOW: 2,
            Priority.WATCH: 1
        }
        return weights.get(priority, 1)
    
    async def _save_recommendations(
        self, 
        recommendations: List[Dict[str, Any]], 
        week: int, 
        season: int
    ) -> None:
        """Save recommendations to database"""
        try:
            # Clear existing recommendations for this week
            self.db.query(WaiverWireRecommendation).filter(
                and_(
                    WaiverWireRecommendation.week == week,
                    WaiverWireRecommendation.season == season
                )
            ).delete()
            
            # Save new recommendations
            for rec in recommendations:
                db_rec = WaiverWireRecommendation(
                    player_id=rec['player_id'],
                    week=week,
                    season=season,
                    recommendation_type=RecommendationType(rec['recommendation_type']),
                    priority=Priority(rec['priority']),
                    confidence_score=rec['confidence'],
                    reason=rec['reason'],
                    projected_points=rec['projected_points'],
                    ownership_percentage=rec['ownership_percentage'],
                    trend_direction=rec['trend_direction']
                )
                self.db.add(db_rec)
            
            self.db.commit()
            logger.info(f"Saved {len(recommendations)} waiver recommendations for Week {week}")
            
        except Exception as e:
            logger.error(f"Error saving recommendations: {str(e)}")
            self.db.rollback()
    
    async def get_matchup_driven_defense_recommendations(
        self, 
        current_defense: Optional[str] = None,
        week: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get defensive streaming recommendations based on live matchup analysis"""
        try:
            if not week:
                week = self.matchup_service.get_current_week()
            
            # Get defensive streaming targets
            streaming_analysis = self.matchup_service.recommend_defensive_streaming(current_defense, week)
            
            if "error" in streaming_analysis:
                return streaming_analysis
            
            # Enhanced recommendations with availability check
            enhanced_recommendations = []
            
            for recommendation in streaming_analysis["streaming_recommendations"]:
                team_abbr = recommendation["team"]
                
                # Find defense player object
                defense_player = self.db.query(Player).filter(
                    and_(
                        Player.team == team_abbr,
                        Player.position == Position.DEF
                    )
                ).first()
                
                if defense_player:
                    # Check ownership level for availability
                    ownership = defense_player.ownership_percentage or 0
                    availability_tier = (
                        "Widely Available" if ownership < 20 else
                        "Moderately Available" if ownership < 50 else
                        "Rarely Available" if ownership < 80 else
                        "Likely Unavailable"
                    )
                    
                    enhanced_recommendations.append({
                        "player_id": defense_player.id,
                        "team_name": f"{team_abbr} Defense",
                        "team_abbreviation": team_abbr,
                        "opponent": recommendation["opponent"],
                        "is_home_game": recommendation["is_home"],
                        "matchup_rating": recommendation["matchup_rating"],
                        "improvement_over_current": recommendation.get("improvement_over_current", 0),
                        "ownership_percentage": ownership,
                        "availability_tier": availability_tier,
                        "recommendation_strength": recommendation.get("recommendation", "Stream"),
                        "key_factors": recommendation["key_factors"],
                        "confidence": recommendation["confidence"],
                        "waiver_priority": (
                            "High" if recommendation["matchup_rating"] >= 8.0 and ownership < 30 else
                            "Medium" if recommendation["matchup_rating"] >= 6.5 and ownership < 50 else
                            "Low"
                        )
                    })
            
            # Sort by combination of matchup rating and availability
            enhanced_recommendations.sort(
                key=lambda x: (x["matchup_rating"] * (1 - x["ownership_percentage"]/100)), 
                reverse=True
            )
            
            result = {
                "week": week,
                "current_defense": current_defense,
                "streaming_recommendations": enhanced_recommendations[:8],
                "current_defense_analysis": streaming_analysis.get("current_defense_analysis"),
                "defenses_to_avoid": streaming_analysis.get("defenses_to_avoid", []),
                "analysis_notes": [
                    "Recommendations prioritize both matchup quality and availability",
                    "Higher ownership reduces waiver priority",
                    "Consider league size when evaluating availability"
                ]
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting matchup-driven defense recommendations: {str(e)}")
            return {"error": str(e)}
    
    async def get_roster_specific_matchup_recommendations(
        self, 
        user_roster: List[Dict[str, Any]], 
        week: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get matchup-specific recommendations based on user's current roster"""
        try:
            if not week:
                week = self.matchup_service.get_current_week()
            
            recommendations = {
                "week": week,
                "upgrade_opportunities": [],
                "defensive_streaming": [],
                "position_analysis": {}
            }
            
            # Analyze each roster position for matchup improvements
            for roster_entry in user_roster:
                if "player_id" not in roster_entry:
                    continue
                
                player = self.db.query(Player).filter(Player.id == roster_entry["player_id"]).first()
                if not player:
                    continue
                
                position = player.position.value if player.position else "UNKNOWN"
                
                # Get all available players at this position
                available_players = self.db.query(Player).filter(
                    and_(
                        Player.position == player.position,
                        or_(
                            Player.ownership_percentage == None,
                            Player.ownership_percentage < 60  # Available threshold
                        )
                    )
                ).all()
                
                # Find better matchup alternatives
                better_alternatives = self.matchup_service.find_better_matchup_alternatives(
                    player, available_players, weeks_ahead=2
                )
                
                if better_alternatives:
                    recommendations["upgrade_opportunities"].extend([
                        {
                            "current_player": {
                                "id": player.id,
                                "name": player.name,
                                "position": position,
                                "team": player.team
                            },
                            "alternative_player": alt["player"],
                            "matchup_improvement": alt["matchup_advantage"],
                            "recommendation_strength": alt["recommendation_strength"],
                            "priority": alt["priority"],
                            "reasoning": alt["reasoning"]
                        }
                        for alt in better_alternatives[:3]  # Top 3 alternatives per position
                    ])
                
                # Special handling for defenses
                if position == "DEF":
                    def_recommendations = await self.get_matchup_driven_defense_recommendations(
                        player.team, week
                    )
                    if "streaming_recommendations" in def_recommendations:
                        recommendations["defensive_streaming"] = def_recommendations["streaming_recommendations"][:5]
            
            # Sort upgrade opportunities by improvement potential
            recommendations["upgrade_opportunities"].sort(
                key=lambda x: x["matchup_improvement"], reverse=True
            )
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error getting roster-specific matchup recommendations: {str(e)}")
            return {"error": str(e)}
    
    async def get_recommendations_by_position(
        self, 
        position: str, 
        week: int, 
        season: int = 2024,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get waiver recommendations filtered by position"""
        try:
            # Get from database if available
            recommendations = self.db.query(WaiverWireRecommendation).join(Player).filter(
                and_(
                    WaiverWireRecommendation.week == week,
                    WaiverWireRecommendation.season == season,
                    Player.position == Position(position.upper())
                )
            ).order_by(
                desc(WaiverWireRecommendation.priority),
                desc(WaiverWireRecommendation.confidence_score)
            ).limit(limit).all()
            
            return [self._format_recommendation(rec) for rec in recommendations]
            
        except Exception as e:
            logger.error(f"Error getting recommendations by position: {str(e)}")
            return []
    
    def _format_recommendation(self, rec: WaiverWireRecommendation) -> Dict[str, Any]:
        """Format database recommendation for API response"""
        return {
            'player_id': rec.player_id,
            'player_name': rec.player.name,
            'position': rec.player.position.value,
            'team': rec.player.team,
            'recommendation_type': rec.recommendation_type.value,
            'priority': rec.priority.value,
            'confidence_score': rec.confidence_score,
            'reason': rec.reason,
            'projected_points': rec.projected_points,
            'ownership_percentage': rec.ownership_percentage,
            'trend_direction': rec.trend_direction,
            'week': rec.week,
            'season': rec.season
        }
    
    async def analyze_add_drop_candidates(
        self, 
        roster_player_ids: List[int],
        week: int,
        season: int = 2024
    ) -> Dict[str, Any]:
        """Analyze current roster for add/drop opportunities"""
        try:
            # Get current roster players
            roster_players = self.db.query(Player).filter(
                Player.id.in_(roster_player_ids)
            ).all()
            
            # Get waiver recommendations
            waiver_adds = await self.generate_weekly_recommendations(week, season, 20)
            
            # Analyze drop candidates from roster
            drop_candidates = []
            for player in roster_players:
                drop_score = await self._calculate_drop_score(player, week, season)
                if drop_score > 0.3:  # Worth considering dropping
                    drop_candidates.append({
                        'player_id': player.id,
                        'player_name': player.name,
                        'position': player.position.value,
                        'drop_score': drop_score,
                        'reason': await self._generate_drop_reason(player, drop_score)
                    })
            
            # Sort drop candidates by score
            drop_candidates.sort(key=lambda x: x['drop_score'], reverse=True)
            
            return {
                'add_candidates': waiver_adds[:10],
                'drop_candidates': drop_candidates[:5],
                'analysis_date': datetime.now().isoformat(),
                'week': week,
                'season': season
            }
            
        except Exception as e:
            logger.error(f"Error analyzing add/drop candidates: {str(e)}")
            return {'add_candidates': [], 'drop_candidates': []}
    
    async def _calculate_drop_score(self, player: Player, week: int, season: int) -> float:
        """Calculate how droppable a player is (higher = more droppable)"""
        # Get recent performance
        recent_performances = self.db.query(PlayerHistoricalPerformance).filter(
            and_(
                PlayerHistoricalPerformance.player_id == player.id,
                PlayerHistoricalPerformance.season == season,
                PlayerHistoricalPerformance.week >= max(1, week - 4)
            )
        ).order_by(PlayerHistoricalPerformance.week.desc()).all()
        
        if not recent_performances:
            return 0.5  # No data, moderate drop candidate
        
        # Poor recent performance
        recent_avg = np.mean([p.fantasy_points_ppr or 0 for p in recent_performances])
        position_benchmarks = {
            Position.QB: 15.0,
            Position.RB: 10.0,
            Position.WR: 8.0,
            Position.TE: 6.0
        }
        
        benchmark = position_benchmarks.get(player.position, 8.0)
        performance_score = max(0, 1 - (recent_avg / benchmark))
        
        # Injury concerns
        injury_score = 0.3 if player.injury_status.value in ['Doubtful', 'Out', 'IR'] else 0
        
        # Low opportunity
        opportunity_score = 0
        if player.snap_count_percentage and player.snap_count_percentage < 50:
            opportunity_score += 0.2
        if player.target_share and player.target_share < 10:
            opportunity_score += 0.2
        
        return min(1.0, performance_score + injury_score + opportunity_score)
    
    async def _generate_drop_reason(self, player: Player, drop_score: float) -> str:
        """Generate reason why player might be droppable"""
        reasons = []
        
        if drop_score > 0.7:
            reasons.append("Poor recent performance")
        
        if player.injury_status.value in ['Doubtful', 'Out', 'IR']:
            reasons.append(f"Injury concerns ({player.injury_status.value})")
        
        if player.snap_count_percentage and player.snap_count_percentage < 50:
            reasons.append("Limited playing time")
        
        if not reasons:
            reasons.append("Underperforming expectations")
        
        return ". ".join(reasons) + "."