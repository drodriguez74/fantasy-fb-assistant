"""
League Scoring Configuration API Endpoints

Manages custom scoring settings, bonuses, and league-specific rules.
"""

import logging

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
from app.models.player import Player
from app.services.scoring_calculation_service import ScoringCalculationService
from app.services.scoring_rules import describe_scoring_rules
from app.services.espn_service_enhanced import espn_service_enhanced
from app.services.sleeper_service import sleeper_service

logger = logging.getLogger(__name__)

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

        # Real, live-detected roster construction (starters/bench/roster
        # size) for this league -- independent of whether a manual scoring
        # override exists below, since LeagueScoring only ever covers point
        # values, never roster slot counts. Best-effort: a platform without
        # real detection support yet (or a live API hiccup) just omits this
        # rather than failing the whole endpoint or fabricating numbers.
        roster_settings = None
        try:
            platform = user_league.platform.value.upper()
            if platform == "ESPN":
                settings_result = await espn_service_enhanced.get_scoring_and_roster_settings(
                    league_id=user_league.league_id,
                    season=user_league.season,
                    swid=user_league.espn_swid,
                    espn_s2=user_league.espn_s2
                )
                if "error" not in settings_result:
                    roster_settings = {
                        "starters": settings_result.get("starters"),
                        "bench": settings_result.get("bench"),
                        "roster_size": settings_result.get("roster_size"),
                        "points_per_reception": settings_result.get("points_per_reception"),
                        "scoring_type": settings_result.get("scoring_type"),
                        "source": settings_result.get("source"),
                    }
            elif platform == "SLEEPER":
                league_info = await sleeper_service.get_league_info(user_league.league_id)
                parsed = sleeper_service.parse_league_settings(league_info)
                if "error" not in parsed:
                    roster_settings = {
                        "starters": parsed.get("starters"),
                        "bench": parsed.get("bench"),
                        "roster_size": parsed.get("roster_size"),
                        "points_per_reception": parsed.get("points_per_reception"),
                        "scoring_type": None,
                        "source": "sleeper",
                    }
        except Exception as roster_err:
            logger.warning(f"Roster-settings auto-detection failed for league {league_id}: {roster_err}")

        if not scoring_config:
            # No manual override -- try to surface this league's real,
            # auto-detected scoring rules (the same extraction
            # draft_assistant_service.py already uses to generate real
            # recommendations) instead of only naming a generic fallback
            # format. Best-effort: a platform without real detection
            # support yet (or a live API hiccup) just omits detected_scoring
            # rather than failing this endpoint or fabricating numbers.
            detected_scoring = None
            try:
                platform = user_league.platform.value.upper()
                if platform == "ESPN":
                    settings_result = await espn_service_enhanced.get_scoring_and_roster_settings(
                        league_id=user_league.league_id,
                        season=user_league.season,
                        swid=user_league.espn_swid,
                        espn_s2=user_league.espn_s2
                    )
                    if "error" not in settings_result:
                        detected_scoring = settings_result.get("scoring_rules")
                elif platform == "SLEEPER":
                    league_info = await sleeper_service.get_league_info(user_league.league_id)
                    parsed = sleeper_service.parse_league_settings(league_info)
                    if "error" not in parsed:
                        detected_scoring = parsed.get("scoring_rules")
            except Exception as detect_err:
                logger.warning(f"Scoring auto-detection failed for league {league_id}: {detect_err}")

            return {
                "has_custom_scoring": False,
                "league_id": league_id,
                "default_scoring": user_league.scoring_format or "PPR",
                "detected_scoring": detected_scoring,
                "detected_scoring_description": describe_scoring_rules(detected_scoring) if detected_scoring else None,
                "roster_settings": roster_settings,
            }

        return {
            "has_custom_scoring": True,
            "league_id": league_id,
            "roster_settings": roster_settings,
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
        # IDOR fix: this endpoint used to require auth via current_user but
        # never checked that scoring_config_ids actually belonged to that
        # user, so any authenticated user could pass another user's
        # LeagueScoring ids and see their comparison data. Verify every
        # requested id resolves to a LeagueScoring row owned (via
        # UserLeague.user_id) by the requesting user before running anything.
        owned_config_ids = {
            row[0]
            for row in db.query(LeagueScoring.id)
            .join(UserLeague, LeagueScoring.user_league_id == UserLeague.id)
            .filter(
                LeagueScoring.id.in_(scoring_config_ids),
                UserLeague.user_id == current_user.id,
            )
            .all()
        }
        unauthorized_ids = set(scoring_config_ids) - owned_config_ids
        if unauthorized_ids:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Scoring config(s) not found or not owned by user: "
                    f"{sorted(unauthorized_ids)}"
                ),
            )

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

    except HTTPException:
        # Don't let the ownership-check 403 above get swallowed and
        # rewritten into a 500 by the generic handler below.
        raise
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