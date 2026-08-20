"""
Advanced Analytics Service for Fantasy Football

This service provides sophisticated statistical analysis, machine learning models,
and optimization algorithms for fantasy football decision making.
"""

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
import statsmodels.api as sm
from statsmodels.tsa.arima.model import ARIMA
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import logging
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from app.models.player import Player, Position
from app.models.historical_performance import (
    PlayerHistoricalPerformance, 
    PlayerSeasonSummary, 
    PlayerTrend,
    MatchupHistory
)

logger = logging.getLogger(__name__)


class AdvancedAnalyticsService:
    """
    Comprehensive analytics service providing:
    - Predictive modeling for player performance
    - Portfolio optimization for roster construction
    - Statistical correlation analysis
    - Machine learning-based recommendations
    - Advanced metrics and scoring systems
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.scaler = StandardScaler()
        
    # PREDICTIVE MODELING
    
    async def predict_player_performance(
        self, 
        player_id: int, 
        weeks_ahead: int = 4,
        model_type: str = "ensemble"
    ) -> Dict[str, Any]:
        """
        Predict player performance using machine learning models
        
        Args:
            player_id: Player to predict for
            weeks_ahead: Number of weeks to predict
            model_type: 'linear', 'rf', 'gb', 'ensemble'
        """
        try:
            # Get historical data
            player_data = await self._get_player_prediction_data(player_id)
            
            if len(player_data) < 10:  # Need minimum data
                return {"error": "Insufficient historical data for prediction"}
            
            # Prepare features and target
            features, target = self._prepare_prediction_features(player_data)
            
            if len(features) == 0:
                return {"error": "Unable to prepare prediction features"}
            
            # Train models
            predictions = {}
            confidence_scores = {}
            
            if model_type in ["linear", "ensemble"]:
                pred, conf = await self._train_linear_model(features, target, weeks_ahead)
                predictions["linear"] = pred
                confidence_scores["linear"] = conf
            
            if model_type in ["rf", "ensemble"]:
                pred, conf = await self._train_random_forest_model(features, target, weeks_ahead)
                predictions["random_forest"] = pred
                confidence_scores["random_forest"] = conf
            
            if model_type in ["gb", "ensemble"]:
                pred, conf = await self._train_gradient_boosting_model(features, target, weeks_ahead)
                predictions["gradient_boosting"] = pred
                confidence_scores["gradient_boosting"] = conf
            
            # Ensemble prediction if multiple models
            if model_type == "ensemble" and len(predictions) > 1:
                ensemble_pred = np.mean([pred for pred in predictions.values()])
                ensemble_conf = np.mean([conf for conf in confidence_scores.values()])
                predictions["ensemble"] = ensemble_pred
                confidence_scores["ensemble"] = ensemble_conf
            
            # Get player info
            player = self.db.query(Player).filter(Player.id == player_id).first()
            
            return {
                "player_id": player_id,
                "player_name": player.name if player else "Unknown",
                "position": player.position.value if player and player.position else "Unknown",
                "weeks_ahead": weeks_ahead,
                "predictions": predictions,
                "confidence_scores": confidence_scores,
                "model_type": model_type,
                "data_points_used": len(player_data),
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error predicting player performance: {str(e)}")
            return {"error": f"Prediction failed: {str(e)}"}
    
    async def _get_player_prediction_data(self, player_id: int) -> List[Dict]:
        """Get historical performance data for prediction"""
        performances = self.db.query(PlayerHistoricalPerformance).filter(
            and_(
                PlayerHistoricalPerformance.player_id == player_id,
                PlayerHistoricalPerformance.week.isnot(None),
                PlayerHistoricalPerformance.fantasy_points_ppr.isnot(None)
            )
        ).order_by(
            PlayerHistoricalPerformance.season,
            PlayerHistoricalPerformance.week
        ).all()
        
        data = []
        for i, perf in enumerate(performances):
            # Create features from historical context
            recent_avg = np.mean([p.fantasy_points_ppr for p in performances[max(0, i-3):i+1] if p.fantasy_points_ppr])
            season_avg = np.mean([p.fantasy_points_ppr for p in performances if p.season == perf.season and p.fantasy_points_ppr])
            
            data.append({
                "week": perf.week,
                "season": perf.season,
                "fantasy_points": perf.fantasy_points_ppr,
                "opponent": perf.opponent_team,
                "location": perf.game_location.value if perf.game_location else "home",
                "recent_avg": recent_avg if not np.isnan(recent_avg) else 0,
                "season_avg": season_avg if not np.isnan(season_avg) else 0,
                "game_date": perf.game_date,
                "snap_percentage": perf.snap_percentage or 0,
                "target_share": perf.target_share or 0
            })
            
        return data
    
    def _prepare_prediction_features(self, player_data: List[Dict]) -> Tuple[np.ndarray, np.ndarray]:
        """Prepare features and target for ML models"""
        df = pd.DataFrame(player_data)
        
        # Create features
        features = []
        targets = []
        
        for i in range(3, len(df)):  # Need at least 3 previous games
            # Feature engineering
            feature_row = [
                df.iloc[i-1]["fantasy_points"],  # Last game
                df.iloc[i-1]["recent_avg"],      # Recent average
                df.iloc[i-1]["season_avg"],      # Season average  
                df.iloc[i]["week"],              # Week number
                1 if df.iloc[i]["location"] == "home" else 0,  # Home/away
                df.iloc[i]["snap_percentage"],   # Snap percentage
                df.iloc[i]["target_share"],      # Target share
                np.mean([df.iloc[j]["fantasy_points"] for j in range(max(0, i-3), i)]),  # 3-game avg
                np.std([df.iloc[j]["fantasy_points"] for j in range(max(0, i-3), i)]),   # 3-game std
            ]
            
            features.append(feature_row)
            targets.append(df.iloc[i]["fantasy_points"])
        
        return np.array(features), np.array(targets)
    
    async def _train_linear_model(self, features: np.ndarray, target: np.ndarray, weeks_ahead: int) -> Tuple[float, float]:
        """Train linear regression model"""
        X_train, X_test, y_train, y_test = train_test_split(features, target, test_size=0.2, random_state=42)
        
        model = Ridge(alpha=1.0)
        model.fit(X_train, y_train)
        
        # Predict on test set for confidence
        y_pred = model.predict(X_test)
        confidence = r2_score(y_test, y_pred)
        
        # Predict future (use last known features as proxy)
        last_features = features[-1:] if len(features) > 0 else np.zeros((1, features.shape[1]))
        prediction = model.predict(last_features)[0]
        
        return float(prediction), float(max(0, confidence))
    
    async def _train_random_forest_model(self, features: np.ndarray, target: np.ndarray, weeks_ahead: int) -> Tuple[float, float]:
        """Train random forest model"""
        X_train, X_test, y_train, y_test = train_test_split(features, target, test_size=0.2, random_state=42)
        
        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(X_train, y_train)
        
        # Predict on test set for confidence
        y_pred = model.predict(X_test)
        confidence = r2_score(y_test, y_pred)
        
        # Predict future
        last_features = features[-1:] if len(features) > 0 else np.zeros((1, features.shape[1]))
        prediction = model.predict(last_features)[0]
        
        return float(prediction), float(max(0, confidence))
    
    async def _train_gradient_boosting_model(self, features: np.ndarray, target: np.ndarray, weeks_ahead: int) -> Tuple[float, float]:
        """Train gradient boosting model"""
        X_train, X_test, y_train, y_test = train_test_split(features, target, test_size=0.2, random_state=42)
        
        model = GradientBoostingRegressor(n_estimators=100, random_state=42)
        model.fit(X_train, y_train)
        
        # Predict on test set for confidence
        y_pred = model.predict(X_test)
        confidence = r2_score(y_test, y_pred)
        
        # Predict future
        last_features = features[-1:] if len(features) > 0 else np.zeros((1, features.shape[1]))
        prediction = model.predict(last_features)[0]
        
        return float(prediction), float(max(0, confidence))
    
    # CORRELATION ANALYSIS
    
    async def analyze_player_correlations(
        self, 
        position: Optional[str] = None,
        min_games: int = 10
    ) -> Dict[str, Any]:
        """
        Analyze correlations between player performances
        """
        try:
            # Get player performance data
            query = self.db.query(PlayerHistoricalPerformance).join(Player)
            
            if position:
                query = query.filter(Player.position == position)
            
            performances = query.filter(
                PlayerHistoricalPerformance.fantasy_points_ppr.isnot(None)
            ).all()
            
            # Group by player
            player_data = {}
            for perf in performances:
                player_id = perf.player_id
                if player_id not in player_data:
                    player_data[player_id] = []
                player_data[player_id].append(perf.fantasy_points_ppr)
            
            # Filter players with minimum games
            player_data = {pid: scores for pid, scores in player_data.items() 
                          if len(scores) >= min_games}
            
            if len(player_data) < 2:
                return {"error": "Insufficient data for correlation analysis"}
            
            # Create correlation matrix
            player_ids = list(player_data.keys())
            correlation_matrix = np.zeros((len(player_ids), len(player_ids)))
            
            for i, pid1 in enumerate(player_ids):
                for j, pid2 in enumerate(player_ids):
                    if i <= j:
                        # Align time series (use common weeks)
                        scores1 = player_data[pid1]
                        scores2 = player_data[pid2]
                        min_len = min(len(scores1), len(scores2))
                        
                        if min_len >= 5:  # Need minimum overlap
                            correlation = np.corrcoef(scores1[:min_len], scores2[:min_len])[0, 1]
                            correlation_matrix[i, j] = correlation
                            correlation_matrix[j, i] = correlation
            
            # Find strongest correlations
            strong_correlations = []
            for i in range(len(player_ids)):
                for j in range(i+1, len(player_ids)):
                    corr_value = correlation_matrix[i, j]
                    if abs(corr_value) > 0.3:  # Significant correlation
                        player1 = self.db.query(Player).filter(Player.id == player_ids[i]).first()
                        player2 = self.db.query(Player).filter(Player.id == player_ids[j]).first()
                        
                        strong_correlations.append({
                            "player1_id": player_ids[i],
                            "player1_name": player1.name if player1 else "Unknown",
                            "player2_id": player_ids[j], 
                            "player2_name": player2.name if player2 else "Unknown",
                            "correlation": float(corr_value),
                            "correlation_type": "positive" if corr_value > 0 else "negative"
                        })
            
            # Sort by absolute correlation value
            strong_correlations.sort(key=lambda x: abs(x["correlation"]), reverse=True)
            
            return {
                "position_filter": position,
                "players_analyzed": len(player_ids),
                "min_games_threshold": min_games,
                "strong_correlations": strong_correlations[:20],  # Top 20
                "correlation_matrix_size": len(player_ids),
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error analyzing correlations: {str(e)}")
            return {"error": f"Correlation analysis failed: {str(e)}"}
    
    # CLUSTERING ANALYSIS
    
    async def cluster_players_by_performance(
        self, 
        position: Optional[str] = None,
        n_clusters: int = 5
    ) -> Dict[str, Any]:
        """
        Cluster players based on performance characteristics
        """
        try:
            # Get player season summaries
            query = self.db.query(PlayerSeasonSummary).join(Player)
            
            if position:
                query = query.filter(Player.position == position)
            
            summaries = query.all()
            
            if len(summaries) < n_clusters:
                return {"error": f"Need at least {n_clusters} players for clustering"}
            
            # Prepare features for clustering
            features = []
            player_info = []
            
            for summary in summaries:
                player = self.db.query(Player).filter(Player.id == summary.player_id).first()
                if not player:
                    continue
                
                feature_row = [
                    summary.avg_fantasy_points_ppr or 0,
                    summary.consistency_score or 0,
                    summary.weekly_ceiling or 0,
                    summary.weekly_floor or 0,
                    summary.boom_weeks or 0,
                    summary.bust_weeks or 0,
                    summary.games_played or 0
                ]
                
                features.append(feature_row)
                player_info.append({
                    "player_id": summary.player_id,
                    "player_name": player.name,
                    "position": player.position.value if player.position else "Unknown",
                    "season": summary.season
                })
            
            if len(features) == 0:
                return {"error": "No valid feature data for clustering"}
            
            # Normalize features
            features_scaled = self.scaler.fit_transform(np.array(features))
            
            # Perform clustering
            kmeans = KMeans(n_clusters=n_clusters, random_state=42)
            cluster_labels = kmeans.fit_predict(features_scaled)
            
            # Analyze clusters
            clusters = {}
            for i, label in enumerate(cluster_labels):
                if label not in clusters:
                    clusters[label] = {
                        "players": [],
                        "characteristics": {},
                        "avg_metrics": {}
                    }
                
                clusters[label]["players"].append(player_info[i])
            
            # Calculate cluster characteristics
            feature_names = ["avg_points", "consistency", "ceiling", "floor", "boom_weeks", "bust_weeks", "games_played"]
            
            for cluster_id, cluster_data in clusters.items():
                cluster_indices = [i for i, label in enumerate(cluster_labels) if label == cluster_id]
                cluster_features = np.array(features)[cluster_indices]
                
                # Calculate averages
                avg_metrics = np.mean(cluster_features, axis=0)
                clusters[cluster_id]["avg_metrics"] = {
                    feature_names[i]: float(avg_metrics[i]) for i in range(len(feature_names))
                }
                
                # Determine cluster characteristics
                if avg_metrics[0] > np.mean([f[0] for f in features]):  # High scoring
                    if avg_metrics[1] > np.mean([f[1] for f in features]):  # High consistency
                        clusters[cluster_id]["characteristics"]["type"] = "Elite Consistent"
                    else:
                        clusters[cluster_id]["characteristics"]["type"] = "High Upside Volatile"
                elif avg_metrics[1] > np.mean([f[1] for f in features]):  # High consistency
                    clusters[cluster_id]["characteristics"]["type"] = "Reliable Floor"
                else:
                    clusters[cluster_id]["characteristics"]["type"] = "Boom/Bust"
            
            return {
                "position_filter": position,
                "n_clusters": n_clusters,
                "total_players": len(features),
                "clusters": clusters,
                "feature_names": feature_names,
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error clustering players: {str(e)}")
            return {"error": f"Clustering analysis failed: {str(e)}"}
    
    # TIME SERIES ANALYSIS
    
    async def analyze_performance_trends(
        self, 
        player_id: int,
        forecast_weeks: int = 4
    ) -> Dict[str, Any]:
        """
        Perform time series analysis and forecasting
        """
        try:
            # Get time series data
            performances = self.db.query(PlayerHistoricalPerformance).filter(
                and_(
                    PlayerHistoricalPerformance.player_id == player_id,
                    PlayerHistoricalPerformance.fantasy_points_ppr.isnot(None)
                )
            ).order_by(
                PlayerHistoricalPerformance.season,
                PlayerHistoricalPerformance.week
            ).all()
            
            if len(performances) < 10:
                return {"error": "Insufficient data for time series analysis"}
            
            # Create time series
            scores = [p.fantasy_points_ppr for p in performances]
            dates = [p.game_date for p in performances if p.game_date]
            
            # Trend analysis
            x = np.arange(len(scores))
            slope, intercept, r_value, p_value, std_err = stats.linregress(x, scores)
            
            # Seasonality detection (simple)
            if len(scores) >= 16:  # At least one season
                season_scores = []
                for i in range(0, len(scores), 16):
                    season_avg = np.mean(scores[i:i+16])
                    season_scores.append(season_avg)
                
                season_trend = np.polyfit(range(len(season_scores)), season_scores, 1)[0] if len(season_scores) > 1 else 0
            else:
                season_trend = 0
            
            # ARIMA forecasting (simplified)
            try:
                # Use simple moving average for forecast if ARIMA fails
                recent_window = min(8, len(scores))
                recent_avg = np.mean(scores[-recent_window:])
                forecast = [recent_avg] * forecast_weeks
                
                # Add trend component
                for i in range(forecast_weeks):
                    forecast[i] += slope * (i + 1)
                
            except Exception:
                # Fallback to simple average
                forecast = [np.mean(scores)] * forecast_weeks
            
            # Statistical measures
            performance_stats = {
                "mean": float(np.mean(scores)),
                "std": float(np.std(scores)),
                "min": float(np.min(scores)),
                "max": float(np.max(scores)),
                "median": float(np.median(scores))
            }
            
            # Get player info
            player = self.db.query(Player).filter(Player.id == player_id).first()
            
            return {
                "player_id": player_id,
                "player_name": player.name if player else "Unknown",
                "data_points": len(scores),
                "trend_analysis": {
                    "linear_slope": float(slope),
                    "trend_strength": float(abs(r_value)),
                    "trend_direction": "increasing" if slope > 0 else "decreasing" if slope < 0 else "stable",
                    "statistical_significance": float(p_value),
                    "season_trend": float(season_trend)
                },
                "performance_stats": performance_stats,
                "forecast": {
                    "weeks_ahead": forecast_weeks,
                    "predicted_scores": [float(x) for x in forecast],
                    "confidence_level": max(0.5, float(r_value ** 2))  # R-squared as proxy for confidence
                },
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error in time series analysis: {str(e)}")
            return {"error": f"Time series analysis failed: {str(e)}"}


# OPTIMIZATION MODELS (Part 2 will include lineup optimization using PuLP)