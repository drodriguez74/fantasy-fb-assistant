from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.api.deps import get_db
from app.services.enhanced_game_situation_service import EnhancedGameSituationService
from pydantic import BaseModel

router = APIRouter()

class GameSituationAnalysisRequest(BaseModel):
    player_ids: List[int]
    analysis_type: Optional[str] = "all"

class GameSituationResponse(BaseModel):
    success: bool
    analysis_type: str
    player_analyses: List[dict]
    comparison_insights: List[str]
    recommendations: List[str]

@router.post("/enhanced-analysis", response_model=GameSituationResponse)
async def analyze_enhanced_game_situations(
    request: GameSituationAnalysisRequest,
    db: Session = Depends(get_db)
):
    """
    Comprehensive enhanced game situation analysis with real NFL data integration
    
    Analysis types:
    - all: Complete analysis across all factors
    - home_away: Home vs away performance analysis
    - weather: Weather impact analysis
    - opponent: Opponent strength analysis
    - game_script: Game script and pace analysis
    - venue: Venue-specific analysis
    - prime_time: Prime time vs regular games
    - rivalry: Division rivalry games
    """
    try:
        service = EnhancedGameSituationService(db)
        result = await service.analyze_comprehensive_game_situations(
            player_ids=request.player_ids,
            analysis_type=request.analysis_type
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return GameSituationResponse(**result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@router.get("/home-away-analysis/{player_id}")
async def get_home_away_analysis(
    player_id: int,
    db: Session = Depends(get_db)
):
    """
    Get detailed home vs away analysis for a specific player
    """
    try:
        service = EnhancedGameSituationService(db)
        result = await service._enhanced_home_away_analysis(player_id)
        return {"success": True, "analysis": result}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Home/away analysis failed: {str(e)}")

@router.get("/weather-analysis/{player_id}")
async def get_weather_analysis(
    player_id: int,
    db: Session = Depends(get_db)
):
    """
    Get detailed weather impact analysis for a specific player
    """
    try:
        service = EnhancedGameSituationService(db)
        result = await service._enhanced_weather_analysis(player_id)
        return {"success": True, "analysis": result}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Weather analysis failed: {str(e)}")

@router.get("/opponent-analysis/{player_id}")
async def get_opponent_analysis(
    player_id: int,
    db: Session = Depends(get_db)
):
    """
    Get detailed opponent strength analysis for a specific player
    """
    try:
        service = EnhancedGameSituationService(db)
        result = await service._enhanced_opponent_analysis(player_id)
        return {"success": True, "analysis": result}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Opponent analysis failed: {str(e)}")

@router.get("/game-script-analysis/{player_id}")
async def get_game_script_analysis(
    player_id: int,
    db: Session = Depends(get_db)
):
    """
    Get detailed game script and pace analysis for a specific player
    """
    try:
        service = EnhancedGameSituationService(db)
        result = await service._enhanced_game_script_analysis(player_id)
        return {"success": True, "analysis": result}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Game script analysis failed: {str(e)}")

@router.get("/venue-analysis/{player_id}")
async def get_venue_analysis(
    player_id: int,
    db: Session = Depends(get_db)
):
    """
    Get detailed venue-specific analysis for a specific player
    """
    try:
        service = EnhancedGameSituationService(db)
        result = await service._enhanced_venue_analysis(player_id)
        return {"success": True, "analysis": result}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Venue analysis failed: {str(e)}")

@router.get("/prime-time-analysis/{player_id}")
async def get_prime_time_analysis(
    player_id: int,
    db: Session = Depends(get_db)
):
    """
    Get prime time vs regular game analysis for a specific player
    """
    try:
        service = EnhancedGameSituationService(db)
        result = await service._prime_time_analysis(player_id)
        return {"success": True, "analysis": result}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prime time analysis failed: {str(e)}")

@router.get("/rivalry-analysis/{player_id}")
async def get_rivalry_analysis(
    player_id: int,
    db: Session = Depends(get_db)
):
    """
    Get division rivalry game analysis for a specific player
    """
    try:
        service = EnhancedGameSituationService(db)
        result = await service._rivalry_game_analysis(player_id)
        return {"success": True, "analysis": result}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rivalry analysis failed: {str(e)}")

# Comparison endpoints
@router.post("/compare-home-away")
async def compare_home_away_performance(
    request: GameSituationAnalysisRequest,
    db: Session = Depends(get_db)
):
    """
    Compare home vs away performance across multiple players
    """
    try:
        service = EnhancedGameSituationService(db)
        results = []
        
        for player_id in request.player_ids:
            analysis = await service._enhanced_home_away_analysis(player_id)
            results.append({
                "player_id": player_id,
                "analysis": analysis
            })
        
        return {"success": True, "comparisons": results}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Home/away comparison failed: {str(e)}")

@router.post("/compare-weather-impact")
async def compare_weather_impact(
    request: GameSituationAnalysisRequest,
    db: Session = Depends(get_db)
):
    """
    Compare weather impact across multiple players
    """
    try:
        service = EnhancedGameSituationService(db)
        results = []
        
        for player_id in request.player_ids:
            analysis = await service._enhanced_weather_analysis(player_id)
            results.append({
                "player_id": player_id,
                "analysis": analysis
            })
        
        return {"success": True, "comparisons": results}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Weather comparison failed: {str(e)}")

# Data management endpoints
@router.post("/game-situations/bulk-create")
async def create_game_situations_bulk(
    game_situations: List[dict],
    db: Session = Depends(get_db)
):
    """
    Bulk create game situation records for data import
    """
    try:
        from app.models.game_situation import GameSituation
        
        created_count = 0
        for situation_data in game_situations:
            # Create new game situation record
            game_situation = GameSituation(**situation_data)
            db.add(game_situation)
            created_count += 1
        
        db.commit()
        
        return {
            "success": True,
            "created_count": created_count,
            "message": f"Successfully created {created_count} game situation records"
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Bulk creation failed: {str(e)}")

@router.get("/defensive-rankings")
async def get_defensive_rankings(
    season: Optional[int] = Query(None, description="Season year"),
    week: Optional[int] = Query(None, description="Week number"),
    team: Optional[str] = Query(None, description="Team abbreviation"),
    db: Session = Depends(get_db)
):
    """
    Get defensive rankings data with optional filters
    """
    try:
        from app.models.game_situation import DefensiveRanking
        
        query = db.query(DefensiveRanking)
        
        if season:
            query = query.filter(DefensiveRanking.season == season)
        if week:
            query = query.filter(DefensiveRanking.week == week)
        if team:
            query = query.filter(DefensiveRanking.team == team)
        
        rankings = query.all()
        
        return {
            "success": True,
            "count": len(rankings),
            "rankings": [
                {
                    "team": ranking.team,
                    "season": ranking.season,
                    "week": ranking.week,
                    "overall_def_rank": ranking.overall_def_rank,
                    "qb_fantasy_rank": ranking.qb_fantasy_rank,
                    "rb_fantasy_rank": ranking.rb_fantasy_rank,
                    "wr_fantasy_rank": ranking.wr_fantasy_rank,
                    "te_fantasy_rank": ranking.te_fantasy_rank,
                    "qb_points_allowed": ranking.qb_points_allowed,
                    "rb_points_allowed": ranking.rb_points_allowed,
                    "wr_points_allowed": ranking.wr_points_allowed,
                    "te_points_allowed": ranking.te_points_allowed
                }
                for ranking in rankings
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch defensive rankings: {str(e)}")

@router.get("/venues")
async def get_venues(
    venue_type: Optional[str] = Query(None, description="Venue type filter"),
    db: Session = Depends(get_db)
):
    """
    Get venue data with optional filters
    """
    try:
        from app.models.game_situation import VenueData
        
        query = db.query(VenueData)
        
        if venue_type:
            query = query.filter(VenueData.venue_type == venue_type)
        
        venues = query.all()
        
        return {
            "success": True,
            "count": len(venues),
            "venues": [
                {
                    "venue_name": venue.venue_name,
                    "team": venue.team,
                    "city": venue.city,
                    "state": venue.state,
                    "venue_type": venue.venue_type,
                    "capacity": venue.capacity,
                    "elevation": venue.elevation,
                    "surface_type": venue.surface_type,
                    "is_offense_friendly": venue.is_offense_friendly,
                    "historical_scoring_factor": venue.historical_scoring_factor
                }
                for venue in venues
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch venues: {str(e)}")

@router.get("/situational-trends/{player_id}")
async def get_situational_trends(
    player_id: int,
    situation_type: Optional[str] = Query(None, description="Situation type filter"),
    db: Session = Depends(get_db)
):
    """
    Get situational trends for a specific player
    """
    try:
        from app.models.game_situation import SituationalTrend
        
        query = db.query(SituationalTrend).filter(SituationalTrend.player_id == player_id)
        
        if situation_type:
            query = query.filter(SituationalTrend.situation_type == situation_type)
        
        trends = query.all()
        
        return {
            "success": True,
            "player_id": player_id,
            "count": len(trends),
            "trends": [
                {
                    "situation_type": trend.situation_type,
                    "situation_value": trend.situation_value,
                    "games_played": trend.games_played,
                    "avg_fantasy_points": trend.avg_fantasy_points,
                    "std_deviation": trend.std_deviation,
                    "boom_games": trend.boom_games,
                    "bust_games": trend.bust_games,
                    "trend_direction": trend.trend_direction,
                    "sample_size_confidence": trend.sample_size_confidence
                }
                for trend in trends
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch situational trends: {str(e)}")

# Statistics and insights endpoints
@router.get("/situation-summary")
async def get_situation_summary(
    db: Session = Depends(get_db)
):
    """
    Get overall summary of game situation data
    """
    try:
        from app.models.game_situation import GameSituation, DefensiveRanking, VenueData, SituationalTrend
        
        game_situations_count = db.query(GameSituation).count()
        defensive_rankings_count = db.query(DefensiveRanking).count()
        venues_count = db.query(VenueData).count()
        trends_count = db.query(SituationalTrend).count()
        
        # Get unique players with situation data
        unique_players = db.query(GameSituation.player_id).distinct().count()
        
        return {
            "success": True,
            "summary": {
                "total_game_situations": game_situations_count,
                "defensive_rankings": defensive_rankings_count,
                "venues": venues_count,
                "situational_trends": trends_count,
                "players_with_data": unique_players
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate summary: {str(e)}")

@router.get("/constants")
async def get_situation_constants():
    """
    Get available constants for game situation analysis
    """
    from app.models.game_situation import VENUE_TYPES, WEATHER_CONDITIONS, GAME_SCRIPTS
    
    return {
        "success": True,
        "constants": {
            "venue_types": list(VENUE_TYPES.values()),
            "weather_conditions": list(WEATHER_CONDITIONS.values()),
            "game_scripts": list(GAME_SCRIPTS.values())
        }
    }