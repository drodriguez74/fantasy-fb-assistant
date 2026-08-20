"""
Advanced Historical Analysis Service

Provides sophisticated analytical features for historical performance data including:
- Player comparison and benchmarking
- Strength of schedule analysis  
- Advanced statistical metrics
- Game situation analysis
- Performance prediction models
"""

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import logging
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, desc

from app.models.player import Player, Position
from app.models.historical_performance import (
    PlayerHistoricalPerformance, 
    PlayerSeasonSummary, 
    PlayerTrend,
    MatchupHistory
)

logger = logging.getLogger(__name__)


class AdvancedHistoricalService:
    """Advanced analytical capabilities for historical performance data"""
    
    def __init__(self, db: Session):
        self.db = db
        self.scaler = StandardScaler()
    
    async def compare_players_advanced(
        self, 
        player_ids: List[int], 
        seasons: int = 3,
        analysis_type: str = "comprehensive"
    ) -> Dict[str, Any]:
        """
        Advanced player comparison with statistical significance testing
        """
        try:
            if len(player_ids) < 2:
                return {"error": "At least 2 players required for comparison"}
            
            players_data = {}
            
            # Get data for each player
            for player_id in player_ids:
                player = self.db.query(Player).filter(Player.id == player_id).first()
                if not player:
                    continue
                
                # Get historical performances
                performances = self.db.query(PlayerHistoricalPerformance).filter(
                    and_(
                        PlayerHistoricalPerformance.player_id == player_id,
                        PlayerHistoricalPerformance.fantasy_points_ppr.isnot(None)
                    )
                ).order_by(
                    PlayerHistoricalPerformance.season,
                    PlayerHistoricalPerformance.week
                ).all()
                
                if len(performances) < 5:  # Need minimum data
                    continue
                
                # Calculate advanced metrics
                fantasy_points = [p.fantasy_points_ppr for p in performances]
                
                players_data[player_id] = {
                    "player_info": {
                        "id": player_id,
                        "name": player.name,
                        "position": player.position.value if player.position else "Unknown"
                    },
                    "raw_data": {
                        "performances": performances,
                        "fantasy_points": fantasy_points
                    },
                    "basic_stats": {
                        "games_played": len(fantasy_points),
                        "mean": np.mean(fantasy_points),
                        "median": np.median(fantasy_points),
                        "std_dev": np.std(fantasy_points),
                        "min": np.min(fantasy_points),
                        "max": np.max(fantasy_points),
                        "range": np.max(fantasy_points) - np.min(fantasy_points)
                    }
                }
                
                # Advanced statistical metrics
                if len(fantasy_points) > 1:
                    q1, q3 = np.percentile(fantasy_points, [25, 75])
                    iqr = q3 - q1
                    
                    players_data[player_id]["advanced_stats"] = {
                        "coefficient_of_variation": np.std(fantasy_points) / np.mean(fantasy_points) if np.mean(fantasy_points) > 0 else 0,
                        "skewness": float(stats.skew(fantasy_points)),
                        "kurtosis": float(stats.kurtosis(fantasy_points)),
                        "q1": float(q1),
                        "q3": float(q3),
                        "iqr": float(iqr),
                        "outlier_threshold_low": float(q1 - 1.5 * iqr),
                        "outlier_threshold_high": float(q3 + 1.5 * iqr)
                    }
                    
                    # Performance consistency metrics
                    players_data[player_id]["consistency_metrics"] = {
                        "boom_rate": len([fp for fp in fantasy_points if fp >= q3]) / len(fantasy_points),
                        "bust_rate": len([fp for fp in fantasy_points if fp <= q1]) / len(fantasy_points),
                        "steady_rate": len([fp for fp in fantasy_points if q1 < fp < q3]) / len(fantasy_points),
                        "ceiling_games": len([fp for fp in fantasy_points if fp >= np.percentile(fantasy_points, 90)]),
                        "floor_games": len([fp for fp in fantasy_points if fp <= np.percentile(fantasy_points, 10)])
                    }
            
            if len(players_data) < 2:
                return {"error": "Insufficient data for comparison"}
            
            # Statistical comparisons
            comparisons = await self._perform_statistical_tests(players_data)
            
            # Rankings and relative performance
            rankings = await self._calculate_relative_rankings(players_data)
            
            # Situational analysis
            situational = await self._analyze_situational_performance(players_data)
            
            return {
                "comparison_type": analysis_type,
                "players_compared": len(players_data),
                "players_data": {pid: {
                    "player_info": data["player_info"],
                    "basic_stats": data["basic_stats"],
                    "advanced_stats": data.get("advanced_stats", {}),
                    "consistency_metrics": data.get("consistency_metrics", {})
                } for pid, data in players_data.items()},
                "statistical_comparisons": comparisons,
                "relative_rankings": rankings,
                "situational_analysis": situational,
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error in advanced player comparison: {str(e)}")
            return {"error": f"Advanced comparison failed: {str(e)}"}
    
    async def _perform_statistical_tests(self, players_data: Dict) -> Dict[str, Any]:
        """Perform statistical significance tests between players"""
        results = {
            "anova_test": None,
            "pairwise_tests": [],
            "effect_sizes": []
        }
        
        try:
            # Prepare data for ANOVA
            groups = []
            group_labels = []
            
            for player_id, data in players_data.items():
                fantasy_points = data["raw_data"]["fantasy_points"]
                groups.append(fantasy_points)
                group_labels.append(data["player_info"]["name"])
            
            # Perform ANOVA test
            if len(groups) >= 2:
                f_stat, p_value = stats.f_oneway(*groups)
                results["anova_test"] = {
                    "f_statistic": float(f_stat),
                    "p_value": float(p_value),
                    "significant": p_value < 0.05,
                    "interpretation": "Significant difference between players" if p_value < 0.05 else "No significant difference"
                }
            
            # Pairwise comparisons
            player_ids = list(players_data.keys())
            for i in range(len(player_ids)):
                for j in range(i + 1, len(player_ids)):
                    pid1, pid2 = player_ids[i], player_ids[j]
                    
                    points1 = players_data[pid1]["raw_data"]["fantasy_points"]
                    points2 = players_data[pid2]["raw_data"]["fantasy_points"]
                    
                    # Mann-Whitney U test (non-parametric)
                    statistic, p_value = stats.mannwhitneyu(points1, points2, alternative='two-sided')
                    
                    # Effect size (Cohen's d)
                    mean1, mean2 = np.mean(points1), np.mean(points2)
                    std1, std2 = np.std(points1), np.std(points2)
                    pooled_std = np.sqrt((std1**2 + std2**2) / 2)
                    cohens_d = (mean1 - mean2) / pooled_std if pooled_std > 0 else 0
                    
                    results["pairwise_tests"].append({
                        "player1": players_data[pid1]["player_info"]["name"],
                        "player2": players_data[pid2]["player_info"]["name"],
                        "statistic": float(statistic),
                        "p_value": float(p_value),
                        "significant": p_value < 0.05,
                        "cohens_d": float(cohens_d),
                        "effect_size": self._interpret_effect_size(abs(cohens_d)),
                        "mean_difference": float(mean1 - mean2)
                    })
            
        except Exception as e:
            logger.error(f"Error in statistical tests: {str(e)}")
        
        return results
    
    def _interpret_effect_size(self, cohens_d: float) -> str:
        """Interpret Cohen's d effect size"""
        if cohens_d < 0.2:
            return "negligible"
        elif cohens_d < 0.5:
            return "small"
        elif cohens_d < 0.8:
            return "medium"
        else:
            return "large"
    
    async def _calculate_relative_rankings(self, players_data: Dict) -> Dict[str, Any]:
        """Calculate relative rankings across different metrics"""
        rankings = {}
        
        metrics = [
            ("mean", "Average Points"),
            ("consistency", "Consistency"),
            ("ceiling", "Ceiling"),
            ("floor", "Floor")
        ]
        
        for metric_key, metric_name in metrics:
            player_scores = []
            
            for player_id, data in players_data.items():
                if metric_key == "mean":
                    score = data["basic_stats"]["mean"]
                elif metric_key == "consistency":
                    score = 1 - data["advanced_stats"].get("coefficient_of_variation", 1)
                elif metric_key == "ceiling":
                    score = data["basic_stats"]["max"]
                elif metric_key == "floor":
                    score = data["basic_stats"]["min"]
                else:
                    score = 0
                
                player_scores.append({
                    "player_id": player_id,
                    "player_name": data["player_info"]["name"],
                    "score": score
                })
            
            # Sort and rank
            player_scores.sort(key=lambda x: x["score"], reverse=True)
            
            for i, player in enumerate(player_scores):
                player["rank"] = i + 1
            
            rankings[metric_key] = {
                "metric_name": metric_name,
                "rankings": player_scores
            }
        
        return rankings
    
    async def _analyze_situational_performance(self, players_data: Dict) -> Dict[str, Any]:
        """Analyze performance in different game situations"""
        situational = {}
        
        for player_id, data in players_data.items():
            performances = data["raw_data"]["performances"]
            player_name = data["player_info"]["name"]
            
            # Home vs Away analysis
            home_games = [p for p in performances if p.game_location and p.game_location.value == "home"]
            away_games = [p for p in performances if p.game_location and p.game_location.value == "away"]
            
            home_points = [p.fantasy_points_ppr for p in home_games if p.fantasy_points_ppr]
            away_points = [p.fantasy_points_ppr for p in away_games if p.fantasy_points_ppr]
            
            # Recent vs Early season
            recent_games = performances[-8:] if len(performances) >= 8 else performances
            early_games = performances[:8] if len(performances) >= 8 else []
            
            recent_points = [p.fantasy_points_ppr for p in recent_games if p.fantasy_points_ppr]
            early_points = [p.fantasy_points_ppr for p in early_games if p.fantasy_points_ppr]
            
            situational[player_id] = {
                "player_name": player_name,
                "home_vs_away": {
                    "home_games": len(home_points),
                    "home_avg": np.mean(home_points) if home_points else 0,
                    "away_games": len(away_points),
                    "away_avg": np.mean(away_points) if away_points else 0,
                    "home_advantage": (np.mean(home_points) - np.mean(away_points)) if home_points and away_points else 0
                },
                "seasonal_timing": {
                    "early_season_avg": np.mean(early_points) if early_points else 0,
                    "recent_games_avg": np.mean(recent_points) if recent_points else 0,
                    "improvement": (np.mean(recent_points) - np.mean(early_points)) if early_points and recent_points else 0
                }
            }
        
        return situational
    
    async def analyze_strength_of_schedule(
        self, 
        player_id: int, 
        season: int = 2024
    ) -> Dict[str, Any]:
        """
        Analyze strength of schedule for a player's opponents
        """
        try:
            # Get player's games for the season
            player = self.db.query(Player).filter(Player.id == player_id).first()
            if not player:
                return {"error": "Player not found"}
            
            performances = self.db.query(PlayerHistoricalPerformance).filter(
                and_(
                    PlayerHistoricalPerformance.player_id == player_id,
                    PlayerHistoricalPerformance.season == season,
                    PlayerHistoricalPerformance.opponent_team.isnot(None)
                )
            ).all()
            
            if not performances:
                return {"error": "No performance data found for this season"}
            
            # Calculate opponent strength metrics
            opponent_analysis = {}
            total_points_allowed = []
            
            for perf in performances:
                opponent = perf.opponent_team
                if opponent not in opponent_analysis:
                    # Get all games against this opponent across all players
                    opponent_games = self.db.query(PlayerHistoricalPerformance).filter(
                        and_(
                            PlayerHistoricalPerformance.opponent_team == opponent,
                            PlayerHistoricalPerformance.season == season,
                            PlayerHistoricalPerformance.fantasy_points_ppr.isnot(None)
                        )
                    ).all()
                    
                    opponent_points = [g.fantasy_points_ppr for g in opponent_games]
                    
                    if opponent_points:
                        opponent_analysis[opponent] = {
                            "games_sample": len(opponent_points),
                            "avg_points_allowed": np.mean(opponent_points),
                            "std_points_allowed": np.std(opponent_points),
                            "ranking": 0  # Will be calculated later
                        }
                        total_points_allowed.extend(opponent_points)
            
            # Calculate opponent rankings (lower avg = better defense = harder matchup)
            avg_league = np.mean(total_points_allowed) if total_points_allowed else 0
            
            opponents_ranked = []
            for opponent, stats in opponent_analysis.items():
                difficulty_score = avg_league - stats["avg_points_allowed"]  # Positive = harder matchup
                opponents_ranked.append({
                    "opponent": opponent,
                    "avg_points_allowed": stats["avg_points_allowed"],
                    "difficulty_score": difficulty_score,
                    "games_sample": stats["games_sample"]
                })
            
            opponents_ranked.sort(key=lambda x: x["difficulty_score"], reverse=True)
            
            # Calculate player's strength of schedule
            player_sos_scores = []
            player_performances = []
            
            for perf in performances:
                opponent_stats = opponent_analysis.get(perf.opponent_team)
                if opponent_stats and perf.fantasy_points_ppr:
                    difficulty = avg_league - opponent_stats["avg_points_allowed"]
                    player_sos_scores.append(difficulty)
                    player_performances.append({
                        "week": perf.week,
                        "opponent": perf.opponent_team,
                        "points_scored": perf.fantasy_points_ppr,
                        "opponent_difficulty": difficulty,
                        "vs_tough_defense": difficulty > 0
                    })
            
            # Calculate overall metrics
            avg_sos = np.mean(player_sos_scores) if player_sos_scores else 0
            tough_games = [p for p in player_performances if p["vs_tough_defense"]]
            easy_games = [p for p in player_performances if not p["vs_tough_defense"]]
            
            return {
                "player_id": player_id,
                "player_name": player.name,
                "season": season,
                "strength_of_schedule": {
                    "overall_difficulty": float(avg_sos),
                    "difficulty_ranking": "Above Average" if avg_sos > 0 else "Below Average",
                    "games_analyzed": len(player_performances),
                    "tough_matchups": len(tough_games),
                    "easy_matchups": len(easy_games)
                },
                "performance_vs_difficulty": {
                    "vs_tough_defenses": {
                        "games": len(tough_games),
                        "avg_points": np.mean([g["points_scored"] for g in tough_games]) if tough_games else 0,
                        "success_rate": len([g for g in tough_games if g["points_scored"] > avg_league]) / len(tough_games) if tough_games else 0
                    },
                    "vs_easy_defenses": {
                        "games": len(easy_games),
                        "avg_points": np.mean([g["points_scored"] for g in easy_games]) if easy_games else 0,
                        "success_rate": len([g for g in easy_games if g["points_scored"] > avg_league]) / len(easy_games) if easy_games else 0
                    }
                },
                "opponent_rankings": opponents_ranked[:10],  # Top 10 toughest
                "game_log": player_performances,
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error analyzing strength of schedule: {str(e)}")
            return {"error": f"SOS analysis failed: {str(e)}"}
    
    async def analyze_breakout_candidates(
        self, 
        position: Optional[str] = None,
        min_games: int = 8
    ) -> Dict[str, Any]:
        """
        Identify potential breakout candidates based on advanced metrics
        """
        try:
            # Get recent performance data
            query = self.db.query(PlayerHistoricalPerformance).join(Player)
            
            if position:
                query = query.filter(Player.position == position.upper())
            
            recent_performances = query.filter(
                PlayerHistoricalPerformance.fantasy_points_ppr.isnot(None)
            ).order_by(
                PlayerHistoricalPerformance.season.desc(),
                PlayerHistoricalPerformance.week.desc()
            ).all()
            
            # Group by player and analyze trends
            player_trends = {}
            
            for perf in recent_performances:
                player_id = perf.player_id
                if player_id not in player_trends:
                    player = self.db.query(Player).filter(Player.id == player_id).first()
                    if not player:
                        continue
                    
                    player_trends[player_id] = {
                        "player_info": {
                            "id": player_id,
                            "name": player.name,
                            "position": player.position.value if player.position else "Unknown"
                        },
                        "performances": []
                    }
                
                player_trends[player_id]["performances"].append({
                    "week": perf.week,
                    "season": perf.season,
                    "points": perf.fantasy_points_ppr,
                    "snap_percentage": perf.snap_percentage or 0,
                    "target_share": perf.target_share or 0
                })
            
            # Analyze each player for breakout indicators
            breakout_candidates = []
            
            for player_id, data in player_trends.items():
                performances = data["performances"]
                
                if len(performances) < min_games:
                    continue
                
                # Sort by recency (most recent first)
                performances.sort(key=lambda x: (x["season"], x["week"]), reverse=True)
                
                recent_games = performances[:6]  # Last 6 games
                earlier_games = performances[6:12] if len(performances) >= 12 else performances[6:]
                
                if len(recent_games) < 3 or len(earlier_games) < 3:
                    continue
                
                # Calculate trends
                recent_avg = np.mean([g["points"] for g in recent_games])
                earlier_avg = np.mean([g["points"] for g in earlier_games])
                
                improvement = recent_avg - earlier_avg
                improvement_rate = improvement / earlier_avg if earlier_avg > 0 else 0
                
                # Opportunity metrics
                recent_snaps = np.mean([g["snap_percentage"] for g in recent_games if g["snap_percentage"] > 0])
                recent_targets = np.mean([g["target_share"] for g in recent_games if g["target_share"] > 0])
                
                # Breakout score calculation
                breakout_score = 0
                indicators = []
                
                # Strong recent improvement
                if improvement_rate > 0.25:  # 25% improvement
                    breakout_score += 25
                    indicators.append("Significant performance improvement")
                
                # High snap percentage
                if recent_snaps > 70:
                    breakout_score += 20
                    indicators.append("High snap share")
                
                # Good target share (for pass catchers)
                if data["player_info"]["position"] in ["WR", "TE"] and recent_targets > 15:
                    breakout_score += 15
                    indicators.append("Strong target share")
                
                # Consistency in recent games
                recent_points = [g["points"] for g in recent_games]
                cv = np.std(recent_points) / np.mean(recent_points) if np.mean(recent_points) > 0 else 1
                if cv < 0.4:  # Low coefficient of variation = consistent
                    breakout_score += 10
                    indicators.append("Consistent recent performance")
                
                # Young player trending up
                total_games = len(performances)
                if total_games < 32:  # Less than 2 full seasons
                    breakout_score += 10
                    indicators.append("Young player with limited sample")
                
                if breakout_score >= 40:  # Threshold for consideration
                    breakout_candidates.append({
                        "player_info": data["player_info"],
                        "breakout_score": breakout_score,
                        "indicators": indicators,
                        "metrics": {
                            "recent_avg_points": round(recent_avg, 2),
                            "earlier_avg_points": round(earlier_avg, 2),
                            "improvement": round(improvement, 2),
                            "improvement_rate": round(improvement_rate * 100, 1),
                            "recent_snap_percentage": round(recent_snaps, 1),
                            "recent_target_share": round(recent_targets, 1),
                            "games_analyzed": len(performances),
                            "consistency_score": round(1 - cv, 2)
                        }
                    })
            
            # Sort by breakout score
            breakout_candidates.sort(key=lambda x: x["breakout_score"], reverse=True)
            
            return {
                "position_filter": position,
                "min_games_threshold": min_games,
                "candidates_found": len(breakout_candidates),
                "breakout_candidates": breakout_candidates[:15],  # Top 15
                "analysis_criteria": [
                    "Performance improvement rate",
                    "Snap percentage trends",
                    "Target share (for receivers)",
                    "Recent consistency",
                    "Player experience level"
                ],
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error analyzing breakout candidates: {str(e)}")
            return {"error": f"Breakout analysis failed: {str(e)}"}