"""
Post-Draft Analysis API Endpoints

Provides roster evaluation and personalized waiver wire recommendations.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from datetime import datetime

from app.api.deps import get_db, get_current_active_user
from app.models.user import User
from app.models.player import Player
from app.services.post_draft_analysis_service import PostDraftAnalysisService
from app.services.sleeper_service import SleeperService
from app.services.espn_service_enhanced import espn_service_enhanced
from app.services.yahoo_service import yahoo_service
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter()


class RosterPlayer(BaseModel):
    player_id: Optional[int] = None
    player_name: str
    position: str
    team: str
    round: Optional[int] = None
    pick: Optional[int] = None


class RosterAnalysisRequest(BaseModel):
    roster: List[RosterPlayer]
    league_settings: Dict[str, Any] = {}


@router.post("/analyze-roster")
async def analyze_roster(
    request: RosterAnalysisRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Comprehensive post-draft roster analysis

    Analyzes roster composition, player values, strengths/weaknesses,
    and provides improvement recommendations.
    """
    try:
        service = PostDraftAnalysisService(db)

        # Convert request to format expected by service
        roster_data = []
        for player in request.roster:
            roster_data.append({
                'player_id': player.player_id,
                'player_name': player.player_name,
                'position': player.position,
                'team': player.team,
                'round': player.round,
                'pick': player.pick
            })

        analysis = await service.analyze_roster_comprehensive(
            user_roster=roster_data,
            league_settings=request.league_settings
        )

        if "error" in analysis:
            raise HTTPException(status_code=400, detail=analysis["error"])

        return {
            "success": True,
            "analysis": analysis,
            "user_id": current_user.id
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze roster: {str(e)}"
        )


@router.post("/personalized-waivers")
async def get_personalized_waiver_targets(
    request: RosterAnalysisRequest,
    week: int = Query(1, ge=1, le=18),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get personalized waiver wire recommendations based on roster composition

    Analyzes current roster and recommends waiver targets that address
    specific positional needs and weaknesses.
    """
    try:
        service = PostDraftAnalysisService(db)

        # Convert request format
        roster_data = []
        for player in request.roster:
            roster_data.append({
                'player_id': player.player_id,
                'player_name': player.player_name,
                'position': player.position,
                'team': player.team,
                'round': player.round,
                'pick': player.pick
            })

        targets = await service.get_personalized_waiver_targets(
            user_roster=roster_data,
            week=week
        )

        if "error" in targets:
            raise HTTPException(status_code=400, detail=targets["error"])

        return {
            "success": True,
            "week": week,
            "personalized_recommendations": targets,
            "user_id": current_user.id
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate personalized waiver targets: {str(e)}"
        )


@router.get("/import-roster/{league_id}")
async def import_roster_from_league(
    league_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Import the current user's roster from one of their connected leagues for
    post-draft analysis. `league_id` is the UserLeague row id (scoped to the
    requesting user), not a raw platform league id.

    Real data only: each platform branch calls the actual platform service.
    If a real fetch genuinely isn't possible (no team_id configured yet, no
    matching roster found, or the platform isn't wired up), this returns an
    honest error rather than fabricated roster data.
    """
    user_service = UserService(db)
    user_league = user_service.get_user_league(current_user.id, league_id)

    if not user_league:
        raise HTTPException(status_code=404, detail="League not found")

    platform = user_league.platform.value.upper()

    try:
        if platform == "ESPN":
            if not user_league.team_id:
                raise HTTPException(
                    status_code=400,
                    detail="Team ID not set for this ESPN league. Set it via PUT /leagues/{league_id}/settings first."
                )

            roster_data = await espn_service_enhanced.get_team_roster(
                league_id=user_league.league_id,
                team_id=int(user_league.team_id),
                season=user_league.season,
                swid=user_league.espn_swid,
                espn_s2=user_league.espn_s2
            )

            if "error" in roster_data:
                raise HTTPException(status_code=400, detail=roster_data["error"])

            roster = [
                {
                    "player_id": None,
                    "player_name": p.get("name", "Unknown Player"),
                    "position": p.get("position", "UNKNOWN"),
                    "team": p.get("team", "FA"),
                    "round": None,
                    "pick": None
                }
                for p in roster_data.get("players", [])
            ]
            team_info = {
                "team_id": roster_data.get("team_id", user_league.team_id),
                "team_name": roster_data.get("team_name", "Your Team"),
                "owner": roster_data.get("owner", "You")
            }

        elif platform == "YAHOO":
            if not user_league.team_id:
                raise HTTPException(
                    status_code=400,
                    detail="Team ID not set for this Yahoo league. Set it via PUT /leagues/{league_id}/settings first."
                )

            roster_data = await yahoo_service.get_team_roster(user_league.team_id)

            if "error" in roster_data:
                raise HTTPException(status_code=400, detail=roster_data["error"])

            roster = [
                {
                    "player_id": None,
                    "player_name": p.get("name", "Unknown Player"),
                    "position": p.get("position", "UNKNOWN"),
                    "team": p.get("team", "FA"),
                    "round": None,
                    "pick": None
                }
                for p in roster_data.get("players", [])
            ]
            team_info = {
                "team_id": user_league.team_id,
                "team_name": user_league.league_name or "Your Team",
                "owner": "You"
            }

        elif platform == "SLEEPER":
            if not user_league.team_id:
                raise HTTPException(
                    status_code=400,
                    detail="Team ID not set for this Sleeper league. Set it via PUT /leagues/{league_id}/settings first."
                )

            sleeper = SleeperService()
            rosters = await sleeper.get_league_rosters(user_league.league_id)

            if rosters and isinstance(rosters, list) and isinstance(rosters[0], dict) and "error" in rosters[0]:
                raise HTTPException(status_code=400, detail=rosters[0]["error"])

            target_roster = next(
                (
                    r for r in rosters
                    if str(r.get("owner_id")) == str(user_league.team_id)
                    or str(r.get("roster_id")) == str(user_league.team_id)
                ),
                None
            )

            if not target_roster:
                raise HTTPException(
                    status_code=400,
                    detail="Could not find a roster matching this team_id in the Sleeper league"
                )

            sleeper_player_ids = target_roster.get("players") or []

            # Resolve as many players as possible against our own DB first,
            # which avoids pulling Sleeper's full (multi-MB) player directory
            # unless we actually have unmatched players.
            known_players = {}
            if sleeper_player_ids:
                db_players = db.query(Player).filter(Player.sleeper_id.in_(sleeper_player_ids)).all()
                known_players = {p.sleeper_id: p for p in db_players}

            missing_ids = [pid for pid in sleeper_player_ids if pid not in known_players]
            sleeper_directory: Dict[str, Any] = {}
            if missing_ids:
                fetched = await sleeper.get_all_players()
                if isinstance(fetched, dict) and "error" not in fetched:
                    sleeper_directory = fetched

            roster = []
            for pid in sleeper_player_ids:
                if pid in known_players:
                    player = known_players[pid]
                    roster.append({
                        "player_id": player.id,
                        "player_name": player.name,
                        "position": player.position.value if player.position else "UNKNOWN",
                        "team": player.team or "FA",
                        "round": None,
                        "pick": None
                    })
                else:
                    info = sleeper_directory.get(pid, {})
                    full_name = (
                        info.get("full_name")
                        or f"{info.get('first_name', '')} {info.get('last_name', '')}".strip()
                        or "Unknown Player"
                    )
                    roster.append({
                        "player_id": None,
                        "player_name": full_name,
                        "position": info.get("position", "UNKNOWN"),
                        "team": info.get("team") or "FA",
                        "round": None,
                        "pick": None
                    })

            team_info = {
                "team_id": user_league.team_id,
                "team_name": user_league.league_name or "Your Team",
                "owner": "You"
            }

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Roster import is not implemented for platform '{platform}' yet"
            )

        return {
            "success": True,
            "league_info": {
                "id": user_league.id,
                "name": user_league.league_name,
                "platform": platform,
                "scoring_format": user_league.scoring_format,
                "season": user_league.season
            },
            "roster": roster,
            "roster_count": len(roster),
            "import_timestamp": datetime.utcnow().isoformat(),
            "data_source": platform.lower(),
            "team_info": team_info
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Roster import error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to import roster: {str(e)}")


@router.get("/user-leagues")
async def get_user_leagues_for_analysis(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get the current user's connected leagues for roster import
    """
    try:
        user_service = UserService(db)
        leagues = user_service.get_user_leagues(current_user.id)

        return {
            "success": True,
            "leagues": [
                {
                    "id": league.id,
                    "name": league.league_name,
                    "platform": league.platform.value.upper(),
                    "scoring_format": league.scoring_format,
                    "season": league.season,
                    "is_active": league.is_active
                }
                for league in leagues
            ],
            "total_leagues": len(leagues)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get user leagues: {str(e)}")
