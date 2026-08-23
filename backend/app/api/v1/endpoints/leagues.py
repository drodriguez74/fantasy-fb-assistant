from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.api.deps import get_db, get_current_active_user
from app.models.user import User
from app.services.yahoo_service import yahoo_service
from app.services.sleeper_service import sleeper_service
from app.services.espn_service_enhanced import espn_service_enhanced
from app.services.league_management_service import LeagueManagementService
from app.schemas.user import UserLeagueCreate, UserLeagueResponse
from app.services.user_service import UserService
from datetime import datetime, timedelta

router = APIRouter()


@router.get("/yahoo/auth-url")
async def get_yahoo_auth_url():
    """Get Yahoo OAuth authorization URL"""
    # Check if Yahoo credentials are configured
    if not yahoo_service.credentials_configured:
        raise HTTPException(
            status_code=400,
            detail="Yahoo API credentials not configured. Please set YAHOO_CLIENT_ID and YAHOO_CLIENT_SECRET in your .env file."
        )
    
    redirect_uri = "http://localhost:3001/yahoo/callback"
    
    auth_url = (
        f"https://api.login.yahoo.com/oauth2/request_auth"
        f"?client_id={yahoo_service.client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope=fspt-r"  # Fantasy Sports Read permission
    )
    
    return {
        "auth_url": auth_url,
        "redirect_uri": redirect_uri
    }


class YahooConnectRequest(BaseModel):
    authorization_code: str
    redirect_uri: str = "http://localhost:3001/yahoo/callback"

@router.post("/yahoo/connect")
async def connect_yahoo_league(
    request: YahooConnectRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Connect to Yahoo Fantasy Sports.

    Real flow:
    1. Exchange the real OAuth authorization_code (from the Yahoo consent
       screen, relayed through YahooCallbackPage's postMessage) for a real
       access/refresh token pair via yahoo_service.authenticate().
    2. Use that access token to fetch this user's real Yahoo leagues via
       yahoo_service.get_user_leagues() -- no token is ever stored on the
       yahoo_service singleton; it's threaded through explicitly.
    3. Persist a UserLeague row per Yahoo league, scoped to current_user,
       carrying the access token, refresh token, and expiry -- mirroring
       exactly how POST /espn/connect persists espn_swid/espn_s2 on
       current_user's own UserLeague rows instead of shared/global state.
    """
    if not yahoo_service.credentials_configured:
        raise HTTPException(
            status_code=400,
            detail="Yahoo API credentials not configured. Please set YAHOO_CLIENT_ID and YAHOO_CLIENT_SECRET in your .env file."
        )

    try:
        token_result = await yahoo_service.authenticate(
            request.authorization_code, request.redirect_uri
        )

        if "error" in token_result:
            raise HTTPException(status_code=400, detail=token_result["error"])

        access_token = token_result.get("access_token")
        refresh_token = token_result.get("refresh_token")
        expires_in = token_result.get("expires_in")

        if not access_token:
            raise HTTPException(
                status_code=400,
                detail="Yahoo did not return an access token"
            )

        expires_at = None
        if expires_in is not None:
            try:
                expires_at = datetime.utcnow() + timedelta(seconds=int(expires_in))
            except (TypeError, ValueError):
                expires_at = None

        # Fetch this user's real Yahoo fantasy football leagues for the
        # current season using the freshly-issued access token.
        season = datetime.utcnow().year
        yahoo_leagues = await yahoo_service.get_user_leagues(access_token, season=season)

        if (
            isinstance(yahoo_leagues, list)
            and len(yahoo_leagues) > 0
            and isinstance(yahoo_leagues[0], dict)
            and "error" in yahoo_leagues[0]
        ):
            raise HTTPException(status_code=400, detail=yahoo_leagues[0]["error"])

        user_service = UserService(db)
        connected_leagues = []

        for yl in yahoo_leagues:
            league_key = yl.get("league_key")
            league_id = yl.get("league_id")
            if not league_id:
                continue

            user_league = user_service.add_user_league(
                user_id=current_user.id,
                platform="yahoo",
                league_id=str(league_id),
                league_data={
                    "league_key": league_key,
                    "league_name": yl.get("name") or f"Yahoo League {league_id}",
                    "season": season,
                    "scoring_format": yl.get("scoring_type") or "PPR",
                    "league_size": yl.get("num_teams"),
                    "yahoo_access_token": access_token,
                    "yahoo_refresh_token": refresh_token,
                    "yahoo_token_expires_at": expires_at,
                }
            )

            if user_league is None:
                continue

            connected_leagues.append({
                "id": user_league.id,
                "league_name": user_league.league_name,
                "league_key": user_league.league_key,
                "platform": "YAHOO",
                "league_size": user_league.league_size,
                "scoring_format": user_league.scoring_format,
            })

        return {
            "success": True,
            "leagues_connected": len(connected_leagues),
            "leagues": connected_leagues
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect Yahoo account: {str(e)}")


class ESPNConnectRequest(BaseModel):
    league_id: str
    season: int = 2025
    swid: Optional[str] = None
    espn_s2: Optional[str] = None
    # Which team in the league is the user's own. Optional so existing
    # callers/tests that don't know it yet still work, but the frontend
    # should always send this after letting the user pick from
    # GET /espn/teams -- leaving it null blocks every feature (roster
    # analysis, matchups) that needs to know "your" team.
    team_id: Optional[str] = None

@router.get("/espn/teams")
async def get_espn_teams(
    league_id: str = Query(..., description="ESPN league ID"),
    season: int = Query(2025, description="Season year"),
    swid: Optional[str] = Query(None, description="ESPN SWID cookie for private leagues"),
    espn_s2: Optional[str] = Query(None, description="ESPN espn_s2 cookie for private leagues")
):
    """List the teams in an ESPN league, so the user connecting can pick which one is theirs."""
    try:
        teams = await espn_service_enhanced.get_league_teams(
            league_id=league_id,
            season=season,
            swid=swid,
            espn_s2=espn_s2
        )

        if teams and isinstance(teams, list) and "error" in teams[0]:
            raise HTTPException(status_code=400, detail=teams[0]["error"])

        return {
            "teams": [
                {
                    "team_id": str(t["team_id"]),
                    "team_name": t.get("team_name"),
                    "owner": t.get("owner"),
                }
                for t in teams
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load ESPN league teams: {str(e)}")


@router.post("/espn/connect")
async def connect_espn_league(
    request: ESPNConnectRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Connect to ESPN Fantasy Football league"""
    try:
        # Test connection and get league info
        connection_result = await espn_service_enhanced.connect_league(
            league_id=request.league_id,
            season=request.season,
            swid=request.swid,
            espn_s2=request.espn_s2
        )

        if not connection_result.get("connected", False):
            raise HTTPException(
                status_code=400,
                detail=connection_result.get("error", "Failed to connect to ESPN league")
            )

        league_info = connection_result["league_info"]

        # Persist the connection against this user, not a shared file on disk --
        # every account used to see whichever league was last written here.
        user_service = UserService(db)
        user_league = user_service.add_user_league(
            user_id=current_user.id,
            platform="espn",
            league_id=request.league_id,
            league_data={
                "league_name": league_info.get("league_name", f"ESPN League {request.league_id}"),
                "season": request.season,
                "league_size": league_info.get("team_count", 10),
                "scoring_format": league_info.get("scoring_type", "PPR"),
                "espn_swid": request.swid,
                "espn_s2": request.espn_s2,
                "team_id": request.team_id,
            }
        )

        # Return connection info
        return {
            "success": True,
            "connected": True,
            "access_level": connection_result.get("access_level", "public"),
            "league": {
                "id": user_league.id,
                "league_name": league_info.get("league_name", f"ESPN League {request.league_id}"),
                "league_key": str(request.league_id),
                "platform": "ESPN",
                "league_size": league_info.get("team_count", 10),
                "scoring_format": league_info.get("scoring_type", "PPR"),
                "current_week": league_info.get("current_week", 1),
                "team_count": league_info.get("team_count", 10),
                "team_id": user_league.team_id,
            },
            "league_info": league_info
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect ESPN league: {str(e)}")


@router.get("/espn/test-connection")
async def test_espn_connection(
    league_id: str,
    season: int = Query(2025, description="Season year"),
    swid: Optional[str] = Query(None, description="ESPN SWID cookie for private leagues"),
    espn_s2: Optional[str] = Query(None, description="ESPN espn_s2 cookie for private leagues")
):
    """Test ESPN league connection without storing"""
    try:
        connection_result = await espn_service_enhanced.connect_league(
            league_id=league_id,
            season=season,
            swid=swid,
            espn_s2=espn_s2
        )
        
        return connection_result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to test ESPN connection: {str(e)}")


@router.get("/sleeper/teams")
async def get_sleeper_teams(
    league_id: str = Query(..., description="Sleeper league ID"),
    username: Optional[str] = Query(None, description="Sleeper username, to auto-suggest which team is yours")
):
    """List the rosters/teams in a Sleeper league, for picking which one is yours.

    Sleeper's API is public and needs no auth -- unlike ESPN/Yahoo there's no
    connect step to test credentials against, so this doubles as the
    "does this league exist" check before persisting anything.
    """
    try:
        league_info = await sleeper_service.get_league_info(league_id)
        if "error" in league_info or not league_info.get("league_id"):
            raise HTTPException(
                status_code=400,
                detail=league_info.get("error", f"Sleeper league {league_id} not found")
            )

        teams = await sleeper_service.get_league_teams(league_id)
        if teams and isinstance(teams, list) and "error" in teams[0]:
            raise HTTPException(status_code=400, detail=teams[0]["error"])

        suggested_team_id = None
        if username:
            user_info = await sleeper_service.get_user_by_username(username)
            if "error" not in user_info and user_info.get("user_id"):
                for team in teams:
                    if team.get("owner_id") == user_info["user_id"]:
                        suggested_team_id = team["team_id"]
                        break

        return {
            "league_name": league_info.get("name", f"Sleeper League {league_id}"),
            "season": league_info.get("season"),
            "teams": teams,
            "suggested_team_id": suggested_team_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load Sleeper league teams: {str(e)}")


class SleeperConnectRequest(BaseModel):
    league_id: str
    username: Optional[str] = None
    # Roster/team ID within the league that belongs to the user, normally
    # picked from GET /sleeper/teams. If omitted but username is provided,
    # we try to resolve it server-side from the username.
    team_id: Optional[str] = None


@router.post("/sleeper/connect")
async def connect_sleeper_league(
    request: SleeperConnectRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Connect to a Sleeper Fantasy Football league.

    Sleeper's API is public (no OAuth/cookies), so this just validates the
    league exists and persists it against the current user -- following the
    same per-user UserLeague pattern as ESPN/Yahoo rather than any shared
    state.
    """
    try:
        league_info = await sleeper_service.get_league_info(request.league_id)
        if "error" in league_info or not league_info.get("league_id"):
            raise HTTPException(
                status_code=400,
                detail=league_info.get("error", f"Sleeper league {request.league_id} not found")
            )

        team_id = request.team_id

        # No team explicitly chosen but we have a username -- try to resolve
        # which roster is theirs so team_id isn't left null (the same gap
        # that used to block ESPN's roster/matchup analysis).
        if not team_id and request.username:
            user_info = await sleeper_service.get_user_by_username(request.username)
            if "error" not in user_info and user_info.get("user_id"):
                rosters = await sleeper_service.get_league_rosters(request.league_id)
                for roster in rosters:
                    if isinstance(roster, dict) and roster.get("owner_id") == user_info["user_id"]:
                        team_id = str(roster.get("roster_id"))
                        break

        scoring_settings = league_info.get("scoring_settings") or {}
        scoring_format = "PPR" if scoring_settings.get("rec") else "Standard"

        user_service = UserService(db)
        user_league = user_service.add_user_league(
            user_id=current_user.id,
            platform="sleeper",
            league_id=request.league_id,
            league_data={
                "league_name": league_info.get("name", f"Sleeper League {request.league_id}"),
                "season": int(league_info.get("season") or datetime.now().year),
                "league_size": league_info.get("total_rosters", 10),
                "scoring_format": scoring_format,
                "team_id": team_id,
            }
        )

        return {
            "success": True,
            "connected": True,
            "league": {
                "id": user_league.id,
                "league_name": user_league.league_name,
                "league_key": request.league_id,
                "platform": "SLEEPER",
                "league_size": user_league.league_size,
                "scoring_format": user_league.scoring_format,
                "team_id": user_league.team_id,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect Sleeper league: {str(e)}")


@router.get("/")
async def get_user_leagues(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get all leagues connected to the current user"""
    user_service = UserService(db)
    leagues = user_service.get_user_leagues(current_user.id)
    return [
        {
            "id": league.id,
            "league_name": league.league_name,
            "league_key": league.league_key,
            "platform": league.platform.value.upper(),
            "scoring_format": league.scoring_format,
            "league_size": league.league_size,
            "season": league.season,
            "is_active": league.is_active,
            "team_id": league.team_id,
            "user_id": league.user_id,
            "is_commissioner": league.is_commissioner,
            "added_at": league.added_at.isoformat() if league.added_at else None,
        }
        for league in leagues
    ]


@router.get("/{league_id}/standings")
async def get_league_standings(
    league_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get real standings for the current user's own connected league.

    This used to have no auth dependency at all and, for league_id == 1,
    read a single shared file (connected_league.json) off disk -- so every
    caller, authenticated or not, saw whichever ESPN league had been
    connected last by anyone. Every other league_id returned a hardcoded
    fake "Demo League" with no teams. Fixed to follow the same pattern as
    /comprehensive-analysis and /roster-analysis: scope to the requesting
    user's own UserLeague row, then fetch real standings using that
    league's own stored platform + credentials.
    """
    try:
        user_service = UserService(db)
        user_league = user_service.get_user_league(current_user.id, league_id)

        if not user_league:
            raise HTTPException(status_code=404, detail="League not found")

        platform = user_league.platform.value.upper()

        if platform == "ESPN":
            standings = await espn_service_enhanced.get_standings(
                league_id=user_league.league_id,
                season=user_league.season,
                swid=user_league.espn_swid,
                espn_s2=user_league.espn_s2
            )

            if standings and isinstance(standings, list) and "error" in standings[0]:
                raise HTTPException(status_code=400, detail=standings[0]["error"])

            return {
                "league_name": user_league.league_name,
                "season": user_league.season,
                "teams": standings
            }

        elif platform == "YAHOO":
            if not user_league.yahoo_access_token:
                raise HTTPException(status_code=400, detail="Yahoo account not connected for this league. Please reconnect your Yahoo account.")
            if user_league.yahoo_token_expires_at and user_league.yahoo_token_expires_at < datetime.utcnow():
                raise HTTPException(status_code=400, detail="Your Yahoo connection has expired. Please reconnect your Yahoo account.")

            teams = await yahoo_service.get_league_teams(user_league.yahoo_access_token, user_league.league_key)

            if teams and isinstance(teams, list) and "error" in teams[0]:
                raise HTTPException(status_code=400, detail=teams[0]["error"])

            teams.sort(key=lambda t: (-int(t.get("wins", 0) or 0), -float(t.get("points_for", 0) or 0)))
            for i, team in enumerate(teams):
                team["rank"] = i + 1

            return {
                "league_name": user_league.league_name,
                "season": user_league.season,
                "teams": teams
            }

        elif platform == "SLEEPER":
            teams = await sleeper_service.get_league_teams(user_league.league_id)

            if teams and isinstance(teams, list) and "error" in teams[0]:
                raise HTTPException(status_code=400, detail=teams[0]["error"])

            teams.sort(key=lambda t: -int(t.get("wins", 0) or 0))
            for i, team in enumerate(teams):
                team["rank"] = i + 1

            return {
                "league_name": user_league.league_name,
                "season": user_league.season,
                "teams": teams
            }

        else:
            raise HTTPException(status_code=400, detail=f"Standings are not yet implemented for {platform} leagues.")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get standings: {str(e)}")


@router.get("/{league_id}/insights")
async def get_league_insights(
    league_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get weekly insights for the current user's own league"""
    try:
        # Scope to the requesting user's own league. This endpoint used to
        # accept an optional/unused current_user, read connected_league.json
        # (a single shared file, see app.utils.league_data_loader), and
        # return hardcoded specific-player advice ("Lamar Jackson" to
        # start, "Justice Hill"/"Rashod Bateman" to pick up) for every
        # league_id and every caller -- real or anonymous -- regardless of
        # who actually owned that league or what was on their roster.
        user_service = UserService(db)
        user_league = user_service.get_user_league(current_user.id, league_id)

        if not user_league:
            raise HTTPException(status_code=404, detail="League not found")

        league_info = {
            "id": user_league.id,
            "name": user_league.league_name,
            "platform": user_league.platform.value.upper(),
            "season": user_league.season,
            "scoring_format": user_league.scoring_format,
            "league_size": user_league.league_size,
        }

        # There is no real per-player start/sit, matchup, or waiver
        # projection engine wired up for league insights (the AI-analysis
        # endpoints that do exist, e.g. /analysis and /waiver-recommendations,
        # depend on roster/matchup data this endpoint doesn't have). Rather
        # than keep fabricating specific-player picks that were never
        # actually computed for this league, return real league metadata
        # and an honest "not yet available" outlook.
        insights_data = {
            "league_name": user_league.league_name,
            "league_info": league_info,
            "insights": {
                "weekly_outlook": {
                    "outlook": "Not available",
                    "key_points": [
                        "Player-specific start/sit and waiver-wire recommendations are not yet computed for this league."
                    ],
                    "confidence": "N/A"
                },
                "start_sit": [],
                "pickup_targets": [],
                "lineup_optimization": {
                    "projected_points": None,
                    "lineup_changes": [],
                    "confidence": "N/A"
                }
            },
            "generated_at": datetime.now().isoformat()
        }

        return insights_data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get league insights: {str(e)}")


@router.get("/{league_id}/roster-analysis")
async def get_roster_analysis(
    league_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get roster analysis for the current user's own connected league.

    This used to hardcode team_id=1 and season=2025 (instead of using the
    connected league's own real user_league.team_id/.season), and layered
    fabricated numbers -- "composition_score": 85, overall "score": 87,
    "avg_player_value": 12.4, plus canned strengths/weaknesses text and a
    leftover dev fallback team name ("CMC-Allen Wrenches") -- on top of an
    otherwise-real roster fetch. There is no real composition/grading
    engine for ESPN rosters yet (the one real grading pipeline that exists,
    _analyze_yahoo_roster in league_management_service.py, is Yahoo-only
    and AI-driven), so rather than keep fabricating scores that were never
    actually computed, this now returns real roster data plus an honest
    "not yet computed" grading state -- the same pattern already used by
    the fixed /{league_id}/insights endpoint.
    """
    try:
        user_service = UserService(db)
        user_league = user_service.get_user_league(current_user.id, league_id)

        if not user_league:
            raise HTTPException(status_code=404, detail="League not found")

        league_info = {
            "id": league_id,
            "name": user_league.league_name,
            "platform": user_league.platform.value.upper(),
            "season": user_league.season,
            "scoring_format": user_league.scoring_format,
            "league_size": user_league.league_size,
        }

        ungraded_analysis_template = {
            "composition": {
                "starting_lineup": [],
                "bench_players": [],
                "composition_score": None
            },
            "overall_grade": {
                "grade": "N/A",
                "score": None,
                "description": "Roster grading is not yet computed."
            },
            "strengths_weaknesses": {
                "strengths": [],
                "weaknesses": []
            }
        }

        if league_info["platform"] != "ESPN":
            return {
                "league_info": league_info,
                "roster_analysis": {
                    "team_name": None,
                    "owner": None,
                    "total_players": 0,
                    **{
                        **ungraded_analysis_template,
                        "overall_grade": {
                            **ungraded_analysis_template["overall_grade"],
                            "description": f"Roster analysis is not yet implemented for {league_info['platform']} leagues."
                        }
                    }
                }
            }

        if not user_league.team_id:
            return {
                "league_info": league_info,
                "roster_analysis": {
                    "team_name": None,
                    "owner": None,
                    "total_players": 0,
                    **{
                        **ungraded_analysis_template,
                        "overall_grade": {
                            **ungraded_analysis_template["overall_grade"],
                            "description": "Your team is not identified for this league yet. Set your team via PUT /leagues/{league_id}/settings to see your real roster."
                        }
                    }
                }
            }

        roster_data = await espn_service_enhanced.get_team_roster(
            league_id=user_league.league_id,
            team_id=user_league.team_id,
            season=user_league.season,
            swid=user_league.espn_swid,
            espn_s2=user_league.espn_s2
        )

        if "error" in roster_data:
            raise HTTPException(status_code=400, detail=roster_data["error"])

        players = roster_data.get("players", [])
        starting_lineup = [p for p in players if p.get("slot_position") != "BENCH"]
        bench_players = [p for p in players if p.get("slot_position") == "BENCH"]

        return {
            "league_info": league_info,
            "roster_analysis": {
                "team_name": roster_data.get("team_name"),
                "owner": roster_data.get("owner"),
                "roster_size": roster_data.get("roster_size", len(players)),
                "total_players": len(players),
                "composition": {
                    "starting_lineup": starting_lineup,
                    "bench_players": bench_players,
                    # No real depth/value-based composition scoring exists
                    # for ESPN rosters yet -- report honestly instead of a
                    # fabricated number.
                    "composition_score": None
                },
                "overall_grade": {
                    "grade": "N/A",
                    "score": None,
                    "description": "Roster grading is not yet computed for ESPN leagues.",
                    "player_count": len(players)
                },
                "strengths_weaknesses": {
                    "strengths": [],
                    "weaknesses": []
                },
                "players": players
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get roster analysis: {str(e)}")


@router.get("/{league_id}/waiver-recommendations")
async def get_waiver_recommendations(
    league_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get league-specific waiver wire recommendations"""
    try:
        league_service = LeagueManagementService(db)
        analysis = await league_service.get_comprehensive_league_analysis(current_user.id, league_id)
        
        if "error" in analysis:
            raise HTTPException(status_code=400, detail=analysis["error"])
        
        return {
            "league_info": analysis.get("league_info", {}),
            "waiver_recommendations": analysis.get("waiver_recommendations", {})
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get waiver recommendations: {str(e)}")


@router.get("/{league_id}/trade-suggestions")
async def get_trade_suggestions(
    league_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get AI-powered trade suggestions"""
    try:
        league_service = LeagueManagementService(db)
        analysis = await league_service.get_comprehensive_league_analysis(current_user.id, league_id)
        
        if "error" in analysis:
            raise HTTPException(status_code=400, detail=analysis["error"])
        
        return {
            "league_info": analysis.get("league_info", {}),
            "trade_recommendations": analysis.get("trade_recommendations", {})
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get trade suggestions: {str(e)}")


@router.put("/{league_id}/settings")
async def update_league_settings(
    league_id: int,
    settings: Dict[str, Any],
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update league settings and preferences"""
    try:
        user_service = UserService(db)
        league = user_service.get_user_league(current_user.id, league_id)
        
        if not league:
            raise HTTPException(status_code=404, detail="League not found")
        
        # Update allowed settings
        allowed_settings = [
            "enable_notifications", "auto_draft_assistant", "team_id"
        ]
        
        updated_fields = {}
        for key, value in settings.items():
            if key in allowed_settings:
                setattr(league, key, value)
                updated_fields[key] = value
        
        db.commit()
        db.refresh(league)
        
        return {
            "success": True,
            "updated_fields": updated_fields,
            "league_id": league_id
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update league settings: {str(e)}")


@router.delete("/{league_id}")
async def disconnect_league(
    league_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Disconnect/remove a league"""
    try:
        user_service = UserService(db)
        success = user_service.remove_user_league(current_user.id, league_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="League not found")
        
        return {"success": True, "message": "League disconnected successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to disconnect league: {str(e)}")