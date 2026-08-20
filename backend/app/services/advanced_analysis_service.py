from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from app.models.player import Player
from app.models.historical_performance import PlayerHistoricalPerformance
from app.services.advanced_analytics_service import AdvancedAnalyticsService
from datetime import datetime, timedelta
import statistics
import numpy as np
from collections import defaultdict

class AdvancedAnalysisService:
    def __init__(self, db: Session):
        self.db = db
        self.analytics_service = AdvancedAnalyticsService(db)

    async def compare_players(self, player_ids: List[int], metrics: List[str] = None) -> Dict[str, Any]:
        """
        Comprehensive player comparison across multiple metrics
        """
        try:
            if not player_ids or len(player_ids) < 2:
                return {"error": "At least 2 players required for comparison"}

            # Get player data
            players = self.db.query(Player).filter(Player.id.in_(player_ids)).all()
            if len(players) != len(player_ids):
                return {"error": "Some players not found"}

            # Default metrics if none provided
            if not metrics:
                metrics = [
                    'projected_points', 'consistency_rating', 'ceiling_score', 'floor_score',
                    'target_share', 'snap_count_percentage', 'trending_count', 'ownership_percentage'
                ]

            comparison_data = []
            for player in players:
                # Get historical performance
                historical_stats = await self._get_player_historical_stats(player.id)
                
                # Build comprehensive player profile
                player_profile = {
                    'id': player.id,
                    'name': player.name,
                    'position': player.position.value if player.position else 'Unknown',
                    'team': player.team,
                    'current_metrics': self._extract_current_metrics(player, metrics),
                    'historical_performance': historical_stats,
                    'advanced_metrics': await self._calculate_advanced_metrics(player),
                    'trend_analysis': await self._analyze_player_trends(player.id),
                    'risk_assessment': self._assess_player_risk(player, historical_stats)
                }
                comparison_data.append(player_profile)

            # Generate comparison insights
            insights = await self._generate_comparison_insights(comparison_data)
            
            return {
                "success": True,
                "players": comparison_data,
                "insights": insights,
                "head_to_head": await self._generate_head_to_head_analysis(comparison_data),
                "recommendation": await self._generate_comparison_recommendation(comparison_data)
            }

        except Exception as e:
            return {"error": f"Player comparison failed: {str(e)}"}

    async def analyze_strength_of_schedule(self, player_ids: List[int], weeks_ahead: int = 4) -> Dict[str, Any]:
        """
        Analyze upcoming matchup difficulty for players
        """
        try:
            players = self.db.query(Player).filter(Player.id.in_(player_ids)).all()
            
            schedule_analysis = []
            for player in players:
                # Get team's upcoming opponents (simplified - would integrate with real NFL schedule)
                upcoming_matchups = await self._get_upcoming_matchups(player.team, weeks_ahead)
                
                # Analyze matchup difficulty
                matchup_analysis = []
                total_difficulty = 0
                
                for week, opponent in upcoming_matchups:
                    difficulty = await self._calculate_matchup_difficulty(
                        player.position.value if player.position else 'FLEX',
                        opponent,
                        player.team
                    )
                    
                    matchup_analysis.append({
                        'week': week,
                        'opponent': opponent,
                        'difficulty_score': difficulty['score'],
                        'difficulty_rating': difficulty['rating'],
                        'key_factors': difficulty['factors'],
                        'projected_impact': difficulty['impact']
                    })
                    total_difficulty += difficulty['score']
                
                avg_difficulty = total_difficulty / len(upcoming_matchups) if upcoming_matchups else 5.0
                
                schedule_analysis.append({
                    'player': {
                        'id': player.id,
                        'name': player.name,
                        'position': player.position.value if player.position else 'Unknown',
                        'team': player.team
                    },
                    'schedule_difficulty': {
                        'average_score': round(avg_difficulty, 2),
                        'rating': self._get_difficulty_rating(avg_difficulty),
                        'rank': 0  # Will be calculated after all players
                    },
                    'upcoming_matchups': matchup_analysis,
                    'recommendation': self._get_schedule_recommendation(avg_difficulty, matchup_analysis)
                })
            
            # Rank players by schedule difficulty
            schedule_analysis.sort(key=lambda x: x['schedule_difficulty']['average_score'])
            for i, analysis in enumerate(schedule_analysis):
                analysis['schedule_difficulty']['rank'] = i + 1
            
            return {
                "success": True,
                "schedule_analysis": schedule_analysis,
                "summary": {
                    "easiest_schedule": schedule_analysis[0]['player']['name'] if schedule_analysis else None,
                    "hardest_schedule": schedule_analysis[-1]['player']['name'] if schedule_analysis else None,
                    "average_difficulty": round(sum(p['schedule_difficulty']['average_score'] for p in schedule_analysis) / len(schedule_analysis), 2) if schedule_analysis else 0
                }
            }

        except Exception as e:
            return {"error": f"Strength of schedule analysis failed: {str(e)}"}

    async def detect_breakout_candidates(self, position: str = None, min_ownership: float = 0.0, max_ownership: float = 50.0) -> Dict[str, Any]:
        """
        Use ML and historical data to identify potential breakout candidates
        """
        try:
            # Build query for potential breakout candidates
            query = self.db.query(Player)
            
            if position and position != 'ALL':
                query = query.filter(Player.position == position)
            
            # Filter by ownership percentage (breakout candidates typically have low ownership)
            query = query.filter(
                and_(
                    or_(Player.ownership_percentage.is_(None), Player.ownership_percentage >= min_ownership),
                    or_(Player.ownership_percentage.is_(None), Player.ownership_percentage <= max_ownership)
                )
            )
            
            candidates = query.all()
            
            breakout_analysis = []
            for player in candidates:
                # Calculate breakout probability using multiple factors
                breakout_score = await self._calculate_breakout_probability(player)
                
                if breakout_score['probability'] > 0.3:  # Only include players with >30% breakout chance
                    historical_stats = await self._get_player_historical_stats(player.id)
                    
                    candidate_profile = {
                        'player': {
                            'id': player.id,
                            'name': player.name,
                            'position': player.position.value if player.position else 'Unknown',
                            'team': player.team,
                            'age': player.age,
                            'ownership_percentage': player.ownership_percentage or 0.0
                        },
                        'breakout_analysis': breakout_score,
                        'supporting_factors': await self._identify_breakout_factors(player, historical_stats),
                        'risk_factors': await self._identify_breakout_risks(player, historical_stats),
                        'recommendation': self._generate_breakout_recommendation(breakout_score)
                    }
                    breakout_analysis.append(candidate_profile)
            
            # Sort by breakout probability
            breakout_analysis.sort(key=lambda x: x['breakout_analysis']['probability'], reverse=True)
            
            return {
                "success": True,
                "breakout_candidates": breakout_analysis[:20],  # Top 20 candidates
                "summary": {
                    "total_candidates": len(breakout_analysis),
                    "high_probability": len([c for c in breakout_analysis if c['breakout_analysis']['probability'] > 0.7]),
                    "medium_probability": len([c for c in breakout_analysis if 0.5 < c['breakout_analysis']['probability'] <= 0.7]),
                    "average_probability": round(sum(c['breakout_analysis']['probability'] for c in breakout_analysis) / len(breakout_analysis), 3) if breakout_analysis else 0
                }
            }

        except Exception as e:
            return {"error": f"Breakout candidate detection failed: {str(e)}"}

    async def analyze_game_situations(self, player_ids: List[int]) -> Dict[str, Any]:
        """
        Analyze how players perform in different game situations
        """
        try:
            players = self.db.query(Player).filter(Player.id.in_(player_ids)).all()
            
            situation_analysis = []
            for player in players:
                # Get historical performance by situation
                historical_data = await self._get_player_historical_stats(player.id)
                
                # Analyze different game situations
                situations = {
                    'home_vs_away': await self._analyze_home_away_splits(player.id, historical_data),
                    'weather_impact': await self._analyze_weather_impact(player.id, historical_data),
                    'opponent_strength': await self._analyze_vs_opponent_strength(player.id, historical_data),
                    'game_script': await self._analyze_game_script_impact(player.id, historical_data),
                    'injury_context': await self._analyze_injury_impact(player.id, historical_data)
                }
                
                # Generate overall situational profile
                situational_profile = {
                    'player': {
                        'id': player.id,
                        'name': player.name,
                        'position': player.position.value if player.position else 'Unknown',
                        'team': player.team
                    },
                    'situation_analysis': situations,
                    'key_insights': await self._generate_situational_insights(situations),
                    'upcoming_context': await self._analyze_upcoming_situations(player)
                }
                
                situation_analysis.append(situational_profile)
            
            return {
                "success": True,
                "situation_analysis": situation_analysis,
                "cross_player_insights": await self._generate_cross_player_situational_insights(situation_analysis)
            }

        except Exception as e:
            return {"error": f"Game situation analysis failed: {str(e)}"}

    # Helper methods
    async def _get_player_historical_stats(self, player_id: int) -> Dict[str, Any]:
        """Get comprehensive historical statistics for a player"""
        historical_records = self.db.query(PlayerHistoricalPerformance).filter(
            PlayerHistoricalPerformance.player_id == player_id
        ).order_by(PlayerHistoricalPerformance.week.desc()).limit(10).all()
        
        if not historical_records:
            return {"games": 0, "avg_points": 0, "consistency": 0}
        
        points = [record.fantasy_points for record in historical_records if record.fantasy_points]
        
        return {
            "games": len(historical_records),
            "avg_points": round(statistics.mean(points), 2) if points else 0,
            "std_dev": round(statistics.stdev(points), 2) if len(points) > 1 else 0,
            "consistency": round((1 - (statistics.stdev(points) / statistics.mean(points))) * 10, 2) if points and statistics.mean(points) > 0 else 0,
            "recent_trend": self._calculate_trend(points[-5:] if len(points) >= 5 else points),
            "ceiling": max(points) if points else 0,
            "floor": min(points) if points else 0
        }

    def _extract_current_metrics(self, player: Player, metrics: List[str]) -> Dict[str, Any]:
        """Extract current season metrics for comparison"""
        current_metrics = {}
        for metric in metrics:
            value = getattr(player, metric, None)
            if hasattr(value, 'value'):  # Handle enum values
                current_metrics[metric] = value.value
            else:
                current_metrics[metric] = value
        return current_metrics

    async def _calculate_advanced_metrics(self, player: Player) -> Dict[str, Any]:
        """Calculate advanced metrics for player analysis"""
        return {
            "value_score": self._calculate_value_score(player),
            "upside_rating": self._calculate_upside_rating(player),
            "consistency_index": self._calculate_consistency_index(player),
            "opportunity_share": self._calculate_opportunity_share(player),
            "efficiency_rating": self._calculate_efficiency_rating(player)
        }

    def _calculate_value_score(self, player: Player) -> float:
        """Calculate overall value score (0-100)"""
        factors = []
        
        if player.projected_points:
            factors.append(min(player.projected_points * 5, 100))
        if player.consistency_rating:
            factors.append(player.consistency_rating * 10)
        if player.ownership_percentage is not None:
            factors.append(max(0, (100 - player.ownership_percentage)))
        
        return round(sum(factors) / len(factors), 2) if factors else 50.0

    def _calculate_upside_rating(self, player: Player) -> float:
        """Calculate upside potential (0-10)"""
        upside = 5.0  # Base rating
        
        if player.ceiling_score:
            upside += min(player.ceiling_score / 5, 3)
        if player.age and player.age < 26:
            upside += 1
        if player.trending_count and player.trending_count > 1000:
            upside += 1
        
        return min(upside, 10.0)

    def _calculate_consistency_index(self, player: Player) -> float:
        """Calculate consistency index (0-10)"""
        if player.consistency_rating:
            return player.consistency_rating
        if player.floor_score and player.ceiling_score:
            variance = player.ceiling_score - player.floor_score
            return max(0, 10 - (variance / 2))
        return 5.0

    def _calculate_opportunity_share(self, player: Player) -> float:
        """Calculate opportunity share rating"""
        opportunity = 0.0
        
        if player.target_share:
            opportunity += player.target_share * 0.4
        if player.snap_count_percentage:
            opportunity += player.snap_count_percentage * 0.6
        
        return min(opportunity, 100.0)

    def _calculate_efficiency_rating(self, player: Player) -> float:
        """Calculate efficiency rating"""
        if player.projected_points and player.target_share:
            return round((player.projected_points / max(player.target_share, 1)) * 10, 2)
        return 5.0

    async def _analyze_player_trends(self, player_id: int) -> Dict[str, Any]:
        """Analyze recent performance trends"""
        recent_performances = self.db.query(PlayerHistoricalPerformance).filter(
            PlayerHistoricalPerformance.player_id == player_id
        ).order_by(PlayerHistoricalPerformance.week.desc()).limit(5).all()
        
        if len(recent_performances) < 3:
            return {"trend": "insufficient_data", "direction": "stable", "confidence": 0}
        
        points = [p.fantasy_points for p in reversed(recent_performances) if p.fantasy_points]
        
        if len(points) < 3:
            return {"trend": "insufficient_data", "direction": "stable", "confidence": 0}
        
        # Calculate trend
        trend = self._calculate_trend(points)
        
        return {
            "trend": trend,
            "direction": "improving" if trend > 0.5 else "declining" if trend < -0.5 else "stable",
            "confidence": min(abs(trend) * 100, 100),
            "recent_average": round(statistics.mean(points), 2),
            "games_analyzed": len(points)
        }

    def _calculate_trend(self, values: List[float]) -> float:
        """Calculate trend direction (-1 to 1)"""
        if len(values) < 2:
            return 0.0
        
        # Simple linear trend calculation
        n = len(values)
        x = list(range(n))
        
        try:
            correlation = np.corrcoef(x, values)[0, 1]
            return correlation if not np.isnan(correlation) else 0.0
        except:
            return 0.0

    def _assess_player_risk(self, player: Player, historical_stats: Dict[str, Any]) -> Dict[str, Any]:
        """Assess various risk factors for a player"""
        risk_factors = []
        risk_score = 0.0
        
        # Injury risk
        if player.injury_status and player.injury_status.value != 'HEALTHY':
            risk_factors.append("Current injury concern")
            risk_score += 0.3
        
        # Age risk
        if player.age and player.age > 30:
            risk_factors.append("Age-related decline risk")
            risk_score += 0.2
        
        # Consistency risk
        if historical_stats.get('consistency', 0) < 5:
            risk_factors.append("High performance variance")
            risk_score += 0.2
        
        # Opportunity risk
        if player.snap_count_percentage and player.snap_count_percentage < 60:
            risk_factors.append("Limited snap count")
            risk_score += 0.15
        
        # Team risk
        if player.depth_chart_order and player.depth_chart_order > 2:
            risk_factors.append("Lower depth chart position")
            risk_score += 0.15
        
        risk_level = "LOW" if risk_score < 0.3 else "MEDIUM" if risk_score < 0.6 else "HIGH"
        
        return {
            "risk_score": min(risk_score, 1.0),
            "risk_level": risk_level,
            "risk_factors": risk_factors,
            "confidence": round((1 - risk_score) * 100, 1)
        }

    async def _generate_comparison_insights(self, comparison_data: List[Dict]) -> List[str]:
        """Generate insights from player comparison"""
        insights = []
        
        if len(comparison_data) >= 2:
            # Compare projected points
            sorted_by_points = sorted(comparison_data, key=lambda x: x['current_metrics'].get('projected_points', 0) or 0, reverse=True)
            highest = sorted_by_points[0]
            insights.append(f"{highest['name']} has the highest projected points at {highest['current_metrics'].get('projected_points', 0)}")
            
            # Compare consistency
            sorted_by_consistency = sorted(comparison_data, key=lambda x: x['current_metrics'].get('consistency_rating', 0) or 0, reverse=True)
            most_consistent = sorted_by_consistency[0]
            insights.append(f"{most_consistent['name']} offers the most consistent performance")
            
            # Risk assessment
            risk_levels = [p['risk_assessment']['risk_level'] for p in comparison_data]
            if 'LOW' in risk_levels:
                low_risk = [p for p in comparison_data if p['risk_assessment']['risk_level'] == 'LOW'][0]
                insights.append(f"{low_risk['name']} presents the lowest risk profile")
        
        return insights

    async def _generate_head_to_head_analysis(self, comparison_data: List[Dict]) -> Dict[str, Any]:
        """Generate head-to-head comparison matrix"""
        if len(comparison_data) != 2:
            return {}
        
        player1, player2 = comparison_data[0], comparison_data[1]
        
        categories = {
            "Projected Points": (player1['current_metrics'].get('projected_points', 0), player2['current_metrics'].get('projected_points', 0)),
            "Consistency": (player1['current_metrics'].get('consistency_rating', 0), player2['current_metrics'].get('consistency_rating', 0)),
            "Upside": (player1['advanced_metrics']['upside_rating'], player2['advanced_metrics']['upside_rating']),
            "Opportunity": (player1['advanced_metrics']['opportunity_share'], player2['advanced_metrics']['opportunity_share']),
            "Risk Level": (player1['risk_assessment']['risk_score'], player2['risk_assessment']['risk_score'])
        }
        
        winner_count = {player1['name']: 0, player2['name']: 0}
        
        head_to_head = {}
        for category, (val1, val2) in categories.items():
            if category == "Risk Level":
                winner = player1['name'] if val1 < val2 else player2['name']  # Lower risk is better
            else:
                winner = player1['name'] if val1 > val2 else player2['name']  # Higher is better
            
            winner_count[winner] += 1
            head_to_head[category] = {
                "winner": winner,
                "values": {player1['name']: val1, player2['name']: val2}
            }
        
        overall_winner = max(winner_count.items(), key=lambda x: x[1])[0]
        
        return {
            "categories": head_to_head,
            "overall_winner": overall_winner,
            "score": f"{winner_count[overall_winner]}-{5 - winner_count[overall_winner]}"
        }

    async def _generate_comparison_recommendation(self, comparison_data: List[Dict]) -> str:
        """Generate overall recommendation from comparison"""
        if not comparison_data:
            return "No players to compare"
        
        # Score each player across multiple factors
        player_scores = []
        for player in comparison_data:
            score = 0
            score += (player['current_metrics'].get('projected_points', 0) or 0) * 2
            score += (player['current_metrics'].get('consistency_rating', 0) or 0) * 3
            score += player['advanced_metrics']['upside_rating'] * 1.5
            score -= player['risk_assessment']['risk_score'] * 10
            
            player_scores.append((player['name'], score))
        
        best_player = max(player_scores, key=lambda x: x[1])
        
        return f"Based on comprehensive analysis, {best_player[0]} appears to be the strongest option with a score of {best_player[1]:.1f}"

    # Placeholder methods for future implementation
    async def _get_upcoming_matchups(self, team: str, weeks: int) -> List[Tuple[int, str]]:
        """Get upcoming matchups for a team (placeholder)"""
        # This would integrate with real NFL schedule data
        mock_opponents = ['DAL', 'NYG', 'WAS', 'PHI', 'SF', 'LAR', 'SEA', 'ARI']
        return [(i + 1, f"vs {mock_opponents[i % len(mock_opponents)]}") for i in range(weeks)]

    async def _calculate_matchup_difficulty(self, position: str, opponent: str, team: str) -> Dict[str, Any]:
        """Calculate matchup difficulty (placeholder)"""
        # Mock difficulty calculation
        import random
        difficulty_score = random.uniform(3.0, 8.0)
        
        return {
            "score": round(difficulty_score, 2),
            "rating": self._get_difficulty_rating(difficulty_score),
            "factors": ["Opponent defense ranking", "Historical performance vs position"],
            "impact": "Moderate impact on production expected"
        }

    def _get_difficulty_rating(self, score: float) -> str:
        """Convert difficulty score to rating"""
        if score < 4:
            return "EASY"
        elif score < 6:
            return "MODERATE"
        else:
            return "DIFFICULT"

    def _get_schedule_recommendation(self, avg_difficulty: float, matchups: List[Dict]) -> str:
        """Generate schedule-based recommendation"""
        if avg_difficulty < 4:
            return "Favorable schedule - consider targeting this player"
        elif avg_difficulty > 6:
            return "Challenging schedule - may want to avoid or trade"
        else:
            return "Average schedule difficulty - standard expectations"

    async def _calculate_breakout_probability(self, player: Player) -> Dict[str, Any]:
        """Calculate breakout probability using various factors"""
        probability = 0.5  # Base probability
        factors = []
        
        # Age factor (younger players more likely to break out)
        if player.age and player.age < 25:
            probability += 0.2
            factors.append("Young age (high upside)")
        elif player.age and player.age < 27:
            probability += 0.1
            factors.append("Prime age range")
        
        # Opportunity factors
        if player.snap_count_percentage and player.snap_count_percentage > 70:
            probability += 0.15
            factors.append("High snap count share")
        
        if player.target_share and player.target_share > 15:
            probability += 0.1
            factors.append("Good target share")
        
        # Trending factors
        if player.trending_direction and player.trending_direction == "UP":
            probability += 0.1
            factors.append("Positive trending direction")
        
        # Efficiency factors
        if player.projected_points and player.ownership_percentage:
            efficiency = player.projected_points / max(player.ownership_percentage, 1)
            if efficiency > 0.5:
                probability += 0.15
                factors.append("High efficiency relative to ownership")
        
        # Team context
        if player.depth_chart_order and player.depth_chart_order <= 2:
            probability += 0.1
            factors.append("Good depth chart position")
        
        return {
            "probability": min(probability, 1.0),
            "confidence": "HIGH" if probability > 0.7 else "MEDIUM" if probability > 0.5 else "LOW",
            "key_factors": factors
        }

    async def _identify_breakout_factors(self, player: Player, historical_stats: Dict) -> List[str]:
        """Identify supporting factors for breakout potential"""
        factors = []
        
        if historical_stats.get('recent_trend', 0) > 0.5:
            factors.append("Recent upward performance trend")
        
        if player.target_share and player.target_share > 20:
            factors.append("High target share indicates opportunity")
        
        if player.age and player.age < 26:
            factors.append("Young player with room for development")
        
        return factors

    async def _identify_breakout_risks(self, player: Player, historical_stats: Dict) -> List[str]:
        """Identify risk factors that could prevent breakout"""
        risks = []
        
        if player.injury_status and player.injury_status.value != 'HEALTHY':
            risks.append("Current injury concerns")
        
        if historical_stats.get('consistency', 0) < 5:
            risks.append("Inconsistent past performance")
        
        if player.depth_chart_order and player.depth_chart_order > 2:
            risks.append("Competition for playing time")
        
        return risks

    def _generate_breakout_recommendation(self, breakout_score: Dict) -> str:
        """Generate recommendation based on breakout analysis"""
        probability = breakout_score['probability']
        
        if probability > 0.7:
            return "STRONG BUY - High breakout potential with multiple supporting factors"
        elif probability > 0.5:
            return "BUY - Good breakout candidate worth targeting"
        elif probability > 0.3:
            return "WATCH - Some upside potential, monitor closely"
        else:
            return "PASS - Low breakout probability"

    # Placeholder methods for situational analysis
    async def _analyze_home_away_splits(self, player_id: int, historical_data: Dict) -> Dict[str, Any]:
        """Analyze home vs away performance"""
        return {
            "home_average": 12.5,
            "away_average": 10.8,
            "preference": "HOME",
            "sample_size": {"home": 5, "away": 5}
        }

    async def _analyze_weather_impact(self, player_id: int, historical_data: Dict) -> Dict[str, Any]:
        """Analyze weather impact on performance"""
        return {
            "outdoor_performance": 11.2,
            "dome_performance": 13.1,
            "weather_sensitivity": "LOW",
            "key_factors": ["Position less affected by weather"]
        }

    async def _analyze_vs_opponent_strength(self, player_id: int, historical_data: Dict) -> Dict[str, Any]:
        """Analyze performance vs strong/weak opponents"""
        return {
            "vs_strong_defense": 9.8,
            "vs_weak_defense": 14.2,
            "matchup_dependency": "MODERATE",
            "optimal_targets": ["Weak pass defense", "High pace opponents"]
        }

    async def _analyze_game_script_impact(self, player_id: int, historical_data: Dict) -> Dict[str, Any]:
        """Analyze performance in different game scripts"""
        return {
            "leading_games": 10.5,
            "trailing_games": 13.8,
            "close_games": 12.1,
            "script_preference": "TRAILING",
            "garbage_time_boost": True
        }

    async def _analyze_injury_impact(self, player_id: int, historical_data: Dict) -> Dict[str, Any]:
        """Analyze impact of injuries on performance"""
        return {
            "games_missed": 2,
            "return_performance": 85.2,
            "injury_risk": "MODERATE",
            "recovery_pattern": "Good return to form after injuries"
        }

    async def _generate_situational_insights(self, situations: Dict) -> List[str]:
        """Generate insights from situational analysis"""
        insights = []
        
        home_away = situations['home_vs_away']
        if home_away['preference'] == 'HOME':
            insights.append(f"Performs better at home ({home_away['home_average']} vs {home_away['away_average']} away)")
        
        game_script = situations['game_script']
        if game_script['script_preference'] == 'TRAILING':
            insights.append("Benefits from negative game script and garbage time")
        
        return insights

    async def _analyze_upcoming_situations(self, player: Player) -> Dict[str, Any]:
        """Analyze upcoming game situations for the player"""
        return {
            "next_game": {
                "location": "HOME",
                "opponent_strength": "WEAK",
                "weather": "DOME",
                "projected_script": "FAVORABLE"
            },
            "outlook": "Positive situational factors for upcoming games"
        }

    async def _generate_cross_player_situational_insights(self, situation_analysis: List[Dict]) -> List[str]:
        """Generate insights comparing situational factors across players"""
        insights = []
        
        if len(situation_analysis) > 1:
            insights.append("Player situational factors analyzed and compared")
            insights.append("Consider upcoming game locations and matchups when making decisions")
        
        return insights