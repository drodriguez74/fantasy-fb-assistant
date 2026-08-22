from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session
import logging
from app.services.ai_service import ai_service
from app.services.sleeper_service import sleeper_service
from app.services.espn_service_enhanced import espn_service_enhanced
from app.services.yahoo_service import yahoo_service
from app.services.user_service import UserService
from app.api.deps import get_db, get_current_active_user
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/my-leagues")
async def get_user_leagues_for_draft(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get the current user's connected leagues for the Live Draft
    Assistant's league picker.

    Reads the real per-user UserLeague table -- the same store the ESPN
    connect flow (POST /leagues/espn/connect) and Sleeper/Yahoo connect
    flows write to -- instead of the single shared connected_league.json
    file this endpoint used to read via league_data_loader, which showed
    every account whichever league had most recently been connected on the
    machine, not that user's own leagues.
    """
    try:
        user_service = UserService(db)
        leagues = user_service.get_user_leagues(current_user.id)

        draft_leagues = []
        for league in leagues:
            draft_leagues.append({
                "id": league.id,
                "league_name": league.league_name or f"{league.platform.value.upper()} League {league.league_id}",
                "platform": league.platform.value,
                "league_id": league.league_id,
                "league_key": league.league_key or league.league_id,
                "season": league.season,
                "league_size": league.league_size,
                "scoring_format": league.scoring_format,
                "team_id": league.team_id,
                "draft_status": "unknown",
                "can_start_session": True
            })

        return {
            "success": True,
            "leagues": draft_leagues
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get draft leagues: {str(e)}")


class DraftRecommendationRequest(BaseModel):
    available_players: List[dict]
    team_needs: List[str]
    draft_position: int
    scoring_format: str = "PPR"
    league_size: int = 12


@router.post("/recommendations")
async def get_draft_recommendations(request: DraftRecommendationRequest):
    """Get AI-powered draft recommendations based on available players and team needs"""
    try:
        recommendations = await ai_service.generate_draft_recommendation(
            available_players=request.available_players,
            team_needs=request.team_needs,
            draft_position=request.draft_position,
            scoring_format=request.scoring_format
        )
        
        if "error" in recommendations:
            raise HTTPException(status_code=500, detail=recommendations["error"])
        
        return recommendations
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get draft recommendations: {str(e)}")


@router.get("/trending-candidates")
async def get_trending_draft_candidates(
    hours: int = Query(48, description="Lookback hours for trending data"),
    limit: int = Query(50, description="Number of candidates to return")
):
    """Get trending players that could be draft targets"""
    try:
        trending_adds = await sleeper_service.get_trending_players("add", hours, limit)
        
        if isinstance(trending_adds, list) and len(trending_adds) > 0 and "error" in trending_adds[0]:
            raise HTTPException(status_code=500, detail=trending_adds[0]["error"])
        
        # Get player data for trending players
        all_players = await sleeper_service.get_all_players()
        
        candidates = []
        for trending_player in trending_adds:
            if isinstance(trending_player, dict) and "player_id" in trending_player:
                player_id = trending_player["player_id"]
                if player_id in all_players:
                    player_data = all_players[player_id]
                    player_data["trending_count"] = trending_player.get("count", 0)
                    player_data["sleeper_id"] = player_id
                    candidates.append(player_data)
        
        return {"candidates": candidates, "hours": hours}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get trending candidates: {str(e)}")


def _is_on_active_roster(player_data: dict) -> bool:
    """Determine whether a Sleeper player record represents someone currently
    rosterable in fantasy drafts (i.e. not retired/free agent/unaffiliated).

    Sleeper's `status` field alone is unreliable: long-retired players (e.g.
    Frank Gore, Adrian Peterson) are still tagged `status: "Active"` in
    Sleeper's dataset. The reliable signal is that they also have `team: null`
    once they're no longer on an NFL roster, so require both a real team and
    an active status.
    """
    return bool(player_data.get("team")) and player_data.get("status") == "Active"


# Sleeper uses 9999999 as a sentinel for "unranked" players; treat missing
# search_rank the same way so unranked players sort to the bottom instead of
# the top.
_UNRANKED_SENTINEL = 9999999


@router.get("/positional-rankings/{position}")
async def get_positional_rankings(
    position: str,
    limit: int = Query(30, description="Number of players to return")
):
    """Get positional rankings for draft preparation"""
    try:
        valid_positions = ["QB", "RB", "WR", "TE", "K", "DEF"]
        if position.upper() not in valid_positions:
            raise HTTPException(status_code=400, detail=f"Invalid position. Must be one of: {valid_positions}")

        # Get all players and filter by position
        all_players = await sleeper_service.get_all_players()

        if "error" in all_players:
            raise HTTPException(status_code=500, detail=all_players["error"])

        position_players = []
        for player_id, player_data in all_players.items():
            if (
                isinstance(player_data, dict)
                and player_data.get("position") == position.upper()
                and _is_on_active_roster(player_data)
            ):
                player_data["sleeper_id"] = player_id
                position_players.append(player_data)

        # Rank using Sleeper's own search_rank (roughly a popularity/relevance
        # rank across all players). Lower is better; missing/unranked players
        # use Sleeper's 9999999 sentinel so they sort last, not first.
        position_players.sort(key=lambda x: x.get("search_rank") or _UNRANKED_SENTINEL)

        return {
            "position": position.upper(),
            "players": position_players[:limit],
            "total": len(position_players)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get positional rankings: {str(e)}")


@router.get("/league-analysis/{league_id}")
async def analyze_league_for_draft(league_id: str):
    """Analyze a Sleeper league to provide draft insights"""
    try:
        # Get league info
        league_info = await sleeper_service.get_league_info(league_id)
        
        if "error" in league_info:
            raise HTTPException(status_code=404, detail="League not found")
        
        # Get rosters to see what positions are being drafted
        rosters = await sleeper_service.get_league_rosters(league_id)
        
        # Analyze roster construction patterns
        position_counts = {}
        total_players = 0
        
        for roster in rosters:
            if "players" in roster and roster["players"]:
                total_players += len(roster["players"])
                # This would require looking up player positions from the players data
        
        return {
            "league_info": {
                "name": league_info.get("name", "Unknown"),
                "total_rosters": league_info.get("total_rosters", 0),
                "scoring_settings": league_info.get("scoring_settings", {}),
                "roster_positions": league_info.get("roster_positions", {})
            },
            "roster_analysis": {
                "total_players_drafted": total_players,
                "average_roster_size": total_players / len(rosters) if rosters else 0
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze league: {str(e)}")


@router.get("/waiver-candidates/{league_id}")
async def get_waiver_candidates_for_draft(league_id: str):
    """Get available waiver candidates that could be late-round draft targets"""
    try:
        candidates = await sleeper_service.get_waiver_candidates(league_id)
        
        if isinstance(candidates, list) and len(candidates) > 0 and "error" in candidates[0]:
            raise HTTPException(status_code=500, detail=candidates[0]["error"])
        
        return {"waiver_candidates": candidates, "league_id": league_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get waiver candidates: {str(e)}")


@router.get("/projections/week/{week}")
async def get_draft_projections(week: int, season: str = "2024"):
    """Get player projections to inform draft decisions"""
    try:
        projections = await sleeper_service.get_player_projections(week, season)
        
        if "error" in projections:
            raise HTTPException(status_code=500, detail=projections["error"])
        
        return {"projections": projections, "week": week, "season": season}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get projections: {str(e)}")