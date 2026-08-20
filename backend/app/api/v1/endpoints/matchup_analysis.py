"""
Matchup Analysis API Endpoints

Provides live matchup analysis, defensive streaming recommendations,
and opponent-specific insights for fantasy decisions.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional

from app.api.deps import get_db, get_current_active_user
from app.models.user import User
from app.models.player import Player
from app.services.matchup_analysis_service import MatchupAnalysisService
from app.services.waiver_wire_service import WaiverWireService

router = APIRouter()


@router.get("/defense-streaming/{week}")
async def get_defensive_streaming_targets(
    week: int,
    current_defense: Optional[str] = Query(None, description="Current defense team abbreviation"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get this week's best defensive streaming targets with matchup analysis"""
    try:
        waiver_service = WaiverWireService(db)
        
        streaming_recommendations = await waiver_service.get_matchup_driven_defense_recommendations(
            current_defense, week
        )
        
        return {
            "success": True,
            "week": week,
            "current_defense": current_defense,
            "recommendations": streaming_recommendations
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get defensive streaming targets: {str(e)}"
        )


@router.get("/player-matchups/{player_id}")
async def get_player_upcoming_matchups(
    player_id: int,
    weeks_ahead: int = Query(3, description="Number of weeks to analyze"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Analyze a player's upcoming matchups for fantasy planning"""
    try:
        player = db.query(Player).filter(Player.id == player_id).first()
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")
        
        matchup_service = MatchupAnalysisService(db)
        matchup_analysis = matchup_service.analyze_player_upcoming_matchups(player, weeks_ahead)
        
        return {
            "success": True,
            "player_analysis": matchup_analysis
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze player matchups: {str(e)}"
        )


@router.post("/roster-matchup-analysis")
async def analyze_roster_matchups(
    roster_data: Dict[str, Any],
    week: Optional[int] = Query(None, description="Week to analyze (default: current week)"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get matchup-driven recommendations for entire roster"""
    try:
        user_roster = roster_data.get("roster", [])
        if not user_roster:
            raise HTTPException(status_code=400, detail="Roster data is required")
        
        waiver_service = WaiverWireService(db)
        
        matchup_recommendations = await waiver_service.get_roster_specific_matchup_recommendations(
            user_roster, week
        )
        
        return {
            "success": True,
            "roster_matchup_analysis": matchup_recommendations
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze roster matchups: {str(e)}"
        )


@router.get("/position-outlook/{position}")
async def get_position_matchup_outlook(
    position: str,
    weeks_ahead: int = Query(4, description="Number of weeks to analyze"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get overall matchup outlook for a position across multiple weeks"""
    try:
        # Validate position
        valid_positions = ["QB", "RB", "WR", "TE", "K", "DEF"]
        if position.upper() not in valid_positions:
            raise HTTPException(status_code=400, detail=f"Invalid position. Must be one of: {valid_positions}")
        
        matchup_service = MatchupAnalysisService(db)
        outlook = matchup_service.get_position_matchup_outlook(position.upper(), weeks_ahead)
        
        return {
            "success": True,
            "position_outlook": outlook
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get position outlook: {str(e)}"
        )


@router.get("/player-vs-defense/{player_id}/{opponent_team}")
async def get_player_vs_defense_history(
    player_id: int,
    opponent_team: str,
    last_n_games: int = Query(5, description="Number of recent games to analyze"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get player's historical performance vs specific defense"""
    try:
        player = db.query(Player).filter(Player.id == player_id).first()
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")
        
        matchup_service = MatchupAnalysisService(db)
        history = matchup_service.get_player_vs_defense_history(player, opponent_team.upper(), last_n_games)
        
        return {
            "success": True,
            "matchup_history": history
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get player vs defense history: {str(e)}"
        )


@router.get("/current-week")
async def get_current_nfl_week(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get the current NFL week for matchup analysis"""
    try:
        matchup_service = MatchupAnalysisService(db)
        current_week = matchup_service.get_current_week()
        
        return {
            "success": True,
            "current_week": current_week,
            "season": 2024
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to determine current week: {str(e)}"
        )