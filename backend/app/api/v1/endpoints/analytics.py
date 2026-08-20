"""
Advanced Analytics API Endpoints

Provides access to sophisticated analytics, machine learning models,
and optimization algorithms for fantasy football.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.api.deps import get_db, get_current_active_user
from app.models.user import User
from app.services.advanced_analytics_service import AdvancedAnalyticsService
from app.services.optimization_service import OptimizationService

router = APIRouter()


# Request Models
class PlayerPredictionRequest(BaseModel):
    player_id: int
    weeks_ahead: int = 4
    model_type: str = "ensemble"  # linear, rf, gb, ensemble


class LineupOptimizationRequest(BaseModel):
    players: List[Dict[str, Any]]
    salary_cap: int = 50000
    lineup_constraints: Optional[Dict[str, int]] = None
    optimization_type: str = "maximize_points"


class MultiLineupRequest(BaseModel):
    players: List[Dict[str, Any]]
    num_lineups: int = 5
    salary_cap: int = 50000
    diversity_constraint: float = 0.7


class RosterOptimizationRequest(BaseModel):
    available_players: List[Dict[str, Any]]
    roster_constraints: Optional[Dict[str, int]] = None
    budget_constraint: Optional[int] = None
    target_weeks: int = 17


class RiskAnalysisRequest(BaseModel):
    roster_players: List[Dict[str, Any]]


# PREDICTIVE ANALYTICS ENDPOINTS

@router.post("/predict/player-performance")
async def predict_player_performance(
    request: PlayerPredictionRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Predict player performance using machine learning models"""
    try:
        analytics_service = AdvancedAnalyticsService(db)
        result = await analytics_service.predict_player_performance(
            player_id=request.player_id,
            weeks_ahead=request.weeks_ahead,
            model_type=request.model_type
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")


@router.get("/correlations/players")
async def analyze_player_correlations(
    position: Optional[str] = Query(None, description="Filter by position"),
    min_games: int = Query(10, description="Minimum games for correlation analysis"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Analyze correlations between player performances"""
    try:
        analytics_service = AdvancedAnalyticsService(db)
        result = await analytics_service.analyze_player_correlations(
            position=position,
            min_games=min_games
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Correlation analysis failed: {str(e)}")


@router.get("/clustering/players")
async def cluster_players_by_performance(
    position: Optional[str] = Query(None, description="Filter by position"),
    n_clusters: int = Query(5, description="Number of clusters"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Cluster players based on performance characteristics"""
    try:
        analytics_service = AdvancedAnalyticsService(db)
        result = await analytics_service.cluster_players_by_performance(
            position=position,
            n_clusters=n_clusters
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clustering analysis failed: {str(e)}")


@router.get("/trends/player/{player_id}")
async def analyze_performance_trends(
    player_id: int,
    forecast_weeks: int = Query(4, description="Number of weeks to forecast"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Perform time series analysis and forecasting for a player"""
    try:
        analytics_service = AdvancedAnalyticsService(db)
        result = await analytics_service.analyze_performance_trends(
            player_id=player_id,
            forecast_weeks=forecast_weeks
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Trend analysis failed: {str(e)}")


# OPTIMIZATION ENDPOINTS

@router.post("/optimize/lineup")
async def optimize_lineup(
    request: LineupOptimizationRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Optimize fantasy lineup using linear programming"""
    try:
        optimization_service = OptimizationService(db)
        result = await optimization_service.optimize_lineup(
            players=request.players,
            salary_cap=request.salary_cap,
            lineup_constraints=request.lineup_constraints,
            optimization_type=request.optimization_type
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lineup optimization failed: {str(e)}")


@router.post("/optimize/multi-lineup")
async def optimize_multi_lineup(
    request: MultiLineupRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Generate multiple optimized lineups with diversity constraints"""
    try:
        optimization_service = OptimizationService(db)
        result = await optimization_service.optimize_multi_lineup(
            players=request.players,
            num_lineups=request.num_lineups,
            salary_cap=request.salary_cap,
            diversity_constraint=request.diversity_constraint
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Multi-lineup optimization failed: {str(e)}")


@router.post("/optimize/season-roster")
async def optimize_season_roster(
    request: RosterOptimizationRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Optimize full season roster construction"""
    try:
        optimization_service = OptimizationService(db)
        result = await optimization_service.optimize_season_roster(
            available_players=request.available_players,
            roster_constraints=request.roster_constraints,
            budget_constraint=request.budget_constraint,
            target_weeks=request.target_weeks
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Season roster optimization failed: {str(e)}")


@router.post("/risk/portfolio-analysis")
async def analyze_portfolio_risk(
    request: RiskAnalysisRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Analyze risk metrics for a fantasy roster"""
    try:
        optimization_service = OptimizationService(db)
        result = await optimization_service.portfolio_risk_analysis(
            roster_players=request.roster_players
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Risk analysis failed: {str(e)}")


# ADVANCED METRICS ENDPOINTS

@router.get("/metrics/position-efficiency")
async def analyze_position_efficiency(
    position: str = Query(..., description="Position to analyze"),
    season: Optional[int] = Query(None, description="Season to analyze"),
    min_games: int = Query(8, description="Minimum games played"),
    db: Session = Depends(get_db)
):
    """Analyze efficiency metrics by position"""
    try:
        from app.models.historical_performance import PlayerSeasonSummary
        from app.models.player import Player
        from sqlalchemy import func
        
        # Get position data
        query = db.query(PlayerSeasonSummary).join(Player).filter(
            Player.position == position.upper(),
            PlayerSeasonSummary.games_played >= min_games
        )
        
        if season:
            query = query.filter(PlayerSeasonSummary.season == season)
        
        summaries = query.all()
        
        if not summaries:
            raise HTTPException(status_code=404, detail="No data found for the specified criteria")
        
        # Calculate efficiency metrics
        efficiency_data = []
        for summary in summaries:
            player = db.query(Player).filter(Player.id == summary.player_id).first()
            
            efficiency_data.append({
                "player_id": summary.player_id,
                "player_name": player.name if player else "Unknown",
                "season": summary.season,
                "games_played": summary.games_played,
                "points_per_game": summary.avg_fantasy_points_ppr,
                "consistency_score": summary.consistency_score,
                "ceiling": summary.weekly_ceiling,
                "floor": summary.weekly_floor,
                "efficiency_rating": (summary.avg_fantasy_points_ppr or 0) * (summary.consistency_score or 0)
            })
        
        # Calculate position benchmarks
        avg_ppg = np.mean([d["points_per_game"] or 0 for d in efficiency_data])
        avg_consistency = np.mean([d["consistency_score"] or 0 for d in efficiency_data])
        
        # Rank players
        efficiency_data.sort(key=lambda x: x["efficiency_rating"], reverse=True)
        
        return {
            "position": position.upper(),
            "season": season,
            "total_players": len(efficiency_data),
            "position_benchmarks": {
                "avg_points_per_game": avg_ppg,
                "avg_consistency": avg_consistency
            },
            "top_performers": efficiency_data[:10],
            "all_players": efficiency_data,
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Position efficiency analysis failed: {str(e)}")


@router.get("/metrics/matchup-analysis")
async def analyze_matchup_metrics(
    team_a: str = Query(..., description="First team abbreviation"),
    team_b: str = Query(..., description="Second team abbreviation"),
    seasons: int = Query(3, description="Number of seasons to analyze"),
    db: Session = Depends(get_db)
):
    """Analyze head-to-head matchup metrics and trends"""
    try:
        from app.models.historical_performance import MatchupHistory
        from sqlalchemy import or_, and_
        from datetime import datetime
        
        current_year = datetime.now().year
        season_range = list(range(current_year - seasons + 1, current_year + 1))
        
        # Get matchup history
        matchups = db.query(MatchupHistory).filter(
            and_(
                or_(
                    and_(MatchupHistory.team_a == team_a.upper(), MatchupHistory.team_b == team_b.upper()),
                    and_(MatchupHistory.team_a == team_b.upper(), MatchupHistory.team_b == team_a.upper())
                ),
                MatchupHistory.season.in_(season_range)
            )
        ).order_by(MatchupHistory.season.desc(), MatchupHistory.week.desc()).all()
        
        if not matchups:
            raise HTTPException(status_code=404, detail="No matchup data found")
        
        # Analyze trends
        total_points_history = [m.total_points for m in matchups if m.total_points]
        
        # Calculate advanced metrics
        matchup_analysis = {
            "teams": [team_a.upper(), team_b.upper()],
            "seasons_analyzed": seasons,
            "total_games": len(matchups),
            "scoring_trends": {
                "avg_total_points": np.mean(total_points_history) if total_points_history else 0,
                "total_points_trend": "increasing" if len(total_points_history) > 1 and 
                                    np.polyfit(range(len(total_points_history)), total_points_history, 1)[0] > 0 else "decreasing",
                "scoring_variance": np.var(total_points_history) if total_points_history else 0
            },
            "game_conditions": {
                "dome_games": len([m for m in matchups if m.dome_game]),
                "outdoor_games": len([m for m in matchups if not m.dome_game])
            },
            "fantasy_impact": self._analyze_fantasy_impact(matchups),
            "recent_games": [
                {
                    "season": m.season,
                    "week": m.week,
                    "total_points": m.total_points,
                    "game_script": m.game_script,
                    "weather": m.weather
                }
                for m in matchups[:5]  # Last 5 games
            ]
        }
        
        return matchup_analysis
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Matchup analysis failed: {str(e)}")


def _analyze_fantasy_impact(matchups):
    """Analyze fantasy point impact of matchups"""
    if not matchups:
        return {}
    
    # Calculate position-specific trends
    positions = ['QB', 'RB', 'WR', 'TE']
    fantasy_impact = {}
    
    for pos in positions:
        team_a_allowed = [getattr(m, f"{pos.lower()}_fantasy_allowed_a") for m in matchups 
                         if getattr(m, f"{pos.lower()}_fantasy_allowed_a") is not None]
        team_b_allowed = [getattr(m, f"{pos.lower()}_fantasy_allowed_b") for m in matchups 
                         if getattr(m, f"{pos.lower()}_fantasy_allowed_b") is not None]
        
        if team_a_allowed or team_b_allowed:
            fantasy_impact[pos] = {
                "avg_allowed": np.mean(team_a_allowed + team_b_allowed),
                "trend": "defense_improving" if len(team_a_allowed + team_b_allowed) > 1 and 
                        np.polyfit(range(len(team_a_allowed + team_b_allowed)), 
                                 team_a_allowed + team_b_allowed, 1)[0] < 0 else "defense_declining"
            }
    
    return fantasy_impact


# VISUALIZATION DATA ENDPOINTS

@router.get("/visualization/correlation-matrix")
async def get_correlation_matrix_data(
    position: Optional[str] = Query(None, description="Filter by position"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get correlation matrix data for visualization"""
    try:
        analytics_service = AdvancedAnalyticsService(db)
        correlation_data = await analytics_service.analyze_player_correlations(
            position=position,
            min_games=8
        )
        
        if "error" in correlation_data:
            raise HTTPException(status_code=400, detail=correlation_data["error"])
        
        # Format for visualization
        correlations = correlation_data.get("strong_correlations", [])
        
        # Create matrix format for heatmap
        players = list(set([c["player1_name"] for c in correlations] + 
                          [c["player2_name"] for c in correlations]))
        
        matrix_data = {
            "players": players,
            "correlations": correlations,
            "matrix_size": len(players),
            "visualization_type": "heatmap"
        }
        
        return matrix_data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Visualization data generation failed: {str(e)}")


@router.get("/visualization/performance-clusters")
async def get_performance_cluster_data(
    position: Optional[str] = Query(None, description="Filter by position"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get performance cluster data for visualization"""
    try:
        analytics_service = AdvancedAnalyticsService(db)
        cluster_data = await analytics_service.cluster_players_by_performance(
            position=position,
            n_clusters=5
        )
        
        if "error" in cluster_data:
            raise HTTPException(status_code=400, detail=cluster_data["error"])
        
        # Format for scatter plot visualization
        visualization_data = {
            "clusters": cluster_data.get("clusters", {}),
            "feature_names": cluster_data.get("feature_names", []),
            "visualization_type": "scatter",
            "axes": {
                "x": "avg_points",
                "y": "consistency",
                "size": "ceiling",
                "color": "cluster_id"
            }
        }
        
        return visualization_data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cluster visualization data generation failed: {str(e)}")


import numpy as np
from datetime import datetime