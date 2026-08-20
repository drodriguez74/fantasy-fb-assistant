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


# Fantasy-relevant positions we're willing to recommend off the waiver wire.
_WAIVER_ELIGIBLE_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF"}


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
        limit: int = 20
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
                confidence = round(add_count / max_add_count, 3)

                recommendations.append({
                    'player_id': player_id,
                    'player_name': name,
                    'position': player_data.get('position'),
                    'team': player_data.get('team'),
                    'recommendation_type': RecommendationType.ADD.value,
                    'priority': rec_priority,
                    'confidence_score': confidence,
                    'reason': (
                        f"Trending add: {add_count:,} adds across Sleeper fantasy "
                        f"leagues in the last 24 hours."
                    ),
                    'projected_points': None,
                    'ownership_percentage': None,
                    'trend_direction': 'up',
                    'add_count_24h': add_count,
                })

                if len(recommendations) >= limit:
                    break

            return recommendations

        except Exception as e:
            logger.error(f"Error getting live trending waiver recommendations: {str(e)}")
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
        
        # Temporarily skip historical performance requirement - generate recommendations based on current data
        recent_performances = []
        
        # Skip players with very high ownership (not waiver eligible)
        if player.ownership_percentage and player.ownership_percentage > 80.0:
            return None
        
        # Calculate component scores
        performance_score = self._calculate_performance_score(recent_performances)
        opportunity_score = self._calculate_opportunity_score(player, recent_performances)
        matchup_score = await self._calculate_matchup_score(player, week, season)
        ownership_score = self._calculate_ownership_score(player)
        trend_score = self._calculate_trend_score(recent_performances)
        
        # Calculate composite score
        total_score = (
            performance_score * self.weights['recent_performance'] +
            opportunity_score * self.weights['opportunity_trend'] +
            matchup_score * self.weights['upcoming_matchups'] +
            ownership_score * self.weights['ownership_level'] +
            trend_score * self.weights['target_share_trend']
        )
        
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
            'reason': reason,
            'projected_points': self._calculate_projected_points(recent_performances),
            'ownership_percentage': player.ownership_percentage or 0.0,
            'trend_direction': self._get_trend_direction(trend_score),
            'component_scores': {
                'performance': performance_score,
                'opportunity': opportunity_score,
                'matchup': matchup_score,
                'ownership': ownership_score,
                'trend': trend_score
            }
        }
    
    def _calculate_performance_score(self, performances: List[PlayerHistoricalPerformance]) -> float:
        """Score based on recent fantasy performance"""
        if not performances:
            # Use projected points as a proxy when no historical data
            return 0.5  # Default moderate score for players without history
        
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
    ) -> float:
        """Score based on opportunity metrics (targets, carries, snaps)"""
        if not performances:
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
    
    def _calculate_trend_score(self, performances: List[PlayerHistoricalPerformance]) -> float:
        """Score based on trending direction"""
        if len(performances) < 2:
            return 0.5
        
        points = [p.fantasy_points_ppr or 0 for p in performances]
        if len(points) < 2:
            return 0.5
        
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
        performance_score: float,
        opportunity_score: float,
        matchup_score: float
    ) -> str:
        """Generate human-readable reason for recommendation"""
        
        reasons = []
        
        # Performance-based reasons
        if performance_score > 0.7:
            recent_avg = np.mean([p.fantasy_points_ppr or 0 for p in performances[:3]])
            reasons.append(f"Strong recent performance ({recent_avg:.1f} PPR avg)")
        
        # Opportunity reasons
        if opportunity_score > 0.6:
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