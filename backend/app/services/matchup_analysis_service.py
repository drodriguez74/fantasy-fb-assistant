"""
Matchup Analysis Service

Provides live matchup analysis for fantasy recommendations including
defensive rankings, schedule strength, and opponent-specific insights.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, func
from datetime import datetime, timedelta

from app.models.nfl_schedule import NFLGame, NFLTeam, DefensiveMatchupRanking, TeamMatchupStrength, GameStatus
from app.models.player import Player, Position
from app.models.historical_performance import PlayerHistoricalPerformance
from app.models.waiver_wire import WaiverWireRecommendation

logger = logging.getLogger(__name__)


class MatchupAnalysisService:
    """Service for analyzing NFL matchups and defensive rankings"""
    
    def __init__(self, db: Session):
        self.db = db
        self._current_season_cache: Optional[int] = None

    def get_current_season(self) -> int:
        """Determine the real current NFL season instead of a hardcoded year.

        Previously every query in this file was pinned to the literal 2024,
        which silently returned stale-or-empty results the moment the real
        season moved on. Prefer the most recent season actually present in
        the NFL schedule data (so this stays correct once that data is
        populated for a new season); fall back to a calendar-based estimate
        when the schedule table is empty. NFL season "N" is conventionally
        the year it kicks off in and runs through the Super Bowl the
        following February, so a bare calendar year is treated as season
        N-1 for Jan/Feb (the previous season's playoffs are still resolving)
        and season N from March onward (free agency/draft/preseason prep
        for fantasy purposes already treats the new year as "the season").
        """
        if self._current_season_cache is not None:
            return self._current_season_cache

        try:
            latest_season = self.db.query(func.max(NFLGame.season)).scalar()
            if latest_season:
                self._current_season_cache = latest_season
                return latest_season
        except Exception as e:
            logger.warning(f"Could not derive season from NFLGame data: {str(e)}")

        now = datetime.utcnow()
        estimated_season = now.year if now.month >= 3 else now.year - 1
        self._current_season_cache = estimated_season
        return estimated_season

    def get_current_week(self) -> int:
        """Determine current NFL week based on schedule"""
        try:
            season = self.get_current_season()
            # Find most recent completed game or next scheduled game
            current_time = datetime.utcnow()

            # Check for games this week
            current_week_game = self.db.query(NFLGame).filter(
                and_(
                    NFLGame.season == season,
                    NFLGame.game_date <= current_time + timedelta(days=3),
                    NFLGame.game_date >= current_time - timedelta(days=3)
                )
            ).first()

            if current_week_game:
                return current_week_game.week

            # Fall back to next scheduled game
            next_game = self.db.query(NFLGame).filter(
                and_(
                    NFLGame.season == season,
                    NFLGame.game_date > current_time
                )
            ).order_by(NFLGame.game_date).first()

            return next_game.week if next_game else 1

        except Exception as e:
            logger.error(f"Error determining current week: {str(e)}")
            return 1
    
    def get_defensive_matchup_rating(
        self, 
        team_abbr: str, 
        position: str, 
        week: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get defensive matchup rating for team vs position"""
        try:
            if not week:
                week = self.get_current_week()
            
            # Get most recent defensive ranking for this team/position
            ranking = self.db.query(DefensiveMatchupRanking).filter(
                and_(
                    DefensiveMatchupRanking.team_abbreviation == team_abbr,
                    DefensiveMatchupRanking.position == position,
                    DefensiveMatchupRanking.season == self.get_current_season(),
                    DefensiveMatchupRanking.week <= week
                )
            ).order_by(DefensiveMatchupRanking.week.desc()).first()
            
            if not ranking:
                return {
                    "team": team_abbr,
                    "position": position,
                    "matchup_rating": 5.0,  # Neutral
                    "rank": 16,
                    "confidence": "Low",
                    "note": "No recent defensive data available"
                }
            
            return {
                "team": team_abbr,
                "position": position,
                "matchup_rating": ranking.matchup_rating,
                "rank_vs_position": ranking.rank_vs_position,
                "fantasy_points_allowed_avg": ranking.fantasy_points_allowed_avg,
                "recent_trend": ranking.fantasy_points_allowed_last_4,
                "confidence": "High" if ranking.confidence_score >= 0.7 else "Medium",
                "key_factors": ranking.key_factors,
                "updated_week": ranking.week
            }
            
        except Exception as e:
            logger.error(f"Error getting defensive matchup rating: {str(e)}")
            return {"error": str(e)}
    
    def analyze_player_upcoming_matchups(
        self, 
        player: Player, 
        weeks_ahead: int = 3
    ) -> Dict[str, Any]:
        """Analyze player's upcoming matchups for next few weeks"""
        try:
            current_week = self.get_current_week()
            position = player.position.value if player.position else "UNKNOWN"
            
            # Get player's upcoming games
            upcoming_games = self.db.query(NFLGame).filter(
                and_(
                    NFLGame.season == self.get_current_season(),
                    NFLGame.week.between(current_week, current_week + weeks_ahead),
                    or_(
                        NFLGame.home_team == player.team,
                        NFLGame.away_team == player.team
                    )
                )
            ).order_by(NFLGame.week).all()
            
            matchup_analysis = []
            total_matchup_score = 0
            
            for game in upcoming_games:
                # Determine opponent
                opponent = game.away_team if game.home_team == player.team else game.home_team
                is_home = game.home_team == player.team
                
                # Get defensive ranking vs this position
                def_rating = self.get_defensive_matchup_rating(opponent, position, game.week)
                
                # Calculate matchup advantage
                matchup_score = def_rating.get("matchup_rating", 5.0)
                
                # Home field adjustment
                if is_home:
                    matchup_score += 0.5
                
                matchup_analysis.append({
                    "week": game.week,
                    "opponent": opponent,
                    "is_home": is_home,
                    "game_date": game.game_date.isoformat() if game.game_date else None,
                    "matchup_rating": round(matchup_score, 1),
                    "opponent_rank_vs_position": def_rating.get("rank_vs_position", 16),
                    "fantasy_points_allowed": def_rating.get("fantasy_points_allowed_avg"),
                    "venue": game.venue,
                    "weather_forecast": game.weather_conditions
                })
                
                total_matchup_score += matchup_score
            
            # Calculate overall matchup outlook
            avg_matchup_score = total_matchup_score / len(upcoming_games) if upcoming_games else 5.0
            
            if avg_matchup_score >= 7.5:
                outlook = "Excellent"
                recommendation = "Strong start/add candidate"
            elif avg_matchup_score >= 6.5:
                outlook = "Good"
                recommendation = "Favorable matchups ahead"
            elif avg_matchup_score >= 5.5:
                outlook = "Average"
                recommendation = "Standard expectations"
            elif avg_matchup_score >= 4.0:
                outlook = "Difficult"
                recommendation = "Consider alternatives"
            else:
                outlook = "Very Difficult"
                recommendation = "Avoid if possible"
            
            return {
                "player_id": player.id,
                "player_name": player.name,
                "position": position,
                "team": player.team,
                "weeks_analyzed": len(upcoming_games),
                "average_matchup_rating": round(avg_matchup_score, 1),
                "outlook": outlook,
                "recommendation": recommendation,
                "upcoming_matchups": matchup_analysis,
                "analysis_date": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error analyzing upcoming matchups for {player.name}: {str(e)}")
            return {"error": str(e)}
    
    def find_better_matchup_alternatives(
        self, 
        current_player: Player, 
        available_players: List[Player],
        weeks_ahead: int = 2
    ) -> List[Dict[str, Any]]:
        """Find available players with better upcoming matchups"""
        try:
            # Analyze current player's matchups
            current_analysis = self.analyze_player_upcoming_matchups(current_player, weeks_ahead)
            current_rating = current_analysis.get("average_matchup_rating", 5.0)
            
            better_alternatives = []
            
            for available_player in available_players:
                # Only compare same position players
                if (available_player.position != current_player.position or 
                    available_player.team == current_player.team):
                    continue
                
                # Analyze available player's matchups
                available_analysis = self.analyze_player_upcoming_matchups(available_player, weeks_ahead)
                available_rating = available_analysis.get("average_matchup_rating", 5.0)
                
                # Check if significantly better matchup
                matchup_improvement = available_rating - current_rating
                
                if matchup_improvement >= 1.0:  # At least 1 point better
                    # Calculate recommendation strength
                    if matchup_improvement >= 2.5:
                        recommendation_strength = "Strong"
                        priority = "High"
                    elif matchup_improvement >= 1.5:
                        recommendation_strength = "Moderate"
                        priority = "Medium"
                    else:
                        recommendation_strength = "Slight"
                        priority = "Low"
                    
                    better_alternatives.append({
                        "player": {
                            "id": available_player.id,
                            "name": available_player.name,
                            "position": available_player.position.value,
                            "team": available_player.team,
                            "projected_points": available_player.projected_points
                        },
                        "matchup_advantage": round(matchup_improvement, 1),
                        "upcoming_rating": round(available_rating, 1),
                        "current_player_rating": round(current_rating, 1),
                        "recommendation_strength": recommendation_strength,
                        "priority": priority,
                        "reasoning": f"Has {matchup_improvement:.1f} point better matchup rating over next {weeks_ahead} weeks",
                        "upcoming_matchups": available_analysis.get("upcoming_matchups", [])
                    })
            
            # Sort by matchup advantage
            better_alternatives.sort(key=lambda x: x["matchup_advantage"], reverse=True)
            
            return better_alternatives[:10]  # Top 10 alternatives
            
        except Exception as e:
            logger.error(f"Error finding better matchup alternatives: {str(e)}")
            return []
    
    def get_weekly_defensive_targets(self, week: Optional[int] = None) -> Dict[str, List[Dict[str, Any]]]:
        """Get this week's best defensive streaming targets"""
        try:
            if not week:
                week = self.get_current_week()
            season = self.get_current_season()

            # Get all defensive matchup rankings for this week
            def_rankings = self.db.query(DefensiveMatchupRanking).filter(
                and_(
                    DefensiveMatchupRanking.week == week,
                    DefensiveMatchupRanking.position == "DEF",
                    DefensiveMatchupRanking.season == season
                )
            ).order_by(DefensiveMatchupRanking.matchup_rating.desc()).all()
            
            streaming_targets = []
            avoid_defenses = []
            
            for ranking in def_rankings:
                # Get opponent for context
                team_games = self.db.query(NFLGame).filter(
                    and_(
                        NFLGame.week == week,
                        NFLGame.season == season,
                        or_(
                            NFLGame.home_team == ranking.team_abbreviation,
                            NFLGame.away_team == ranking.team_abbreviation
                        )
                    )
                ).first()
                
                opponent = None
                is_home = False
                if team_games:
                    opponent = (team_games.away_team if team_games.home_team == ranking.team_abbreviation 
                              else team_games.home_team)
                    is_home = team_games.home_team == ranking.team_abbreviation
                
                defense_data = {
                    "team": ranking.team_abbreviation,
                    "opponent": opponent,
                    "is_home": is_home,
                    "matchup_rating": ranking.matchup_rating,
                    "rank_vs_offense": ranking.rank_vs_position,
                    "avg_points_allowed": ranking.fantasy_points_allowed_avg,
                    "recent_trend": ranking.fantasy_points_allowed_last_4,
                    "confidence": ranking.confidence_score,
                    "key_factors": ranking.key_factors or []
                }
                
                # Categorize defenses
                if ranking.matchup_rating >= 7.5:
                    streaming_targets.append({
                        **defense_data,
                        "tier": "Premium Stream",
                        "recommendation": "Strong start"
                    })
                elif ranking.matchup_rating >= 6.0:
                    streaming_targets.append({
                        **defense_data,
                        "tier": "Good Stream", 
                        "recommendation": "Solid option"
                    })
                elif ranking.matchup_rating <= 3.5:
                    avoid_defenses.append({
                        **defense_data,
                        "tier": "Avoid",
                        "recommendation": "Look for alternatives"
                    })
            
            return {
                "week": week,
                "streaming_targets": streaming_targets[:8],  # Top 8 targets
                "avoid_defenses": avoid_defenses[:5],  # Top 5 to avoid
                "analysis_timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting weekly defensive targets: {str(e)}")
            return {"error": str(e)}
    
    def get_position_matchup_outlook(
        self, 
        position: str, 
        weeks_ahead: int = 4
    ) -> Dict[str, Any]:
        """Get overall matchup outlook for a position across multiple weeks"""
        try:
            current_week = self.get_current_week()
            
            # Get all matchup ratings for this position
            rankings = self.db.query(DefensiveMatchupRanking).filter(
                and_(
                    DefensiveMatchupRanking.position == position,
                    DefensiveMatchupRanking.season == self.get_current_season(),
                    DefensiveMatchupRanking.week.between(current_week, current_week + weeks_ahead)
                )
            ).order_by(
                DefensiveMatchupRanking.week,
                DefensiveMatchupRanking.matchup_rating.desc()
            ).all()
            
            if not rankings:
                return {"error": f"No matchup data available for {position}"}
            
            # Group by week
            weekly_outlook = {}
            for ranking in rankings:
                week = ranking.week
                if week not in weekly_outlook:
                    weekly_outlook[week] = {
                        "best_matchups": [],
                        "worst_matchups": [],
                        "week_average_rating": 0
                    }
                
                matchup_data = {
                    "team": ranking.team_abbreviation,
                    "rating": ranking.matchup_rating,
                    "rank": ranking.rank_vs_position,
                    "points_allowed": ranking.fantasy_points_allowed_avg
                }
                
                # Top 5 best and worst matchups per week
                if ranking.matchup_rating >= 6.5:
                    weekly_outlook[week]["best_matchups"].append(matchup_data)
                elif ranking.matchup_rating <= 4.0:
                    weekly_outlook[week]["worst_matchups"].append(matchup_data)
            
            # Calculate weekly averages
            for week_data in weekly_outlook.values():
                week_rankings = [r for r in rankings if r.week == week]
                if week_rankings:
                    week_data["week_average_rating"] = round(
                        sum(r.matchup_rating for r in week_rankings) / len(week_rankings), 1
                    )
                
                # Limit to top 5 for each category
                week_data["best_matchups"] = week_data["best_matchups"][:5]
                week_data["worst_matchups"] = week_data["worst_matchups"][:5]
            
            return {
                "position": position,
                "weeks_analyzed": weeks_ahead,
                "weekly_outlook": weekly_outlook,
                "total_rankings_analyzed": len(rankings)
            }
            
        except Exception as e:
            logger.error(f"Error getting position matchup outlook: {str(e)}")
            return {"error": str(e)}
    
    def recommend_defensive_streaming(
        self, 
        current_defense: Optional[str] = None,
        week: Optional[int] = None
    ) -> Dict[str, Any]:
        """Recommend defensive streaming options"""
        try:
            if not week:
                week = self.get_current_week()
            
            # Get this week's defensive targets
            weekly_targets = self.get_weekly_defensive_targets(week)
            
            if "error" in weekly_targets:
                return weekly_targets
            
            recommendations = {
                "current_week": week,
                "streaming_recommendations": [],
                "current_defense_analysis": None
            }
            
            # Analyze current defense if provided
            if current_defense:
                current_analysis = self.get_defensive_matchup_rating(current_defense, "DEF", week)
                recommendations["current_defense_analysis"] = current_analysis
                
                # Compare alternatives to current defense
                current_rating = current_analysis.get("matchup_rating", 5.0)
                
                for target in weekly_targets["streaming_targets"]:
                    improvement = target["matchup_rating"] - current_rating
                    
                    if improvement >= 1.0:  # Significant improvement
                        recommendations["streaming_recommendations"].append({
                            **target,
                            "improvement_over_current": round(improvement, 1),
                            "recommendation_type": "Upgrade"
                        })
            else:
                # No current defense - show all good options
                recommendations["streaming_recommendations"] = weekly_targets["streaming_targets"]
            
            # Add avoid list
            recommendations["defenses_to_avoid"] = weekly_targets["avoid_defenses"]
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error recommending defensive streaming: {str(e)}")
            return {"error": str(e)}
    
    def get_player_vs_defense_history(
        self, 
        player: Player, 
        opponent_team: str,
        last_n_games: int = 5
    ) -> Dict[str, Any]:
        """Get player's historical performance vs specific defense"""
        try:
            # Get historical games vs this opponent
            historical_games = self.db.query(PlayerHistoricalPerformance).filter(
                and_(
                    PlayerHistoricalPerformance.player_id == player.id,
                    PlayerHistoricalPerformance.opponent_team == opponent_team,
                    PlayerHistoricalPerformance.season >= 2022  # Last 2+ seasons
                )
            ).order_by(PlayerHistoricalPerformance.season.desc(), 
                      PlayerHistoricalPerformance.week.desc()).limit(last_n_games).all()
            
            if not historical_games:
                return {
                    "player_name": player.name,
                    "opponent": opponent_team,
                    "games_found": 0,
                    "note": "No recent history vs this opponent"
                }
            
            # Calculate performance metrics
            total_points = sum(game.fantasy_points_ppr or 0 for game in historical_games)
            avg_points = total_points / len(historical_games)
            
            # Compare to player's season average
            season_avg = player.projected_points or 0
            performance_vs_opponent = (avg_points / season_avg * 100) if season_avg > 0 else 100
            
            game_details = []
            for game in historical_games:
                game_details.append({
                    "season": game.season,
                    "week": game.week,
                    "fantasy_points": game.fantasy_points_ppr,
                    "location": game.game_location.value if game.game_location else "Unknown"
                })
            
            return {
                "player_name": player.name,
                "opponent": opponent_team,
                "games_analyzed": len(historical_games),
                "avg_points_vs_opponent": round(avg_points, 1),
                "player_season_avg": season_avg,
                "performance_vs_opponent_pct": round(performance_vs_opponent, 1),
                "historical_games": game_details,
                "performance_category": (
                    "Excellent" if performance_vs_opponent >= 120 else
                    "Good" if performance_vs_opponent >= 110 else
                    "Average" if performance_vs_opponent >= 90 else
                    "Below Average" if performance_vs_opponent >= 80 else
                    "Poor"
                )
            }
            
        except Exception as e:
            logger.error(f"Error getting player vs defense history: {str(e)}")
            return {"error": str(e)}
    
    def update_defensive_rankings(self, week: int, defensive_data: List[Dict[str, Any]]):
        """Update defensive rankings for a specific week"""
        try:
            season = self.get_current_season()
            for team_defense in defensive_data:
                team = team_defense["team"]

                # Update rankings for each position
                for position in ["QB", "RB", "WR", "TE", "K", "DEF"]:
                    position_data = team_defense.get(f"{position.lower()}_defense", {})

                    # Check if ranking already exists
                    existing = self.db.query(DefensiveMatchupRanking).filter(
                        and_(
                            DefensiveMatchupRanking.team_abbreviation == team,
                            DefensiveMatchupRanking.position == position,
                            DefensiveMatchupRanking.week == week,
                            DefensiveMatchupRanking.season == season
                        )
                    ).first()

                    if existing:
                        # Update existing ranking
                        existing.rank_vs_position = position_data.get("rank", 16)
                        existing.fantasy_points_allowed_avg = position_data.get("points_allowed", 0)
                        existing.matchup_rating = position_data.get("matchup_rating", 5.0)
                        existing.confidence_score = position_data.get("confidence", 0.5)
                        existing.key_factors = position_data.get("factors", [])
                        existing.updated_at = datetime.utcnow()
                    else:
                        # Create new ranking
                        new_ranking = DefensiveMatchupRanking(
                            season=season,
                            week=week,
                            team_abbreviation=team,
                            position=position,
                            rank_vs_position=position_data.get("rank", 16),
                            fantasy_points_allowed_avg=position_data.get("points_allowed", 0),
                            matchup_rating=position_data.get("matchup_rating", 5.0),
                            confidence_score=position_data.get("confidence", 0.5),
                            key_factors=position_data.get("factors", [])
                        )
                        self.db.add(new_ranking)
            
            self.db.commit()
            logger.info(f"Updated defensive rankings for week {week}")
            
        except Exception as e:
            logger.error(f"Error updating defensive rankings: {str(e)}")
            self.db.rollback()