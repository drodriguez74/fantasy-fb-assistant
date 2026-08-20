from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List
from sqlalchemy.orm import Session
from datetime import datetime
from pydantic import BaseModel
from app.api.deps import get_db, get_current_active_user
from app.models.user import User
from app.models.player import Player, Position
from app.services.sleeper_service import sleeper_service
# from app.services.ai_service import ai_service # Temporarily commented out due to missing dependencies
# from app.services.scraper_service import scraper_service # Temporarily commented out due to missing dependencies
from app.services.player_data_service import PlayerDataService
from app.services.historical_data_service import HistoricalDataService

router = APIRouter()

# Sleeper uses 9999999 as a sentinel for "unranked" players (see the
# positional-rankings fix in draft.py); treat missing search_rank the same
# way so unranked players sort to the bottom instead of the top.
_UNRANKED_SENTINEL = 9999999

_VALID_SORTS = ("rank", "bye_week")


@router.get("/")
async def get_players(
    position: Optional[str] = Query(None, description="Filter by position (QB, RB, WR, TE, K, DEF)"),
    sort: Optional[str] = Query(
        None,
        description="Sort order: 'rank' (Sleeper search_rank ascending, ADP proxy) or "
                     "'bye_week' (ascending, players with no bye week sort last). "
                     "Defaults to the existing relevance sort (rostered players first, then search_rank)."
    ),
    page: int = Query(1, description="Page number (1-based)", ge=1),
    page_size: int = Query(50, description="Number of players per page", ge=1, le=200)
):
    """Get all NFL players with optional position filtering"""
    try:
        if sort is not None and sort not in _VALID_SORTS:
            raise HTTPException(status_code=400, detail=f"Invalid sort. Must be one of: {list(_VALID_SORTS)}")

        all_players = await sleeper_service.get_all_players()
        
        if "error" in all_players:
            raise HTTPException(status_code=500, detail=all_players["error"])
        
        # Convert to list, transform data, and filter if needed
        players_list = []
        fantasy_positions = ["QB", "RB", "WR", "TE", "K", "DEF", "DST"]
        
        for player_id, player_data in all_players.items():
            if isinstance(player_data, dict):
                player_position = player_data.get("position", "UNKNOWN")
                
                # Skip non-fantasy positions unless specifically requested
                if not position and player_position not in fantasy_positions:
                    continue
                
                # Transform Sleeper format to our Player model format
                transformed_player = {
                    "id": int(player_id) if player_id.isdigit() else hash(player_id) % 100000,
                    "name": player_data.get("full_name", f"{player_data.get('first_name', '')} {player_data.get('last_name', '')}").strip(),
                    "team": player_data.get("team_abbr") or player_data.get("team") or "FA",
                    "position": player_data.get("position", "UNKNOWN"),
                    "espn_id": str(player_data.get("espn_id")) if player_data.get("espn_id") else None,
                    "yahoo_id": str(player_data.get("yahoo_id")) if player_data.get("yahoo_id") else None,
                    "sleeper_id": player_id,
                    "projected_points": None,  # Could be calculated from projections
                    "adp": None,  # Could be calculated from ADP data
                    "bye_week": player_data.get("bye_week"),
                    "injury_status": player_data.get("injury_status") or "Healthy",
                    "depth_chart_order": player_data.get("depth_chart_order"),
                    "ai_analysis": None,  # Generated on demand
                    "risk_level": None,  # Could be calculated based on injury status
                    "created_at": "2025-08-13T00:00:00Z",  # Placeholder
                    "updated_at": "2025-08-13T00:00:00Z"   # Placeholder
                }
                
                # Apply position filter
                if position and transformed_player["position"] != position.upper():
                    continue
                    
                players_list.append(transformed_player)
        
        if sort == "rank":
            # Rank by Sleeper's own search_rank (ADP proxy), ascending. Missing/
            # unranked players use Sleeper's sentinel so they sort last, not first.
            def rank_sort_key(player):
                original_data = all_players.get(player["sleeper_id"], {})
                return original_data.get("search_rank") or _UNRANKED_SENTINEL

            players_list.sort(key=rank_sort_key)
        elif sort == "bye_week":
            # Ascending by bye week; players with no bye week data (None) sort last
            # instead of first or raising on the None/int comparison.
            def bye_week_sort_key(player):
                bye_week = player["bye_week"]
                return (bye_week is None, bye_week if bye_week is not None else 0)

            players_list.sort(key=bye_week_sort_key)
        else:
            # Default: sort by relevance (players with teams first, then by search rank)
            def sort_key(player):
                has_team = 1 if player["team"] != "FA" else 2
                # Get search rank from original data if available
                original_data = all_players.get(player["sleeper_id"], {})
                search_rank = original_data.get("search_rank") or _UNRANKED_SENTINEL
                return (has_team, search_rank)

            players_list.sort(key=sort_key)
        
        # Apply pagination
        total_count = len(players_list)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_players = players_list[start_idx:end_idx]
        
        # Calculate pagination metadata
        total_pages = (total_count + page_size - 1) // page_size
        has_next = page < total_pages
        has_previous = page > 1
        
        return {
            "players": paginated_players,
            "pagination": {
                "total_count": total_count,
                "total_pages": total_pages,
                "current_page": page,
                "page_size": page_size,
                "has_next": has_next,
                "has_previous": has_previous,
                "next_page": page + 1 if has_next else None,
                "previous_page": page - 1 if has_previous else None
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get players: {str(e)}")


@router.get("/trending")
async def get_trending_players(
    trend_type: str = Query("add", description="Trend type: 'add' or 'drop'"),
    hours: int = Query(24, description="Lookback hours for trending data"),
    limit: int = Query(25, description="Number of trending players to return")
):
    """Get trending players (adds/drops)"""
    try:
        trending = await sleeper_service.get_trending_players(trend_type, hours, limit)
        
        if isinstance(trending, list) and len(trending) > 0 and "error" in trending[0]:
            raise HTTPException(status_code=500, detail=trending[0]["error"])
        
        return {"trending_players": trending, "trend_type": trend_type, "hours": hours}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get trending players: {str(e)}")


@router.get("/projections/week/{week}")
async def get_projections(week: int, season: str = "2024"):
    """Get player projections for a specific week"""
    try:
        projections = await sleeper_service.get_player_projections(week, season)
        
        if "error" in projections:
            raise HTTPException(status_code=500, detail=projections["error"])
        
        return {"projections": projections, "week": week, "season": season}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get projections: {str(e)}")


@router.get("/{player_id}")
async def get_player(player_id: str):
    """Get detailed player information including AI analysis"""
    try:
        # Get player data from Sleeper
        all_players = await sleeper_service.get_all_players()
        
        if player_id not in all_players:
            raise HTTPException(status_code=404, detail="Player not found")
        
        player_data = all_players[player_id]
        player_name = player_data.get("full_name", "Unknown Player")
        
        # Get player stats
        stats = await sleeper_service.get_player_stats(player_id)
        
        # Get AI analysis
        # ai_analysis = await ai_service.generate_player_analysis( # Temporarily disabled
        ai_analysis = "AI analysis temporarily unavailable. Player analysis will be restored soon."
        
        # Get recent news
        # news = await scraper_service.scrape_player_news(player_name) # Temporarily disabled
        news = []
        
        return {
            "id": int(player_id) if player_id.isdigit() else hash(player_id) % 100000,
            "player_data": player_data,
            "stats": stats,
            "ai_analysis": ai_analysis,
            "recent_news": news[:3],  # Latest 3 news articles
            "sleeper_id": player_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get player details: {str(e)}")


@router.get("/{player_id}/stats/{season}")
async def get_player_stats(player_id: str, season: str = "2024"):
    """Get player stats for a specific season"""
    try:
        stats = await sleeper_service.get_player_stats(player_id, season)
        
        if "error" in stats:
            raise HTTPException(status_code=500, detail=stats["error"])
        
        return {"player_id": player_id, "season": season, "stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get player stats: {str(e)}")


@router.get("/search/{player_name}")
async def search_players(player_name: str, db: Session = Depends(get_db)):
    """Search for players by name"""
    try:
        # First search our local players database
        search_term = f"%{player_name.lower()}%"
        local_players = db.query(Player).filter(
            Player.name.ilike(search_term)
        ).limit(10).all()
        
        matches = []
        
        # Convert local players to expected format
        for player in local_players:
            matches.append({
                "id": player.id,
                "name": player.name,
                "full_name": player.name,
                "position": player.position.value if hasattr(player.position, 'value') else str(player.position),
                "team": player.team,
                "sleeper_id": player.sleeper_id
            })
        
        # Always search Sleeper for additional results to ensure comprehensive coverage
        if len(matches) < 15:
            all_players = await sleeper_service.get_all_players()
            
            if "error" not in all_players:
                sleeper_search_term = player_name.lower()
                sleeper_matches = []
                
                for player_id, player_data in all_players.items():
                    if isinstance(player_data, dict):
                        full_name = player_data.get("full_name", "").lower()
                        first_name = player_data.get("first_name", "").lower()
                        last_name = player_data.get("last_name", "").lower()
                        position = player_data.get("position", "")
                        
                        if (sleeper_search_term in full_name or 
                            sleeper_search_term in first_name or 
                            sleeper_search_term in last_name):
                            
                            # Check if this player is already in our matches
                            if not any(m.get("sleeper_id") == player_id for m in matches):
                                # Calculate match score for prioritization
                                score = 0
                                if sleeper_search_term in first_name:
                                    score += 10
                                if sleeper_search_term in last_name:
                                    score += 10
                                if first_name.startswith(sleeper_search_term):
                                    score += 20
                                if last_name.startswith(sleeper_search_term):
                                    score += 20
                                if position in ["QB", "RB", "WR", "TE"]:  # Fantasy relevant positions
                                    score += 5
                                
                                sleeper_player = {
                                    "id": None,  # No local ID
                                    "name": player_data.get("full_name", ""),
                                    "full_name": player_data.get("full_name", ""),
                                    "position": position,
                                    "team": player_data.get("team", "FA"),
                                    "sleeper_id": player_id,
                                    "match_score": score
                                }
                                sleeper_matches.append(sleeper_player)
                
                # Sort Sleeper matches by score (highest first) and add to results
                sleeper_matches.sort(key=lambda x: x.get("match_score", 0), reverse=True)
                for player in sleeper_matches:
                    player.pop("match_score", None)  # Remove score from final result
                    matches.append(player)
                    if len(matches) >= 20:
                        break
        
        return {"matches": matches[:20], "search_term": player_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to search players: {str(e)}")


class AddPlayerRequest(BaseModel):
    sleeper_id: str

@router.post("/add-from-sleeper")
async def add_player_from_sleeper(
    request: AddPlayerRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Add a player from Sleeper data to our local database and sync their historical data"""
    try:
        # Check if player already exists in our database
        existing_player = db.query(Player).filter(Player.sleeper_id == request.sleeper_id).first()
        if existing_player:
            return {
                "message": "Player already exists",
                "player_id": existing_player.id,
                "player_name": existing_player.name
            }
        
        # Get player data from Sleeper
        all_players = await sleeper_service.get_all_players()
        
        if request.sleeper_id not in all_players:
            raise HTTPException(status_code=404, detail="Player not found in Sleeper data")
        
        player_data = all_players[request.sleeper_id]
        
        # Map position string to enum
        position_str = player_data.get("position", "")
        try:
            position = Position(position_str) if position_str else Position.UNKNOWN
        except ValueError:
            position = Position.UNKNOWN
        
        # Create new player in our database
        new_player = Player(
            name=player_data.get("full_name", ""),
            position=position,
            team=player_data.get("team"),
            sleeper_id=request.sleeper_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(new_player)
        db.commit()
        db.refresh(new_player)
        
        # Sync historical data for this player
        try:
            historical_service = HistoricalDataService(db)
            sync_result = await historical_service.sync_specific_player(new_player.id)
            
            return {
                "message": "Player added successfully and historical data sync initiated",
                "player_id": new_player.id,
                "player_name": new_player.name,
                "position": position_str,
                "team": player_data.get("team"),
                "sync_result": sync_result
            }
        except Exception as sync_error:
            # Player was added but historical sync failed - that's OK
            return {
                "message": "Player added successfully but historical data sync encountered an issue",
                "player_id": new_player.id,
                "player_name": new_player.name,
                "position": position_str,
                "team": player_data.get("team"),
                "sync_error": str(sync_error)
            }
            
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to add player: {str(e)}")


@router.post("/{player_id}/analysis")
async def generate_player_analysis(
    player_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Generate AI-powered analysis for a specific player"""
    try:
        # Get player data from Sleeper
        all_players = await sleeper_service.get_all_players()
        
        if player_id not in all_players:
            raise HTTPException(status_code=404, detail="Player not found")
        
        player_data = all_players[player_id]
        player_name = player_data.get("full_name", "Unknown Player")
        
        # Get additional context data
        stats = await sleeper_service.get_player_stats(player_id)
        
        # Prepare comprehensive data for AI analysis
        analysis_data = {
            "player_info": player_data,
            "recent_stats": stats,
            "position": player_data.get("position"),
            "team": player_data.get("team"),
            "injury_status": player_data.get("injury_status"),
            "depth_chart_order": player_data.get("depth_chart_order"),
            "fantasy_positions": player_data.get("fantasy_positions", [])
        }
        
        # Generate AI analysis
        # ai_analysis = await ai_service.generate_player_analysis( # Temporarily disabled
        #     player_name=player_name,
        #     player_data=analysis_data
        # )
        ai_analysis = "AI analysis temporarily unavailable. Player analysis will be restored soon."
        
        return {
            "player_id": player_id,
            "player_name": player_name,
            "ai_analysis": ai_analysis,
            "generated_at": "2025-08-13T00:00:00Z",
            "analysis_type": "comprehensive"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate analysis: {str(e)}")


@router.get("/{player_id}/quick-analysis")
async def get_quick_player_analysis(
    player_id: str,
    include_ai: bool = Query(False, description="Include AI-generated analysis")
):
    """Get quick player analysis with optional AI insights"""
    try:
        # Get player data from Sleeper
        all_players = await sleeper_service.get_all_players()
        
        if player_id not in all_players:
            raise HTTPException(status_code=404, detail="Player not found")
        
        player_data = all_players[player_id]
        player_name = player_data.get("full_name", "Unknown Player")
        
        # Transform to our format
        transformed_player = {
            "id": int(player_id) if player_id.isdigit() else hash(player_id) % 100000,
            "name": player_name,
            "team": player_data.get("team_abbr") or player_data.get("team") or "FA",
            "position": player_data.get("position", "UNKNOWN"),
            "espn_id": str(player_data.get("espn_id")) if player_data.get("espn_id") else None,
            "yahoo_id": str(player_data.get("yahoo_id")) if player_data.get("yahoo_id") else None,
            "sleeper_id": player_id,
            "projected_points": None,
            "adp": None,
            "bye_week": player_data.get("bye_week"),
            "injury_status": player_data.get("injury_status") or "Healthy",
            "depth_chart_order": player_data.get("depth_chart_order"),
            "ai_analysis": None,
            "risk_level": None,
            "created_at": "2025-08-13T00:00:00Z",
            "updated_at": "2025-08-13T00:00:00Z"
        }
        
        # Add AI analysis if requested
        if include_ai:
            try:
                stats = await sleeper_service.get_player_stats(player_id)
                analysis_data = {
                    "player_info": player_data,
                    "recent_stats": stats,
                    "position": player_data.get("position"),
                    "team": player_data.get("team"),
                    "injury_status": player_data.get("injury_status"),
                }
                
                # ai_analysis = await ai_service.generate_player_analysis( # Temporarily disabled
                #     player_name=player_name,
                #     player_data=analysis_data
                # )
                ai_analysis = "AI analysis temporarily unavailable. Player analysis will be restored soon."
                transformed_player["ai_analysis"] = ai_analysis
                
                # Generate risk level based on analysis
                if "high risk" in ai_analysis.lower() or "injury" in ai_analysis.lower():
                    transformed_player["risk_level"] = "HIGH"
                elif "medium risk" in ai_analysis.lower() or "questionable" in ai_analysis.lower():
                    transformed_player["risk_level"] = "MEDIUM"
                else:
                    transformed_player["risk_level"] = "LOW"
                    
            except Exception as ai_error:
                # Don't fail the whole request if AI analysis fails
                transformed_player["ai_analysis"] = "AI analysis temporarily unavailable"
                transformed_player["risk_level"] = "UNKNOWN"
        
        return transformed_player
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get player analysis: {str(e)}")


# Enhanced Player Data Endpoints

@router.post("/sync")
async def sync_player_data(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Sync player data from external sources with enhanced analytics"""
    try:
        player_service = PlayerDataService(db)
        result = await player_service.sync_player_data()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to sync player data: {str(e)}")


@router.get("/enhanced/")
async def get_enhanced_players(
    position: Optional[str] = Query(None, description="Filter by position"),
    team: Optional[str] = Query(None, description="Filter by team"),
    injury_status: Optional[str] = Query(None, description="Filter by injury status"),
    min_projected_points: Optional[float] = Query(None, description="Minimum projected points"),
    max_risk_level: Optional[str] = Query(None, description="Maximum risk level (LOW, MEDIUM, HIGH)"),
    limit: int = Query(50, description="Number of players to return"),
    db: Session = Depends(get_db)
):
    """Get enhanced player data with advanced filtering"""
    try:
        player_service = PlayerDataService(db)
        players = player_service.get_players_by_criteria(
            position=position,
            team=team,
            injury_status=injury_status,
            min_projected_points=min_projected_points,
            max_risk_level=max_risk_level,
            limit=limit
        )
        
        # Convert to dict format
        players_data = []
        for player in players:
            player_dict = {
                "id": player.id,
                "name": player.name,
                "first_name": player.first_name,
                "last_name": player.last_name,
                "team": player.team,
                "position": player.position.value if player.position else None,
                "sleeper_id": player.sleeper_id,
                "age": player.age,
                "height": player.height,
                "weight": player.weight,
                "college": player.college,
                "years_exp": player.years_exp,
                "projected_points": player.projected_points,
                "projected_points_half_ppr": player.projected_points_half_ppr,
                "projected_points_standard": player.projected_points_standard,
                "adp": player.adp,
                "adp_trend": player.adp_trend,
                "target_share": player.target_share,
                "snap_count_percentage": player.snap_count_percentage,
                "injury_status": player.injury_status.value if player.injury_status else None,
                "injury_body_part": player.injury_body_part,
                "injury_notes": player.injury_notes,
                "trending_direction": player.trending_direction,
                "trending_count": player.trending_count,
                "risk_level": player.risk_level.value if player.risk_level else None,
                "ceiling_score": player.ceiling_score,
                "floor_score": player.floor_score,
                "consistency_rating": player.consistency_rating,
                "position_rank": player.position_rank,
                "tier": player.tier,
                "is_rookie": player.is_rookie,
                "is_handcuff": player.is_handcuff,
                "season_stats": player.season_stats,
                "last_game_stats": player.last_game_stats,
                "updated_at": player.updated_at.isoformat() if player.updated_at else None
            }
            players_data.append(player_dict)
        
        return {
            "players": players_data,
            "total": len(players_data),
            "filters_applied": {
                "position": position,
                "team": team,
                "injury_status": injury_status,
                "min_projected_points": min_projected_points,
                "max_risk_level": max_risk_level
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get enhanced players: {str(e)}")


@router.get("/enhanced/trending/{direction}")
async def get_enhanced_trending_players(
    direction: str,
    limit: int = Query(20, description="Number of players to return"),
    db: Session = Depends(get_db)
):
    """Get trending players with enhanced data"""
    try:
        if direction.upper() not in ["UP", "DOWN"]:
            raise HTTPException(status_code=400, detail="Direction must be 'UP' or 'DOWN'")
            
        player_service = PlayerDataService(db)
        players = player_service.get_trending_players(direction=direction, limit=limit)
        
        # Convert to dict format
        players_data = []
        for player in players:
            player_dict = {
                "id": player.id,
                "name": player.name,
                "team": player.team,
                "position": player.position.value if player.position else None,
                "projected_points": player.projected_points,
                "trending_count": player.trending_count,
                "trending_direction": player.trending_direction,
                "risk_level": player.risk_level.value if player.risk_level else None,
                "injury_status": player.injury_status.value if player.injury_status else None,
                "target_share": player.target_share,
                "ownership_percentage": player.ownership_percentage
            }
            players_data.append(player_dict)
        
        return {
            "trending_players": players_data,
            "direction": direction.upper(),
            "total": len(players_data)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get trending players: {str(e)}")


@router.get("/enhanced/injury-report")
async def get_injury_report(db: Session = Depends(get_db)):
    """Get comprehensive injury report with enhanced data"""
    try:
        player_service = PlayerDataService(db)
        injured_players = player_service.get_injury_report()
        
        # Convert to dict format
        injury_data = []
        for player in injured_players:
            player_dict = {
                "id": player.id,
                "name": player.name,
                "team": player.team,
                "position": player.position.value if player.position else None,
                "injury_status": player.injury_status.value if player.injury_status else None,
                "injury_body_part": player.injury_body_part,
                "injury_notes": player.injury_notes,
                "injury_updated_at": player.injury_updated_at.isoformat() if player.injury_updated_at else None,
                "practice_status": player.practice_status,
                "projected_points": player.projected_points,
                "risk_level": player.risk_level.value if player.risk_level else None,
                "depth_chart_order": player.depth_chart_order
            }
            injury_data.append(player_dict)
        
        return {
            "injury_report": injury_data,
            "total_injured": len(injury_data),
            "report_generated_at": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get injury report: {str(e)}")


@router.put("/enhanced/{player_id}/metrics")
async def calculate_player_metrics(
    player_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Calculate advanced metrics for a specific player"""
    try:
        player_service = PlayerDataService(db)
        result = await player_service.calculate_advanced_metrics(player_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to calculate metrics: {str(e)}")


@router.post("/enhanced/{player_id}/analysis")
async def generate_enhanced_analysis(
    player_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Generate enhanced AI analysis using comprehensive player data"""
    try:
        player_service = PlayerDataService(db)
        result = await player_service.generate_enhanced_analysis(player_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate enhanced analysis: {str(e)}")


@router.get("/enhanced/comparison")
async def compare_players(
    player_ids: str = Query(..., description="Comma-separated list of player IDs"),
    db: Session = Depends(get_db)
):
    """Compare multiple players with enhanced metrics"""
    try:
        player_id_list = [int(id.strip()) for id in player_ids.split(",")]
        
        if len(player_id_list) > 5:
            raise HTTPException(status_code=400, detail="Maximum 5 players can be compared at once")
        
        players = db.query(Player).filter(Player.id.in_(player_id_list)).all()
        
        if len(players) != len(player_id_list):
            raise HTTPException(status_code=404, detail="One or more players not found")
        
        # Convert to comparison format
        comparison_data = []
        for player in players:
            player_data = {
                "id": player.id,
                "name": player.name,
                "team": player.team,
                "position": player.position.value if player.position else None,
                "projected_points": player.projected_points,
                "adp": player.adp,
                "target_share": player.target_share,
                "snap_count_percentage": player.snap_count_percentage,
                "ceiling_score": player.ceiling_score,
                "floor_score": player.floor_score,
                "consistency_rating": player.consistency_rating,
                "risk_level": player.risk_level.value if player.risk_level else None,
                "injury_status": player.injury_status.value if player.injury_status else None,
                "tier": player.tier,
                "position_rank": player.position_rank,
                "season_stats": player.season_stats,
                "age": player.age,
                "years_exp": player.years_exp
            }
            comparison_data.append(player_data)
        
        return {
            "comparison": comparison_data,
            "players_compared": len(comparison_data),
            "comparison_date": datetime.utcnow().isoformat()
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid player ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compare players: {str(e)}")


@router.get("/database")
async def get_players_from_database(
    db: Session = Depends(get_db),
    position: Optional[str] = Query(None, description="Filter by position (QB, RB, WR, TE, K, DEF)"),
    team: Optional[str] = Query(None, description="Filter by team"),
    injury_status: Optional[str] = Query(None, description="Filter by injury status"),
    min_projected_points: Optional[float] = Query(None, description="Minimum projected points"),
    max_risk_level: Optional[str] = Query(None, description="Maximum risk level (LOW, MEDIUM, HIGH)"),
    page: int = Query(1, description="Page number (1-based)", ge=1),
    page_size: int = Query(50, description="Number of players per page", ge=1, le=200)
):
    """Get players from database with advanced filtering and pagination"""
    try:
        player_service = PlayerDataService(db)
        result = player_service.get_players_by_criteria(
            position=position,
            team=team,
            injury_status=injury_status,
            min_projected_points=min_projected_points,
            max_risk_level=max_risk_level,
            page=page,
            page_size=page_size
        )
        
        # Convert Player objects to dictionaries for JSON response
        players_data = []
        for player in result["players"]:
            player_data = {
                "id": player.id,
                "name": player.name,
                "team": player.team,
                "position": player.position.value if player.position else None,
                "projected_points": player.projected_points,
                "adp": player.adp,
                "bye_week": player.bye_week,
                "injury_status": player.injury_status.value if player.injury_status else None,
                "injury_body_part": player.injury_body_part,
                "target_share": player.target_share,
                "snap_count_percentage": player.snap_count_percentage,
                "depth_chart_order": player.depth_chart_order,
                "risk_level": player.risk_level.value if player.risk_level else None,
                "tier": player.tier,
                "position_rank": player.position_rank,
                "trending_direction": player.trending_direction,
                "consistency_rating": player.consistency_rating,
                "ceiling_score": player.ceiling_score,
                "floor_score": player.floor_score,
                "age": player.age,
                "years_exp": player.years_exp,
                "created_at": player.created_at.isoformat() if player.created_at else None,
                "updated_at": player.updated_at.isoformat() if player.updated_at else None
            }
            players_data.append(player_data)
        
        return {
            "players": players_data,
            "pagination": result["pagination"]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get players from database: {str(e)}")