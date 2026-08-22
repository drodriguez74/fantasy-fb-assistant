"""
League Scoring Configuration API Endpoints

Manages custom scoring settings, bonuses, and league-specific rules.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from app.api.deps import get_db, get_current_active_user
from app.models.user import User
from app.models.league_scoring import LeagueScoring, ScoringPreset
from app.models.player import Player
from app.models.user_league import UserLeague
from app.services.scoring_calculation_service import ScoringCalculationService

router = APIRouter()


class ScoringConfigRequest(BaseModel):
    user_league_id: int
    scoring_type: str = "PPR"
    
    # Passing
    passing_yards_per_point: float = 25.0
    passing_td_points: float = 4.0
    passing_int_points: float = -1.0
    passing_300_yard_bonus: float = 0.0
    passing_400_yard_bonus: float = 0.0
    # Real, independent completion-accuracy scoring (see
    # app.services.scoring_rules's module docstring -- some real leagues
    # reward accurate/efficient QBs with e.g. +0.5 per completion, -0.5 per
    # incompletion, distinct from PPR-style volume scoring). Present on the
    # LeagueScoring DB model since this feature was first built, but never
    # exposed on this request model until now -- without these two fields,
    # a completion-accuracy league could never actually be configured
    # through this endpoint, only through the DB directly.
    completion_points: float = 0.0
    incompletion_points: float = 0.0
    
    # Rushing
    rushing_yards_per_point: float = 10.0
    rushing_td_points: float = 6.0
    rushing_100_yard_bonus: float = 0.0
    rushing_200_yard_bonus: float = 0.0
    
    # Receiving
    receiving_yards_per_point: float = 10.0
    receiving_td_points: float = 6.0
    reception_points: float = 1.0
    receiving_100_yard_bonus: float = 0.0
    receiving_200_yard_bonus: float = 0.0
    
    # Kicking
    fg_0_39_points: float = 3.0
    fg_40_49_points: float = 4.0
    fg_50_plus_points: float = 5.0
    extra_point_points: float = 1.0
    
    # Defense
    def_sack_points: float = 1.0
    def_int_points: float = 2.0
    def_fumble_rec_points: float = 2.0
    def_td_points: float = 6.0
    def_0_points_allowed: float = 10.0
    def_1_6_points_allowed: float = 7.0
    def_7_13_points_allowed: float = 4.0
    
    # Penalties
    fumble_lost_points: float = -2.0
    
    # Advanced
    target_points: float = 0.0
    carry_points: float = 0.0
    
    # Custom rules
    custom_scoring_rules: Optional[Dict[str, Any]] = None


@router.post("/configure")
async def configure_league_scoring(
    config: ScoringConfigRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Configure or update scoring settings for a user's league
    """
    try:
        # Verify user owns this league
        user_league = db.query(UserLeague).filter(
            and_(
                UserLeague.id == config.user_league_id,
                UserLeague.user_id == current_user.id
            )
        ).first()
        
        if not user_league:
            raise HTTPException(status_code=404, detail="League not found or not owned by user")
        
        # Check if scoring config already exists
        existing_config = db.query(LeagueScoring).filter(
            LeagueScoring.user_league_id == config.user_league_id
        ).first()
        
        if existing_config:
            # Update existing configuration
            for field, value in config.dict().items():
                if field != 'user_league_id' and hasattr(existing_config, field):
                    setattr(existing_config, field, value)
            scoring_config = existing_config
        else:
            # Create new configuration
            scoring_config = LeagueScoring(**config.dict())
            db.add(scoring_config)
        
        db.commit()
        db.refresh(scoring_config)
        
        # Recalculate points for this league
        scoring_service = ScoringCalculationService(db)
        recalc_result = scoring_service.recalculate_player_points_for_league(
            scoring_config.id
        )
        
        return {
            "success": True,
            "scoring_config_id": scoring_config.id,
            "recalculation_result": recalc_result,
            "message": "League scoring configured successfully"
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to configure scoring: {str(e)}"
        )


@router.get("/presets")
async def get_scoring_presets(db: Session = Depends(get_db)):
    """Get available scoring presets (ESPN, Yahoo, Sleeper defaults)"""
    try:
        scoring_service = ScoringCalculationService(db)
        
        # Ensure default presets exist
        scoring_service.create_default_presets()
        
        presets = db.query(ScoringPreset).filter(
            ScoringPreset.is_default == True
        ).order_by(ScoringPreset.popularity_rank).all()
        
        return {
            "success": True,
            "presets": [
                {
                    "id": preset.id,
                    "name": preset.name,
                    "description": preset.description,
                    "scoring_type": preset.scoring_type.value,
                    "settings": preset.scoring_settings
                }
                for preset in presets
            ]
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load presets: {str(e)}"
        )


@router.get("/league/{league_id}")
async def get_league_scoring(
    league_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get scoring configuration for a specific league"""
    try:
        # Verify user owns this league
        user_league = db.query(UserLeague).filter(
            and_(
                UserLeague.id == league_id,
                UserLeague.user_id == current_user.id
            )
        ).first()
        
        if not user_league:
            raise HTTPException(status_code=404, detail="League not found")
        
        scoring_config = db.query(LeagueScoring).filter(
            LeagueScoring.user_league_id == league_id
        ).first()
        
        if not scoring_config:
            return {
                "has_custom_scoring": False,
                "league_id": league_id,
                "default_scoring": user_league.scoring_format or "PPR"
            }
        
        return {
            "has_custom_scoring": True,
            "league_id": league_id,
            "scoring_config": {
                "id": scoring_config.id,
                "scoring_type": scoring_config.scoring_type.value,
                "passing_settings": {
                    "yards_per_point": scoring_config.passing_yards_per_point,
                    "td_points": scoring_config.passing_td_points,
                    "int_points": scoring_config.passing_int_points,
                    # Real, independent completion-accuracy scoring (see
                    # ScoringConfigRequest.completion_points/incompletion_points
                    # above, and app.services.scoring_rules's module
                    # docstring) -- omitted here before this pass, which
                    # meant a caller could configure these via POST
                    # /configure but never see them come back from GET.
                    "completion_points": scoring_config.completion_points,
                    "incompletion_points": scoring_config.incompletion_points,
                    "bonuses": {
                        "300_yards": scoring_config.passing_300_yard_bonus,
                        "400_yards": scoring_config.passing_400_yard_bonus
                    }
                },
                "rushing_settings": {
                    "yards_per_point": scoring_config.rushing_yards_per_point,
                    "td_points": scoring_config.rushing_td_points,
                    "bonuses": {
                        "100_yards": scoring_config.rushing_100_yard_bonus,
                        "200_yards": scoring_config.rushing_200_yard_bonus
                    }
                },
                "receiving_settings": {
                    "yards_per_point": scoring_config.receiving_yards_per_point,
                    "td_points": scoring_config.receiving_td_points,
                    "reception_points": scoring_config.reception_points,
                    "target_points": scoring_config.target_points,
                    "bonuses": {
                        "100_yards": scoring_config.receiving_100_yard_bonus,
                        "200_yards": scoring_config.receiving_200_yard_bonus
                    }
                },
                "fumble_lost_points": scoring_config.fumble_lost_points
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get league scoring: {str(e)}"
        )


@router.post("/compare-players")
async def compare_players_scoring_systems(
    player_ids: List[int],
    scoring_config_ids: List[int],
    season: int = Query(2024),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Compare how players perform under different scoring systems
    """
    try:
        scoring_service = ScoringCalculationService(db)
        
        comparisons = {}
        
        for player_id in player_ids:
            player = db.query(Player).filter(Player.id == player_id).first()
            if not player:
                continue
            
            player_comparison = scoring_service.compare_scoring_systems(
                player_id, scoring_config_ids, season
            )
            
            if "error" not in player_comparison:
                comparisons[player.name] = player_comparison
        
        return {
            "success": True,
            "season": season,
            "players_compared": len(comparisons),
            "scoring_systems_compared": len(scoring_config_ids),
            "comparisons": comparisons
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to compare scoring systems: {str(e)}"
        )


@router.get("/analysis/{league_id}")
async def analyze_league_scoring_impact(
    league_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Analyze how the league's scoring system affects player values
    """
    try:
        # Get league scoring config
        user_league = db.query(UserLeague).filter(
            and_(
                UserLeague.id == league_id,
                UserLeague.user_id == current_user.id
            )
        ).first()
        
        if not user_league:
            raise HTTPException(status_code=404, detail="League not found")
        
        scoring_config = db.query(LeagueScoring).filter(
            LeagueScoring.user_league_id == league_id
        ).first()
        
        if not scoring_config:
            return {
                "message": "No custom scoring configured. Using standard analysis.",
                "default_scoring": user_league.scoring_format or "PPR"
            }
        
        scoring_service = ScoringCalculationService(db)
        impact_analysis = scoring_service.get_league_scoring_impact(scoring_config.id)
        
        return {
            "success": True,
            "league_id": league_id,
            "league_name": user_league.league_name,
            "scoring_analysis": impact_analysis
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze scoring impact: {str(e)}"
        )