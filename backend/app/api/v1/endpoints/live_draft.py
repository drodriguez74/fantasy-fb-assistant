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


class MarkDraftedRequest(BaseModel):
    session_id: str
    # available_players records use "player_id" (see
    # espn_service_enhanced._format_player / the Sleeper equivalent) --
    # type varies by platform (ESPN: int, Sleeper: str), so accept either.
    player_id: Any


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
        # The connected UserLeague row's own id (not the platform's
        # external league_id string) for this session, when one exists --
        # threaded through to draft_assistant.start_draft_session so it can
        # check for a manually-configured LeagueScoring override (see
        # DraftAssistantService._apply_manual_scoring_override). None for a
        # Sleeper league the user never formally "connected" via this app
        # (Sleeper needs no auth, so a bare league_id works without one) --
        # that's fine, it just means no manual override is possible for it.
        user_league_id: Optional[int] = None

        try:
            draft_platform = DraftPlatform(platform)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unsupported platform: {platform}")

        if draft_platform == DraftPlatform.SLEEPER:
            sleeper_league = UserService(db).get_user_league_by_platform_id(
                user_id=current_user.id,
                platform="sleeper",
                league_id=league_id
            )
            if sleeper_league:
                user_league_id = sleeper_league.id

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
            user_league_id = espn_league.id
            platform_credentials = {
                "swid": espn_league.espn_swid,
                "espn_s2": espn_league.espn_s2,
                "season": espn_league.season or 2025,
            }

        # Yahoo needs a real per-user OAuth access token to read a league.
        # Those live on the caller's own UserLeague row, written by the
        # real Yahoo connect flow (POST /leagues/yahoo/connect ->
        # UserLeague.yahoo_access_token/yahoo_refresh_token/
        # yahoo_token_expires_at, see leagues.py) -- looked up here the
        # same way the ESPN branch above looks up swid/espn_s2, rather than
        # trusting anything the client could pass in the request body.
        # Yahoo tokens expire in ~1hr (unlike ESPN's long-lived cookies),
        # so an expired token is rejected honestly right here at session
        # start -- the same "expired == absent, tell the user to
        # reconnect" check league_management_service._get_yahoo_token and
        # leagues.py's own GET .../analysis /.../matchups endpoints already
        # use -- rather than letting the session start and fail later with
        # a cryptic 401 from Yahoo's API.
        if draft_platform == DraftPlatform.YAHOO:
            user_service = UserService(db)
            yahoo_league = user_service.get_user_league_by_platform_id(
                user_id=current_user.id,
                platform="yahoo",
                league_id=league_id
            )

            if not yahoo_league:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "No Yahoo league connected for this league ID. "
                        "Connect your Yahoo account first from the Leagues "
                        "page, then start the draft session again."
                    )
                )

            if not yahoo_league.yahoo_access_token:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Your Yahoo connection is missing an access token. "
                        "Reconnect your Yahoo account from the Leagues "
                        "page, then start the draft session again."
                    )
                )

            if yahoo_league.yahoo_token_expires_at and yahoo_league.yahoo_token_expires_at < datetime.utcnow():
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Your Yahoo connection has expired. Reconnect your "
                        "Yahoo account from the Leagues page, then start "
                        "the draft session again."
                    )
                )

            scoring_format = yahoo_league.scoring_format or scoring_format
            league_size = yahoo_league.league_size or league_size
            user_league_id = yahoo_league.id
            platform_credentials = {
                "access_token": yahoo_league.yahoo_access_token,
                "expires_at": yahoo_league.yahoo_token_expires_at,
            }
            # Yahoo's API addresses a league by its composite league_key
            # (e.g. "449.l.12345"), not the bare numeric league_id this
            # endpoint receives from the frontend's league picker -- see
            # draft_assistant_service._get_yahoo_draft_state's docstring.
            # Prefer the stored league_key (set at connect time by POST
            # /leagues/yahoo/connect); fall back to league_id if it's ever
            # missing rather than failing the session outright.
            league_id = yahoo_league.league_key or league_id

        result = await draft_assistant.start_draft_session(
            platform=draft_platform,
            league_id=league_id,
            user_team_id=request.user_team_id,
            draft_settings={
                "scoring_format": scoring_format,
                "league_size": league_size,
                "season": 2025
            },
            platform_credentials=platform_credentials,
            user_league_id=user_league_id,
            db=db
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


@router.post("/mark-drafted")
async def mark_player_drafted(request: MarkDraftedRequest):
    """Manually remove a player from the available pool because some OTHER
    team drafted them. Distinct from /update-pick (which records the
    session user's own pick): this exists because ESPN's live draft feed
    is confirmed to never reflect real in-progress picks (see CLAUDE.md),
    so available_players silently includes already-drafted players for an
    entire draft unless corrected this way.
    """
    try:
        result = await draft_assistant.mark_player_drafted(
            session_id=request.session_id,
            player_id=request.player_id
        )

        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])

        await manager.send_update(request.session_id, {
            "type": "player_marked_drafted",
            "data": result
        })

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to mark player drafted: {str(e)}")


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


@router.delete("/session/{session_id}")
async def end_draft_session(session_id: str):
    """End a draft session"""
    if session_id not in draft_assistant.active_drafts:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Clean up session
    del draft_assistant.active_drafts[session_id]
    manager.disconnect(session_id)
    
    return {"message": "Draft session ended successfully"}