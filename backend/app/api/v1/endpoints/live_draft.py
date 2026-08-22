from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_active_user
from app.models.user import User
from app.services.draft_assistant_service import draft_assistant, DraftPlatform
from app.services.espn_service import espn_service
from app.services.user_service import UserService
from app.services.yahoo_service import yahoo_service
from datetime import datetime
import asyncio
import json

router = APIRouter()


class StartDraftRequest(BaseModel):
    league_id: str  # League ID from frontend
    platform: Optional[str] = "sleeper"
    scoring_format: Optional[str] = "PPR"
    league_size: Optional[int] = 12
    user_team_id: Optional[str] = None


class UpdatePickRequest(BaseModel):
    session_id: str
    # Real player records (from Sleeper's raw player pool, or an AI
    # recommendation) commonly carry numeric/null fields (projected_points,
    # a missing team for free agents, etc). Dict[str, str] rejected any of
    # those with a 422, so this accepts arbitrary JSON-serializable values.
    player_picked: Dict[str, Any]


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections[session_id] = websocket

    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]

    async def send_update(self, session_id: str, data: dict):
        if session_id in self.active_connections:
            try:
                await self.active_connections[session_id].send_text(json.dumps(data))
            except:
                self.disconnect(session_id)


manager = ConnectionManager()


@router.post("/start-session")
async def start_draft_session(
    request: StartDraftRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Start a new live draft assistant session for 2025 season"""
    try:
        platform = (request.platform or "sleeper").lower()
        league_id = request.league_id
        scoring_format = request.scoring_format
        league_size = request.league_size
        real_espn_league = False
        platform_credentials: Dict[str, Any] = {}

        try:
            draft_platform = DraftPlatform(platform)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unsupported platform: {platform}")

        # ESPN needs per-user session cookies (swid/espn_s2) to read a
        # private league. Those live on the caller's own UserLeague row,
        # written by the real ESPN connect flow (POST /leagues/espn/connect
        # -> UserLeague.espn_swid/espn_s2, see leagues.py). Look that up
        # here rather than trusting anything the client could pass in the
        # request body, and rather than any shared file/global state -- the
        # same reason leagues.py moved its own ESPN endpoints off
        # connected_league.json (a single file every account used to share).
        if draft_platform == DraftPlatform.ESPN:
            user_service = UserService(db)
            espn_league = user_service.get_user_league_by_platform_id(
                user_id=current_user.id,
                platform="espn",
                league_id=league_id
            )

            if not espn_league:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "No ESPN league connected for this league ID. "
                        "Connect your ESPN league first from the Leagues page "
                        "(enter your league ID, season, and SWID/espn_s2 "
                        "cookies), then start the draft session again."
                    )
                )

            scoring_format = espn_league.scoring_format or scoring_format
            league_size = espn_league.league_size or league_size
            real_espn_league = True
            platform_credentials = {
                "swid": espn_league.espn_swid,
                "espn_s2": espn_league.espn_s2,
                "season": espn_league.season or 2025,
            }

        result = await draft_assistant.start_draft_session(
            platform=draft_platform,
            league_id=league_id,
            user_team_id=request.user_team_id,
            draft_settings={
                "scoring_format": scoring_format,
                "league_size": league_size,
                "season": 2025
            },
            platform_credentials=platform_credentials
        )

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        result["platform"] = platform
        result["league_id"] = league_id
        result["real_espn_league"] = real_espn_league
        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start draft session: {str(e)}")


@router.get("/recommendations/{session_id}")
async def get_live_recommendations(session_id: str):
    """Get current draft recommendations for a session"""
    try:
        recommendations = await draft_assistant.get_live_recommendations(session_id)
        
        if "error" in recommendations:
            raise HTTPException(status_code=404, detail=recommendations["error"])
        
        return recommendations
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get recommendations: {str(e)}")


@router.get("/draft-board/{session_id}")
async def get_draft_board(session_id: str):
    """Get comprehensive draft board with tiers"""
    try:
        draft_board = await draft_assistant.get_draft_board(session_id)
        
        if "error" in draft_board:
            raise HTTPException(status_code=404, detail=draft_board["error"])
        
        return draft_board
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get draft board: {str(e)}")


@router.get("/team-analysis/{session_id}")
async def get_team_analysis(session_id: str):
    """Get analysis of user's current team"""
    try:
        analysis = await draft_assistant.get_team_analysis(session_id)
        
        if "error" in analysis:
            raise HTTPException(status_code=404, detail=analysis["error"])
        
        return analysis
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get team analysis: {str(e)}")


@router.post("/update-pick")
async def update_user_pick(request: UpdatePickRequest):
    """Update the session when user makes a pick"""
    try:
        result = await draft_assistant.update_user_pick(
            session_id=request.session_id,
            player_picked=request.player_picked
        )
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        
        # Send real-time update to WebSocket if connected
        await manager.send_update(request.session_id, {
            "type": "pick_update",
            "data": result
        })
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update pick: {str(e)}")


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time draft updates"""
    await manager.connect(websocket, session_id)
    
    try:
        while True:
            # Keep connection alive and send periodic updates
            await asyncio.sleep(10)  # Update every 10 seconds
            
            # Get fresh recommendations
            try:
                recommendations = await draft_assistant.get_live_recommendations(session_id)
                
                if "error" not in recommendations:
                    await manager.send_update(session_id, {
                        "type": "recommendations_update",
                        "data": recommendations,
                        "timestamp": "now"
                    })
            except Exception as e:
                await manager.send_update(session_id, {
                    "type": "error",
                    "message": f"Failed to get updates: {str(e)}"
                })
                
    except WebSocketDisconnect:
        manager.disconnect(session_id)


# Platform-specific endpoints for league connection

@router.get("/espn/leagues/{league_id}/info")
async def get_espn_league_info(league_id: str, season: int = 2025):
    """Get ESPN league information"""
    try:
        league_info = await espn_service.get_league_info(league_id, season)
        
        if "error" in league_info:
            raise HTTPException(status_code=404, detail=league_info["error"])
        
        return league_info
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get ESPN league info: {str(e)}")


@router.get("/espn/leagues/{league_id}/teams")
async def get_espn_teams(league_id: str, season: int = 2025):
    """Get ESPN league teams"""
    try:
        teams = await espn_service.get_league_teams(league_id, season)
        
        if isinstance(teams, list) and len(teams) > 0 and "error" in teams[0]:
            raise HTTPException(status_code=404, detail=teams[0]["error"])
        
        return {"teams": teams}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get ESPN teams: {str(e)}")


@router.get("/espn/leagues/{league_id}/draft")
async def get_espn_draft_info(league_id: str, season: int = 2025):
    """Get ESPN draft information"""
    try:
        draft_info = await espn_service.get_draft_info(league_id, season)
        
        if "error" in draft_info:
            raise HTTPException(status_code=404, detail=draft_info["error"])
        
        return draft_info
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get ESPN draft info: {str(e)}")


@router.post("/yahoo/authenticate")
async def yahoo_authenticate(authorization_code: str, redirect_uri: str):
    """Authenticate with Yahoo Fantasy API"""
    try:
        result = await yahoo_service.authenticate(authorization_code, redirect_uri)
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Yahoo authentication failed: {str(e)}")


@router.get("/yahoo/leagues")
async def get_yahoo_leagues(season: int = 2025):
    """Get user's Yahoo Fantasy leagues"""
    try:
        leagues = await yahoo_service.get_user_leagues(season)
        
        if isinstance(leagues, list) and len(leagues) > 0 and "error" in leagues[0]:
            raise HTTPException(status_code=401, detail="Not authenticated with Yahoo")
        
        return {"leagues": leagues}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get Yahoo leagues: {str(e)}")


@router.get("/yahoo/leagues/{league_key}/draft")
async def get_yahoo_draft_info(league_key: str):
    """Get Yahoo league draft information"""
    try:
        draft_info = await yahoo_service.monitor_live_draft(league_key)
        
        if "error" in draft_info:
            raise HTTPException(status_code=404, detail=draft_info["error"])
        
        return draft_info
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get Yahoo draft info: {str(e)}")


@router.get("/session/{session_id}/status")
async def get_session_status(session_id: str):
    """Get current status of a draft session"""
    if session_id not in draft_assistant.active_drafts:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = draft_assistant.active_drafts[session_id]
    
    return {
        "session_id": session_id,
        "platform": session["platform"].value,
        "league_id": session["league_id"],
        "started_at": session["started_at"],
        "last_updated": session["last_updated"],
        "picks_made": len(session["user_roster"]),
        "status": "active"
    }


@router.delete("/session/{session_id}")
async def end_draft_session(session_id: str):
    """End a draft session"""
    if session_id not in draft_assistant.active_drafts:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Clean up session
    del draft_assistant.active_drafts[session_id]
    manager.disconnect(session_id)
    
    return {"message": "Draft session ended successfully"}