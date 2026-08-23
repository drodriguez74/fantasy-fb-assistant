from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from app.models.player import Player, InjuryStatus
from app.models.historical_performance import PlayerHistoricalPerformance, GameLocation
from app.models.nfl_schedule import NFLGame
from app.services.advanced_analytics_service import AdvancedAnalyticsService
from app.services.matchup_analysis_service import MatchupAnalysisService
from datetime import datetime, timedelta
import statistics
import numpy as np
from scipy import stats as scipy_stats
from collections import defaultdict

class AdvancedAnalysisService:
    # Minimum games required on each side of a split (home/away, dome/outdoor,
    # etc.) before we'll report it as a real number rather than "insufficient".
    MIN_SPLIT_SAMPLE = 2

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

            # Real statistical significance testing (ANOVA/Mann-Whitney/Cohen's d),
            # merged in from advanced_historical_service.py -- see
            # _perform_statistical_tests for details.
            points_by_player = [
                {"id": p["id"], "name": p["name"], "points": self._get_player_points_series(p["id"])}
                for p in comparison_data
            ]
            statistical_analysis = await self._perform_statistical_tests(points_by_player)

            return {
                "success": True,
                "players": comparison_data,
                "insights": insights,
                "head_to_head": await self._generate_head_to_head_analysis(comparison_data),
                "statistical_analysis": statistical_analysis,
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
                # Real NFL schedule lookup (see _get_upcoming_matchups) -- empty
                # when this team has no synced schedule rows for the upcoming weeks.
                upcoming_matchups = await self._get_upcoming_matchups(player.team, weeks_ahead)

                # Analyze matchup difficulty
                matchup_analysis = []
                scored_difficulties = []

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
                        'projected_impact': difficulty['impact'],
                        'historical_points_allowed': difficulty['historical_check']
                    })
                    if difficulty['score'] is not None:
                        scored_difficulties.append(difficulty['score'])

                # CATEGORY: Insufficient data -- honestly flagged rather than
                # silently defaulting to a neutral-looking 5.0 (the old
                # behavior), which would have looked like a real "average"
                # matchup rather than "we don't know yet."
                if not upcoming_matchups:
                    schedule_analysis.append({
                        'player': {
                            'id': player.id,
                            'name': player.name,
                            'position': player.position.value if player.position else 'Unknown',
                            'team': player.team
                        },
                        'schedule_difficulty': {
                            'average_score': None,
                            'rating': 'INSUFFICIENT_DATA',
                            'rank': None,
                            'data_confidence': 'insufficient'
                        },
                        'upcoming_matchups': [],
                        'recommendation': 'No synced schedule data for the upcoming weeks -- unable to project strength of schedule.'
                    })
                    continue

                avg_difficulty = round(sum(scored_difficulties) / len(scored_difficulties), 2) if scored_difficulties else None
                data_confidence = 'computed' if scored_difficulties else 'insufficient'

                schedule_analysis.append({
                    'player': {
                        'id': player.id,
                        'name': player.name,
                        'position': player.position.value if player.position else 'Unknown',
                        'team': player.team
                    },
                    'schedule_difficulty': {
                        'average_score': avg_difficulty,
                        'rating': self._get_difficulty_rating(avg_difficulty) if avg_difficulty is not None else 'INSUFFICIENT_DATA',
                        'rank': 0,  # Will be calculated after all players
                        'data_confidence': data_confidence
                    },
                    'upcoming_matchups': matchup_analysis,
                    'recommendation': self._get_schedule_recommendation(avg_difficulty, matchup_analysis) if avg_difficulty is not None else 'Defensive ranking data not yet available for these opponents -- unable to project schedule impact.'
                })

            # Rank players by schedule difficulty (players with no score yet sort last)
            schedule_analysis.sort(
                key=lambda x: (x['schedule_difficulty']['average_score'] is None, x['schedule_difficulty']['average_score'])
            )
            for i, analysis in enumerate(schedule_analysis):
                if analysis['schedule_difficulty']['average_score'] is not None:
                    analysis['schedule_difficulty']['rank'] = i + 1
            
            # Only players with a real computed score can be meaningfully
            # called "easiest"/"hardest" -- an insufficient-data player
            # sorts last (see key above) but isn't a genuine data point.
            scored_players = [p for p in schedule_analysis if p['schedule_difficulty']['average_score'] is not None]

            return {
                "success": True,
                "schedule_analysis": schedule_analysis,
                "summary": {
                    "easiest_schedule": scored_players[0]['player']['name'] if scored_players else None,
                    "hardest_schedule": scored_players[-1]['player']['name'] if scored_players else None,
                    "average_difficulty": round(sum(p['schedule_difficulty']['average_score'] for p in scored_players) / len(scored_players), 2) if scored_players else None,
                    "players_with_data": len(scored_players),
                    "players_without_data": len(schedule_analysis) - len(scored_players)
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
                # Calculate breakout probability using multiple factors, including
                # a real historical performance trend (see _calculate_breakout_probability)
                points_series = self._get_player_points_series(player.id)
                breakout_score = await self._calculate_breakout_probability(player, points_series)
                
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
        
        points = [record.fantasy_points_ppr for record in historical_records if record.fantasy_points_ppr]
        
        return {
            "games": len(historical_records),
            "avg_points": round(statistics.mean(points), 2) if points else 0,
            "std_dev": round(statistics.stdev(points), 2) if len(points) > 1 else 0,
            "consistency": round((1 - (statistics.stdev(points) / statistics.mean(points))) * 10, 2) if points and statistics.mean(points) > 0 else 0,
            "recent_trend": self._calculate_trend(points[-5:] if len(points) >= 5 else points),
            "ceiling": max(points) if points else 0,
            "floor": min(points) if points else 0
        }

    def _get_player_points_series(self, player_id: int) -> List[float]:
        """Real, chronologically-ordered fantasy_points_ppr history for a player
        (all logged PlayerHistoricalPerformance rows with a non-null value) --
        the raw series statistical tests below are run against."""
        records = self.db.query(PlayerHistoricalPerformance).filter(
            PlayerHistoricalPerformance.player_id == player_id,
            PlayerHistoricalPerformance.fantasy_points_ppr.isnot(None)
        ).order_by(PlayerHistoricalPerformance.season, PlayerHistoricalPerformance.week).all()
        return [r.fantasy_points_ppr for r in records]

    # --- CATEGORY: Computed (merged from advanced_historical_service.py) ---
    # advanced_historical_service.py's compare_players_advanced() ran real ANOVA
    # (scipy.stats.f_oneway), pairwise Mann-Whitney U tests, and Cohen's d effect
    # sizes across players' historical fantasy_points_ppr series -- statistics
    # this (the wired) service's compare_players() didn't have. Per the product
    # decision to consolidate on this service as the canonical compare-players
    # path, that real statistical-significance testing is merged in here rather
    # than duplicated in the now-decommissioned advanced_historical_service.py.
    async def _perform_statistical_tests(self, players: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        players: [{"id", "name", "points": List[float]}, ...]. Players with
        fewer than 2 logged games are excluded from the tests (a significance
        test on a single data point isn't meaningful) and reported separately
        rather than silently dropped.
        """
        insufficient = [p["name"] for p in players if len(p["points"]) < 2]
        eligible = [p for p in players if len(p["points"]) >= 2]

        if len(eligible) < 2:
            return {
                "anova_test": None,
                "pairwise_tests": [],
                "data_confidence": "insufficient",
                "insufficient_data_players": insufficient,
                "note": "Need at least 2 players with 2+ logged historical games to run significance tests."
            }

        groups = [p["points"] for p in eligible]
        f_stat, anova_p = scipy_stats.f_oneway(*groups)
        anova_result = {
            "f_statistic": round(float(f_stat), 4) if not np.isnan(f_stat) else None,
            "p_value": round(float(anova_p), 4) if not np.isnan(anova_p) else None,
            "significant": bool(anova_p < 0.05) if not np.isnan(anova_p) else None,
            "interpretation": (
                "Statistically significant difference between players' historical scoring"
                if not np.isnan(anova_p) and anova_p < 0.05
                else "No statistically significant difference detected between players' historical scoring"
            )
        }

        pairwise_tests = []
        for i in range(len(eligible)):
            for j in range(i + 1, len(eligible)):
                p1, p2 = eligible[i], eligible[j]
                mw_stat, mw_p = scipy_stats.mannwhitneyu(p1["points"], p2["points"], alternative='two-sided')

                mean1, mean2 = statistics.mean(p1["points"]), statistics.mean(p2["points"])
                std1 = statistics.stdev(p1["points"]) if len(p1["points"]) > 1 else 0.0
                std2 = statistics.stdev(p2["points"]) if len(p2["points"]) > 1 else 0.0
                pooled_std = ((std1 ** 2 + std2 ** 2) / 2) ** 0.5
                cohens_d = (mean1 - mean2) / pooled_std if pooled_std > 0 else 0.0

                pairwise_tests.append({
                    "player1": p1["name"],
                    "player2": p2["name"],
                    "mann_whitney_u": round(float(mw_stat), 3),
                    "p_value": round(float(mw_p), 4),
                    "significant": bool(mw_p < 0.05),
                    "cohens_d": round(float(cohens_d), 3),
                    "effect_size": self._interpret_effect_size(abs(cohens_d)),
                    "mean_difference": round(mean1 - mean2, 2)
                })

        return {
            "anova_test": anova_result,
            "pairwise_tests": pairwise_tests,
            "data_confidence": "computed",
            "insufficient_data_players": insufficient
        }

    def _interpret_effect_size(self, cohens_d: float) -> str:
        """Interpret Cohen's d effect size (standard Cohen 1988 thresholds)."""
        if cohens_d < 0.2:
            return "negligible"
        elif cohens_d < 0.5:
            return "small"
        elif cohens_d < 0.8:
            return "medium"
        else:
            return "large"

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
        
        points = [p.fantasy_points_ppr for p in reversed(recent_performances) if p.fantasy_points_ppr]
        
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

    # --- CATEGORY: Computed (real implementation) ---
    # These two methods used to be static/random placeholders (mock opponent
    # cycling through a fixed 8-team list, and `random.uniform(3.0, 8.0)` for
    # "difficulty" -- meaning the score changed on every call even for the
    # *same* player, and was never actually derived from that player's real
    # team or opponent). They now source real schedule and defensive-ranking
    # data from the NFLGame / DefensiveMatchupRanking tables via
    # MatchupAnalysisService -- the same real infrastructure the Matchup
    # Analysis and Waiver Wire features already use elsewhere in this app.
    # If this deployment's schedule/defensive-ranking tables haven't been
    # synced yet, these honestly return empty/low-confidence results instead
    # of a plausible-looking fake number -- see the "insufficient" branches
    # below and in analyze_strength_of_schedule().
    async def _get_upcoming_matchups(self, team: str, weeks: int) -> List[Tuple[int, str]]:
        """Get a team's real upcoming opponents from the NFL schedule (Computed)."""
        matchup_service = MatchupAnalysisService(self.db)
        current_week = matchup_service.get_current_week()

        games = self.db.query(NFLGame).filter(
            and_(
                NFLGame.season == 2024,
                NFLGame.week.between(current_week, current_week + max(weeks, 1) - 1),
                or_(NFLGame.home_team == team, NFLGame.away_team == team)
            )
        ).order_by(NFLGame.week).all()

        return [
            (game.week, game.away_team if game.home_team == team else game.home_team)
            for game in games
        ]

    async def _calculate_matchup_difficulty(self, position: str, opponent: str, team: str) -> Dict[str, Any]:
        """
        Calculate matchup difficulty from real defensive rankings (Computed),
        falling back to an explicit "insufficient" state (not a fabricated
        score) when no ranking has been synced yet for this opponent/position.
        """
        matchup_service = MatchupAnalysisService(self.db)
        rating = matchup_service.get_defensive_matchup_rating(opponent, position)
        historical_check = self._get_historical_matchup_difficulty(opponent, position)

        if "error" in rating or rating.get("confidence") == "Low":
            return {
                "score": None,
                "rating": "INSUFFICIENT_DATA",
                "factors": [rating.get("note", "No defensive ranking data available for this opponent/position yet")],
                "impact": "Insufficient data to project matchup impact",
                "data_confidence": "insufficient",
                "historical_check": historical_check
            }

        # matchup_rating is on a 1-10 scale where 10 = best matchup for the
        # offense; difficulty is the inverse of that.
        difficulty_score = 10 - rating["matchup_rating"]

        return {
            "score": round(difficulty_score, 2),
            "rating": self._get_difficulty_rating(difficulty_score),
            "factors": [
                f"{opponent} ranked #{rating.get('rank_vs_position', '?')} vs {position}",
                f"Fantasy points allowed (season avg): {rating.get('fantasy_points_allowed_avg')}"
            ],
            "impact": f"Recent trend: {rating['recent_trend']} pts/game allowed (last 4)" if rating.get("recent_trend") is not None else "Recent trend data unavailable",
            "data_confidence": "computed",
            "historical_check": historical_check
        }

    # --- CATEGORY: Computed (merged from advanced_historical_service.py) ---
    # advanced_historical_service.py's analyze_strength_of_schedule() computed a
    # real, empirical "points allowed to this position" figure straight from
    # PlayerHistoricalPerformance game logs (every player who has actually faced
    # this opponent), rather than the forward-looking DefensiveMatchupRanking
    # table the method above uses. Both are real -- one is a live/projected
    # ranking, the other is this app's own historical record -- so this is
    # merged in as a second, empirically-grounded cross-check on each matchup
    # rather than replacing the already-Computed ranking above.
    def _get_historical_matchup_difficulty(self, opponent: str, position: str) -> Dict[str, Any]:
        rows = self.db.query(PlayerHistoricalPerformance).join(
            Player, PlayerHistoricalPerformance.player_id == Player.id
        ).filter(
            and_(
                PlayerHistoricalPerformance.opponent_team == opponent,
                PlayerHistoricalPerformance.fantasy_points_ppr.isnot(None),
                Player.position == position
            )
        ).all()

        points = [r.fantasy_points_ppr for r in rows]
        if len(points) < self.MIN_SPLIT_SAMPLE:
            return {
                "avg_points_allowed": None,
                "sample_size": len(points),
                "data_confidence": "insufficient",
                "note": f"Not enough logged historical games against {opponent} at {position} yet."
            }

        return {
            "avg_points_allowed": round(statistics.mean(points), 2),
            "std_dev": round(statistics.stdev(points), 2) if len(points) > 1 else 0.0,
            "sample_size": len(points),
            "data_confidence": "computed"
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

    async def _calculate_breakout_probability(self, player: Player, points_series: Optional[List[float]] = None) -> Dict[str, Any]:
        """Calculate breakout probability using various factors, including a
        real historical performance trend (see historical_trend below)."""
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

        # --- CATEGORY: Computed (merged from advanced_historical_service.py) ---
        # Everything above is derived from static/current-season Player fields.
        # advanced_historical_service.py's analyze_breakout_candidates() instead
        # computed a real recent-vs-earlier-games improvement rate and a
        # coefficient-of-variation consistency score from actual weekly
        # PlayerHistoricalPerformance logs -- a genuinely stronger, time-series
        # signal the static factors above can't see. Merged in here rather than
        # kept only in the now-decommissioned duplicate. Honestly reports
        # insufficient data (and contributes nothing to the score) rather than
        # fabricating a trend when fewer than 4 logged games exist per side.
        historical_trend: Dict[str, Any]
        points_series = points_series or []
        if len(points_series) >= 8:
            recent = points_series[-6:]
            earlier = points_series[-12:-6] if len(points_series) >= 12 else points_series[:-6]
        else:
            recent, earlier = [], []

        if len(recent) >= 4 and len(earlier) >= 4:
            recent_avg = statistics.mean(recent)
            earlier_avg = statistics.mean(earlier)
            improvement_rate = (recent_avg - earlier_avg) / earlier_avg if earlier_avg > 0 else 0.0
            cv = statistics.stdev(recent) / recent_avg if recent_avg > 0 and len(recent) > 1 else None

            if improvement_rate > 0.25:
                probability += 0.15
                factors.append("Significant real recent-vs-earlier performance improvement")
            if cv is not None and cv < 0.4:
                probability += 0.05
                factors.append("Consistent recent performance (low game-to-game variance)")

            historical_trend = {
                "recent_avg_points": round(recent_avg, 2),
                "earlier_avg_points": round(earlier_avg, 2),
                "improvement_rate": round(improvement_rate * 100, 1),
                "consistency_cv": round(cv, 3) if cv is not None else None,
                "games_analyzed": len(recent) + len(earlier),
                "data_confidence": "computed"
            }
        else:
            historical_trend = {
                "recent_avg_points": None,
                "earlier_avg_points": None,
                "improvement_rate": None,
                "consistency_cv": None,
                "games_analyzed": len(points_series),
                "data_confidence": "insufficient",
                "note": "Needs at least 4 logged games each in a recent and an earlier window to compute a real trend."
            }

        return {
            "probability": min(probability, 1.0),
            "confidence": "HIGH" if probability > 0.7 else "MEDIUM" if probability > 0.5 else "LOW",
            "key_factors": factors,
            "historical_trend": historical_trend
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

    # --- Game situation analysis ---
    # This whole block used to be six hardcoded methods returning the exact
    # same numbers (12.5/10.8, 11.2/13.1, 9.8/14.2, 10.5/13.8/12.1, "games
    # missed: 2") for every player regardless of player_id -- this was the
    # confirmed bug behind the "Game Situations" tab looking identical no
    # matter who was selected. Each method below is now one of:
    #   CATEGORY Computed  -- a real, per-player query/join against real data
    #   CATEGORY Heuristic -- a real per-player query standing in for a more
    #                         sophisticated calculation (e.g. keyword-bucketing
    #                         a free-text field instead of a structured enum)
    #   CATEGORY Insufficient data -- no data source exists for the claim at
    #                         all; honestly reported instead of fabricated
    # Note: PlayerHistoricalPerformance is populated by
    # historical_data_service.py's Sleeper sync, but that sync does not
    # currently write game_location/weather_conditions/game_script for any
    # record (see _process_weekly_stats), and no records exist yet in this
    # deployment. So on this database, the Computed/Heuristic methods below
    # will legitimately report "insufficient data" today -- that's a real,
    # per-player-parameterized query correctly finding nothing, not a fake
    # number. They'll start returning real, differing-per-player results the
    # moment that data is synced.
    async def _analyze_home_away_splits(self, player_id: int, historical_data: Dict) -> Dict[str, Any]:
        """CATEGORY: Computed. Real home/away fantasy-point split from this
        player's own historical game log (PlayerHistoricalPerformance.game_location)."""
        records = self.db.query(PlayerHistoricalPerformance).filter(
            PlayerHistoricalPerformance.player_id == player_id,
            PlayerHistoricalPerformance.game_location.isnot(None),
            PlayerHistoricalPerformance.fantasy_points_ppr.isnot(None)
        ).all()

        home_points = [r.fantasy_points_ppr for r in records if r.game_location == GameLocation.HOME]
        away_points = [r.fantasy_points_ppr for r in records if r.game_location == GameLocation.AWAY]

        if len(home_points) < self.MIN_SPLIT_SAMPLE or len(away_points) < self.MIN_SPLIT_SAMPLE:
            return {
                "home_average": None,
                "away_average": None,
                "preference": "INSUFFICIENT_DATA",
                "sample_size": {"home": len(home_points), "away": len(away_points)},
                "data_confidence": "insufficient",
                "note": "Needs at least 2 logged home games and 2 away games; not enough game-log data synced for this player yet."
            }

        home_avg = round(statistics.mean(home_points), 2)
        away_avg = round(statistics.mean(away_points), 2)
        return {
            "home_average": home_avg,
            "away_average": away_avg,
            "preference": "HOME" if home_avg > away_avg else "AWAY",
            "sample_size": {"home": len(home_points), "away": len(away_points)},
            "data_confidence": "computed"
        }

    async def _analyze_weather_impact(self, player_id: int, historical_data: Dict) -> Dict[str, Any]:
        """CATEGORY: Heuristic. Buckets this player's logged games into
        dome/outdoor via a keyword match against weather_conditions (a
        free-text field) -- a real per-player signal, but a proxy rather
        than a structured venue lookup."""
        records = self.db.query(PlayerHistoricalPerformance).filter(
            PlayerHistoricalPerformance.player_id == player_id,
            PlayerHistoricalPerformance.weather_conditions.isnot(None),
            PlayerHistoricalPerformance.fantasy_points_ppr.isnot(None)
        ).all()

        dome_points = [r.fantasy_points_ppr for r in records if 'dome' in (r.weather_conditions or '').lower()]
        outdoor_points = [r.fantasy_points_ppr for r in records if 'dome' not in (r.weather_conditions or '').lower()]

        if len(dome_points) < self.MIN_SPLIT_SAMPLE or len(outdoor_points) < self.MIN_SPLIT_SAMPLE:
            return {
                "outdoor_performance": None,
                "dome_performance": None,
                "weather_sensitivity": "INSUFFICIENT_DATA",
                "key_factors": [],
                "data_confidence": "insufficient",
                "note": "No logged weather_conditions data for this player yet (or too few games to split dome vs outdoor)."
            }

        outdoor_avg = round(statistics.mean(outdoor_points), 2)
        dome_avg = round(statistics.mean(dome_points), 2)
        variance = abs(outdoor_avg - dome_avg)
        sensitivity = "HIGH" if variance > 3 else "MEDIUM" if variance > 1.5 else "LOW"
        return {
            "outdoor_performance": outdoor_avg,
            "dome_performance": dome_avg,
            "weather_sensitivity": sensitivity,
            "key_factors": [f"{len(dome_points)} dome games vs {len(outdoor_points)} outdoor games logged"],
            "data_confidence": "heuristic"
        }

    async def _analyze_vs_opponent_strength(self, player_id: int, historical_data: Dict) -> Dict[str, Any]:
        """CATEGORY: Insufficient data (genuinely not feasible this pass).
        Classifying a player's *historical* games by the strength of the
        defense they actually faced that week would require joining each
        game-log row to that week's real defensive ranking at the time --
        this app has no such join: PlayerHistoricalPerformance rows don't
        carry an opponent_team the sync ever populates, and there's no
        historical (as-of-that-week) defensive-ranking table to join
        against even if they did. Building that is a new data pipeline, not
        a bug fix, so we report the honest gap instead of the old
        fabricated 9.8/14.2 split shown for every player.
        For a *forward-looking* equivalent that IS real, see
        analyze_strength_of_schedule() / _calculate_matchup_difficulty(),
        which use the real DefensiveMatchupRanking table."""
        return {
            "vs_strong_defense": None,
            "vs_weak_defense": None,
            "matchup_dependency": "INSUFFICIENT_DATA",
            "optimal_targets": [],
            "data_confidence": "insufficient",
            "note": "This app does not yet link historical game logs to the defensive strength faced that week. See the Strength of Schedule tab for real forward-looking opponent-difficulty data."
        }

    async def _analyze_game_script_impact(self, player_id: int, historical_data: Dict) -> Dict[str, Any]:
        """CATEGORY: Heuristic. Buckets this player's logged games by the
        free-text game_script field (e.g. "blowout_win", "close_game") into
        leading/trailing/close via keyword matching -- real per-player data,
        but a proxy since the field isn't a structured enum."""
        records = self.db.query(PlayerHistoricalPerformance).filter(
            PlayerHistoricalPerformance.player_id == player_id,
            PlayerHistoricalPerformance.game_script.isnot(None),
            PlayerHistoricalPerformance.fantasy_points_ppr.isnot(None)
        ).all()

        def _bucket(script: str) -> Optional[str]:
            s = script.lower()
            if 'blowout_win' in s or ('leading' in s and 'trailing' not in s):
                return 'leading'
            if 'blowout_loss' in s or 'trailing' in s:
                return 'trailing'
            if 'close' in s:
                return 'close'
            return None

        buckets: Dict[str, List[float]] = defaultdict(list)
        for r in records:
            bucket = _bucket(r.game_script)
            if bucket:
                buckets[bucket].append(r.fantasy_points_ppr)

        if sum(len(v) for v in buckets.values()) < self.MIN_SPLIT_SAMPLE * 2:
            return {
                "leading_games": None,
                "trailing_games": None,
                "close_games": None,
                "script_preference": "INSUFFICIENT_DATA",
                "garbage_time_boost": None,
                "data_confidence": "insufficient",
                "note": "No logged game_script data for this player yet."
            }

        averages = {k: round(statistics.mean(v), 2) for k, v in buckets.items() if v}
        preference = max(averages, key=averages.get) if averages else None
        return {
            "leading_games": averages.get('leading'),
            "trailing_games": averages.get('trailing'),
            "close_games": averages.get('close'),
            "script_preference": preference.upper() if preference else "INSUFFICIENT_DATA",
            "garbage_time_boost": (averages.get('trailing', 0) > averages.get('leading', 0)) if 'trailing' in averages and 'leading' in averages else None,
            "data_confidence": "heuristic"
        }

    async def _analyze_injury_impact(self, player_id: int, historical_data: Dict) -> Dict[str, Any]:
        """CATEGORY: split. Current injury status is a real, live per-player
        field (Player.injury_status) -- Computed. Historical "games missed" /
        "return-to-form performance" would need a per-game injury log this
        app doesn't have (Player.games_played/games_started are also
        unpopulated), so that half is honestly reported as insufficient
        rather than the old fabricated "games_missed: 2, return_performance:
        85.2" shown for every player regardless of their actual health."""
        player = self.db.query(Player).filter(Player.id == player_id).first()
        if not player:
            return {
                "current_status": "UNKNOWN",
                "injury_risk": "INSUFFICIENT_DATA",
                "historical_impact": "insufficient_data",
                "data_confidence": "insufficient"
            }

        status = player.injury_status if player.injury_status else InjuryStatus.HEALTHY
        risk = "LOW" if status == InjuryStatus.HEALTHY else "HIGH" if status in (InjuryStatus.OUT, InjuryStatus.IR) else "MODERATE"

        return {
            "current_status": status.value,
            "body_part": player.injury_body_part,
            "notes": player.injury_notes,
            "status_updated_at": player.injury_updated_at.isoformat() if player.injury_updated_at else None,
            "injury_risk": risk,
            "historical_impact": "insufficient_data",
            "historical_impact_note": "No per-game injury-designation log available to compute games missed or return-to-form performance.",
            "data_confidence": "computed"
        }

    async def _generate_situational_insights(self, situations: Dict) -> List[str]:
        """Generate insights from situational analysis -- only from sections
        that actually have data; insufficient-data sections are skipped
        rather than turned into a fabricated insight."""
        insights = []

        home_away = situations.get('home_vs_away', {})
        if home_away.get('preference') == 'HOME':
            insights.append(f"Performs better at home ({home_away['home_average']} vs {home_away['away_average']} away)")
        elif home_away.get('preference') == 'AWAY':
            insights.append(f"Performs better on the road ({home_away['away_average']} vs {home_away['home_average']} home)")

        game_script = situations.get('game_script', {})
        if game_script.get('script_preference') == 'TRAILING':
            insights.append("Benefits from negative game script and garbage time")

        if not insights:
            insights.append("Not enough logged game-situation data yet to draw a situational insight for this player")

        return insights

    async def _analyze_upcoming_situations(self, player: Player) -> Dict[str, Any]:
        """CATEGORY: Computed. Reuses the same real NFLGame /
        DefensiveMatchupRanking infrastructure as analyze_strength_of_schedule(),
        instead of the previous hardcoded 'next game is HOME vs a WEAK dome
        opponent' shown for literally every player."""
        matchup_service = MatchupAnalysisService(self.db)
        matchup_info = matchup_service.analyze_player_upcoming_matchups(player, weeks_ahead=1)

        if "error" in matchup_info or not matchup_info.get("upcoming_matchups"):
            return {
                "next_game": None,
                "outlook": "No synced schedule data for this player's next game yet.",
                "data_confidence": "insufficient"
            }

        next_game = matchup_info["upcoming_matchups"][0]
        return {
            "next_game": {
                "week": next_game["week"],
                "opponent": next_game["opponent"],
                "location": "HOME" if next_game["is_home"] else "AWAY",
                "opponent_rank_vs_position": next_game.get("opponent_rank_vs_position"),
                "matchup_rating": next_game.get("matchup_rating")
            },
            "outlook": matchup_info.get("outlook", "Unknown"),
            "data_confidence": "computed"
        }

    async def _generate_cross_player_situational_insights(self, situation_analysis: List[Dict]) -> List[str]:
        """Generate insights comparing situational factors across players"""
        insights = []
        
        if len(situation_analysis) > 1:
            insights.append("Player situational factors analyzed and compared")
            insights.append("Consider upcoming game locations and matchups when making decisions")
        
        return insights