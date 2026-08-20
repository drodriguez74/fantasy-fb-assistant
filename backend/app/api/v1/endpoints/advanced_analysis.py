from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.api.deps import get_db, get_current_active_user
from app.models.user import User
from app.services.advanced_analysis_service import AdvancedAnalysisService

router = APIRouter()

class PlayerComparisonRequest(BaseModel):
    player_ids: List[int]
    metrics: Optional[List[str]] = None

class ScheduleAnalysisRequest(BaseModel):
    player_ids: List[int]
    weeks_ahead: Optional[int] = 4

class BreakoutCandidatesRequest(BaseModel):
    position: Optional[str] = None
    min_ownership: Optional[float] = 0.0
    max_ownership: Optional[float] = 50.0

class GameSituationRequest(BaseModel):
    player_ids: List[int]

@router.post("/compare-players")
async def compare_players(
    request: PlayerComparisonRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Compare multiple players across various metrics and generate insights
    """
    try:
        analysis_service = AdvancedAnalysisService(db)
        
        if len(request.player_ids) < 2:
            raise HTTPException(status_code=400, detail="At least 2 players required for comparison")
        
        if len(request.player_ids) > 5:
            raise HTTPException(status_code=400, detail="Maximum 5 players allowed for comparison")
        
        result = await analysis_service.compare_players(
            player_ids=request.player_ids,
            metrics=request.metrics
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Player comparison failed: {str(e)}")

@router.post("/strength-of-schedule")
async def analyze_strength_of_schedule(
    request: ScheduleAnalysisRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Analyze strength of schedule for players over upcoming weeks
    """
    try:
        analysis_service = AdvancedAnalysisService(db)
        
        if not request.player_ids:
            raise HTTPException(status_code=400, detail="At least 1 player required for schedule analysis")
        
        if len(request.player_ids) > 10:
            raise HTTPException(status_code=400, detail="Maximum 10 players allowed for schedule analysis")
        
        if request.weeks_ahead < 1 or request.weeks_ahead > 8:
            raise HTTPException(status_code=400, detail="Weeks ahead must be between 1 and 8")
        
        result = await analysis_service.analyze_strength_of_schedule(
            player_ids=request.player_ids,
            weeks_ahead=request.weeks_ahead
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Strength of schedule analysis failed: {str(e)}")

@router.post("/breakout-candidates")
async def detect_breakout_candidates(
    request: BreakoutCandidatesRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Detect potential breakout candidates using ML and statistical analysis
    """
    try:
        analysis_service = AdvancedAnalysisService(db)
        
        if request.min_ownership < 0 or request.min_ownership > 100:
            raise HTTPException(status_code=400, detail="Min ownership must be between 0 and 100")
        
        if request.max_ownership < 0 or request.max_ownership > 100:
            raise HTTPException(status_code=400, detail="Max ownership must be between 0 and 100")
        
        if request.min_ownership >= request.max_ownership:
            raise HTTPException(status_code=400, detail="Min ownership must be less than max ownership")
        
        result = await analysis_service.detect_breakout_candidates(
            position=request.position,
            min_ownership=request.min_ownership,
            max_ownership=request.max_ownership
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Breakout candidate detection failed: {str(e)}")

@router.post("/game-situations")
async def analyze_game_situations(
    request: GameSituationRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Analyze player performance in various game situations
    """
    try:
        analysis_service = AdvancedAnalysisService(db)
        
        if not request.player_ids:
            raise HTTPException(status_code=400, detail="At least 1 player required for situation analysis")
        
        if len(request.player_ids) > 8:
            raise HTTPException(status_code=400, detail="Maximum 8 players allowed for situation analysis")
        
        result = await analysis_service.analyze_game_situations(
            player_ids=request.player_ids
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Game situation analysis failed: {str(e)}")

@router.get("/player-suggestions")
async def get_player_suggestions(
    query: str = Query(..., description="Player name search query"),
    position: Optional[str] = Query(None, description="Filter by position"),
    limit: int = Query(10, description="Maximum number of suggestions"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get player suggestions for analysis tools
    """
    try:
        from app.models.player import Player
        from sqlalchemy import or_
        
        # Build query
        query_filter = Player.name.ilike(f"%{query}%")
        
        db_query = db.query(Player).filter(query_filter)
        
        if position and position != "ALL":
            db_query = db_query.filter(Player.position == position)
        
        # Order by relevance (projected points, ownership, etc.)
        players = db_query.order_by(
            Player.projected_points.desc().nullslast(),
            Player.name
        ).limit(limit).all()
        
        suggestions = []
        for player in players:
            suggestions.append({
                "id": player.id,
                "name": player.name,
                "position": player.position.value if player.position else None,
                "team": player.team,
                "projected_points": player.projected_points,
                "ownership_percentage": player.ownership_percentage
            })
        
        return {
            "suggestions": suggestions,
            "total": len(suggestions)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Player suggestions failed: {str(e)}")

@router.get("/analysis-summary")
async def get_analysis_summary(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get summary statistics for the advanced analysis system
    """
    try:
        from app.models.player import Player
        
        # Get basic stats
        total_players = db.query(Player).count()
        qb_count = db.query(Player).filter(Player.position == "QB").count()
        rb_count = db.query(Player).filter(Player.position == "RB").count()
        wr_count = db.query(Player).filter(Player.position == "WR").count()
        te_count = db.query(Player).filter(Player.position == "TE").count()
        
        # Get players with projected points
        players_with_projections = db.query(Player).filter(Player.projected_points.isnot(None)).count()
        
        # Get trending players
        trending_up = db.query(Player).filter(Player.trending_direction == "UP").count()
        trending_down = db.query(Player).filter(Player.trending_direction == "DOWN").count()
        
        return {
            "database_stats": {
                "total_players": total_players,
                "position_breakdown": {
                    "QB": qb_count,
                    "RB": rb_count,
                    "WR": wr_count,
                    "TE": te_count
                },
                "players_with_projections": players_with_projections,
                "trending_players": {
                    "up": trending_up,
                    "down": trending_down
                }
            },
            "analysis_capabilities": {
                "player_comparison": "Compare up to 5 players across multiple metrics",
                "schedule_analysis": "Analyze strength of schedule for upcoming weeks",
                "breakout_detection": "ML-powered breakout candidate identification",
                "situational_analysis": "Performance analysis across game situations"
            },
            "last_updated": "Real-time data analysis available"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis summary failed: {str(e)}")

@router.get("/metrics-available")
async def get_available_metrics(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get list of available metrics for player comparison
    """
    try:
        metrics = {
            "basic_metrics": [
                {"key": "projected_points", "name": "Projected Points", "description": "Season projected fantasy points"},
                {"key": "consistency_rating", "name": "Consistency Rating", "description": "Performance consistency (0-10)"},
                {"key": "ceiling_score", "name": "Ceiling Score", "description": "Highest potential weekly score"},
                {"key": "floor_score", "name": "Floor Score", "description": "Lowest expected weekly score"}
            ],
            "usage_metrics": [
                {"key": "target_share", "name": "Target Share", "description": "Percentage of team targets"},
                {"key": "snap_count_percentage", "name": "Snap Count %", "description": "Percentage of offensive snaps"},
                {"key": "depth_chart_order", "name": "Depth Chart Order", "description": "Position on team depth chart"}
            ],
            "trend_metrics": [
                {"key": "trending_count", "name": "Trending Count", "description": "Social media trending mentions"},
                {"key": "ownership_percentage", "name": "Ownership %", "description": "Fantasy league ownership percentage"},
                {"key": "trending_direction", "name": "Trending Direction", "description": "UP, DOWN, or STABLE trend"}
            ],
            "risk_metrics": [
                {"key": "injury_status", "name": "Injury Status", "description": "Current injury designation"},
                {"key": "age", "name": "Age", "description": "Player age"},
                {"key": "years_exp", "name": "Experience", "description": "Years of NFL experience"}
            ]
        }
        
        return {
            "available_metrics": metrics,
            "total_metrics": sum(len(category) for category in metrics.values()),
            "default_comparison_metrics": [
                "projected_points", "consistency_rating", "ceiling_score", 
                "floor_score", "target_share", "snap_count_percentage"
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Metrics retrieval failed: {str(e)}")