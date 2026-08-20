from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends
from typing import Dict, List, Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_active_user
from app.models.user import User
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
    player_picked: Dict[str, str]  # player info


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
async def start_draft_session(request: StartDraftRequest):
    """Start a new live draft assistant session for 2025 season"""
    try:
        # Load real connection data if available
        connection_data = {}
        try:
            with open("/Users/darwinrodriguez/projects/fantasy-football-assistant/backend/connected_league.json", "r") as f:
                connection_data = json.load(f)
        except FileNotFoundError:
            pass
        
        # Use real league data if connected, otherwise use request data
        if connection_data.get("espn_league_id"):
            real_league_id = connection_data["espn_league_id"]
            league_settings = {
                "scoring_format": connection_data.get("scoring_format", "PPR"),
                "league_size": connection_data.get("league_size", 10),
                "league_name": f"ESPN League {real_league_id}",
                "season": 2025
            }
        else:
            real_league_id = request.league_id
            league_settings = {
                "scoring_format": request.scoring_format,
                "league_size": request.league_size,
                "league_name": f"League {request.league_id}",
                "season": 2025
            }
        
        session_id = f"draft_{real_league_id}_{request.platform}_{int(datetime.now().timestamp())}"
        
        # Return session with league data immediately (no API calls)
        return {
            "session_id": session_id,
            "platform": request.platform,
            "league_id": real_league_id,
            "started_at": datetime.now().isoformat(),
            "status": "active",
            "league_name": league_settings["league_name"],
            "scoring_format": league_settings["scoring_format"],
            "league_size": league_settings["league_size"],
            "season": 2025,
            "draft_position": 5,
            "current_round": 1,
            "current_pick": 1,
            "real_espn_league": bool(connection_data.get("espn_league_id")),
            "espn_league_id": real_league_id
        }
        
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