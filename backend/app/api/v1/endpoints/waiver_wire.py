"""
Waiver Wire API Endpoints

RESTful endpoints for waiver wire recommendations, analysis, and weekly insights.
"""

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.api.deps import get_db, get_current_active_user
from app.models.user import User
from app.services.waiver_wire_service import WaiverWireService
from app.services.notification_service import notify_trending_adds

router = APIRouter()


@router.get("/league-aware-recommendations/{league_id}")
async def get_league_aware_waiver_recommendations(
    league_id: int,
    week: int = Query(..., description="NFL week number"),
    position: Optional[str] = Query(None, description="Filter by position (QB, RB, WR, TE)"),
    limit: int = Query(20, description="Maximum recommendations to return"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get waiver wire recommendations tailored for your specific league"""
    try:
        from app.utils.league_data_loader import get_league_info
        league_info = get_league_info(league_id)
        
        waiver_service = WaiverWireService(db)
        
        # Use league's season instead of default
        season = league_info["season"]
        
        if position:
            recommendations = await waiver_service.get_recommendations_by_position(
                position.upper(), week, season, limit
            )
        else:
            recommendations = await waiver_service.generate_weekly_recommendations(
                week, season, limit
            )
        
        return {
            "league_info": {
                "id": league_info["id"],
                "name": league_info["name"],
                "platform": league_info["platform"],
                "scoring_format": league_info["scoring_format"],
                "season": league_info["season"]
            },
            "week": week,
            "season": season,
            "position_filter": position,
            "recommendations": recommendations,
            "total_found": len(recommendations),
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get league-aware waiver recommendations: {str(e)}")


class WaiverAnalysisRequest(BaseModel):
    roster_player_ids: List[int]
    week: Optional[int] = None
    season: int = 2025


class AlertSubscriptionRequest(BaseModel):
    position: Optional[str] = None
    min_ownership: float = 0.0
    max_ownership: float = 50.0
    priority_levels: List[str] = ["urgent", "high"]


@router.get("/recommendations")
async def get_waiver_recommendations(
    week: int = Query(..., description="NFL week number"),
    season: int = Query(2025, description="NFL season"),
    position: Optional[str] = Query(None, description="Filter by position (QB, RB, WR, TE)"),
    priority: Optional[str] = Query(None, description="Filter by priority (urgent, high, medium, low, watch)"),
    limit: int = Query(20, description="Maximum recommendations to return"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get waiver wire recommendations for a specific week.

    Sourced from Sleeper's live trending-add feed rather than the local
    Player/WaiverWireRecommendation tables, which have no ingestion pipeline
    behind them and are empty for a fresh deployment -- see
    WaiverWireService.get_live_trending_recommendations for details.
    """
    try:
        waiver_service = WaiverWireService(db)

        recommendations = await waiver_service.get_live_trending_recommendations(
            position=position, priority=priority, limit=limit
        )

        # Lazily generate in-app notifications for genuinely new, high-signal
        # trending adds -- derived from this same live Sleeper response, not
        # a separate/fabricated check. See notification_service for why this
        # is wired here (request-driven) rather than on a Celery schedule.
        notify_trending_adds(db, current_user.id, recommendations)

        return {
            "week": week,
            "season": season,
            "position_filter": position,
            "priority_filter": priority,
            "recommendations": recommendations,
            "total_found": len(recommendations),
            "generated_at": datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get waiver recommendations: {str(e)}")


@router.get("/recommendations/priority/{priority_level}")
async def get_recommendations_by_priority(
    priority_level: str,
    week: int = Query(..., description="NFL week number"),
    season: int = Query(2025, description="NFL season"),
    limit: int = Query(10, description="Maximum recommendations to return"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get waiver recommendations by priority level (urgent, high, medium, low, watch)"""
    try:
        from app.models.waiver_wire import WaiverWireRecommendation, Priority
        from sqlalchemy import and_, desc
        
        # Validate priority level
        valid_priorities = ["urgent", "high", "medium", "low", "watch"]
        if priority_level.lower() not in valid_priorities:
            raise HTTPException(status_code=400, detail=f"Invalid priority. Must be one of: {valid_priorities}")
        
        # Query recommendations by priority
        recommendations = db.query(WaiverWireRecommendation).filter(
            and_(
                WaiverWireRecommendation.week == week,
                WaiverWireRecommendation.season == season,
                WaiverWireRecommendation.priority == Priority(priority_level.upper())
            )
        ).order_by(desc(WaiverWireRecommendation.confidence_score)).limit(limit).all()
        
        waiver_service = WaiverWireService(db)
        formatted_recs = [waiver_service._format_recommendation(rec) for rec in recommendations]
        
        return {
            "priority_level": priority_level,
            "week": week,
            "season": season,
            "recommendations": formatted_recs,
            "total_found": len(formatted_recs)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get priority recommendations: {str(e)}")


@router.post("/analyze-roster")
async def analyze_roster_moves(
    request: WaiverAnalysisRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Analyze current roster for optimal add/drop moves"""
    try:
        waiver_service = WaiverWireService(db)
        
        # Use current week if not specified
        week = request.week or datetime.now().isocalendar()[1]
        
        analysis = await waiver_service.analyze_add_drop_candidates(
            request.roster_player_ids,
            week,
            request.season
        )
        
        return {
            "roster_analysis": analysis,
            "recommendations_summary": {
                "add_count": len(analysis.get("add_candidates", [])),
                "drop_count": len(analysis.get("drop_candidates", [])),
                "priority_adds": len([
                    rec for rec in analysis.get("add_candidates", [])
                    if rec.get("priority") in ["urgent", "high"]
                ])
            },
            "analyzed_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze roster: {str(e)}")


@router.get("/trending")
async def get_trending_players(
    week: int = Query(..., description="NFL week number"),
    season: int = Query(2025, description="NFL season"),
    position: Optional[str] = Query(None, description="Filter by position"),
    trend_direction: str = Query("up", description="Trend direction (up, down, both)"),
    limit: int = Query(15, description="Maximum players to return"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get trending players on the waiver wire"""
    try:
        from app.models.waiver_wire import WaiverWireTrend
        from app.models.player import Player, Position
        from sqlalchemy import and_, desc
        
        # Build query
        query = db.query(WaiverWireTrend, Player).join(Player).filter(
            and_(
                WaiverWireTrend.week == week,
                WaiverWireTrend.season == season
            )
        )
        
        # Filter by position if specified
        if position:
            query = query.filter(Player.position == Position(position.upper()))
        
        # Filter by trend direction
        if trend_direction == "up":
            query = query.filter(WaiverWireTrend.ownership_change > 2.0)
        elif trend_direction == "down":
            query = query.filter(WaiverWireTrend.ownership_change < -2.0)
        # "both" includes all trends
        
        # Order by pickup rate and ownership change
        trends = query.order_by(
            desc(WaiverWireTrend.pickup_rate),
            desc(WaiverWireTrend.ownership_change)
        ).limit(limit).all()
        
        trending_players = []
        for trend, player in trends:
            trending_players.append({
                "player_id": player.id,
                "player_name": player.name,
                "position": player.position.value,
                "team": player.team,
                "ownership_change": trend.ownership_change,
                "pickup_rate": trend.pickup_rate,
                "drop_rate": trend.drop_rate,
                "recent_performance": trend.recent_performance,
                "upcoming_matchup_rating": trend.upcoming_matchup_rating,
                "target_share_trend": trend.target_share_trend,
                "snap_count_trend": trend.snap_count_trend
            })
        
        return {
            "week": week,
            "season": season,
            "trend_direction": trend_direction,
            "position_filter": position,
            "trending_players": trending_players,
            "total_found": len(trending_players)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get trending players: {str(e)}")


@router.get("/alerts")
async def get_waiver_alerts(
    active_only: bool = Query(True, description="Only return active alerts"),
    priority: Optional[str] = Query(None, description="Filter by priority level"),
    limit: int = Query(20, description="Maximum alerts to return"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get waiver wire alerts and time-sensitive notifications"""
    try:
        from app.models.waiver_wire import WaiverWireAlert, Priority
        from sqlalchemy import and_, desc
        
        # Build query
        query = db.query(WaiverWireAlert)
        
        if active_only:
            query = query.filter(WaiverWireAlert.is_active == True)
        
        if priority:
            query = query.filter(WaiverWireAlert.urgency == Priority(priority.upper()))
        
        # Order by urgency and creation time
        alerts = query.order_by(
            desc(WaiverWireAlert.urgency),
            desc(WaiverWireAlert.created_at)
        ).limit(limit).all()
        
        formatted_alerts = []
        for alert in alerts:
            formatted_alerts.append({
                "id": alert.id,
                "player_id": alert.player_id,
                "player_name": alert.player.name,
                "position": alert.player.position.value,
                "team": alert.player.team,
                "alert_type": alert.alert_type,
                "title": alert.title,
                "message": alert.message,
                "urgency": alert.urgency.value,
                "trigger_event": alert.trigger_event,
                "expires_at": alert.expires_at.isoformat() if alert.expires_at else None,
                "created_at": alert.created_at.isoformat(),
                "is_active": alert.is_active
            })
        
        return {
            "alerts": formatted_alerts,
            "total_found": len(formatted_alerts),
            "active_only": active_only,
            "priority_filter": priority
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get waiver alerts: {str(e)}")


@router.post("/generate-recommendations")
async def generate_weekly_recommendations(
    background_tasks: BackgroundTasks,
    week: int = Query(..., description="NFL week number"),
    season: int = Query(2025, description="NFL season"),
    force_refresh: bool = Query(False, description="Force regeneration of recommendations"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Generate or refresh waiver wire recommendations for a week"""
    try:
        waiver_service = WaiverWireService(db)
        
        if force_refresh:
            # Run synchronously for immediate results
            recommendations = await waiver_service.generate_weekly_recommendations(week, season)
            
            return {
                "success": True,
                "message": "Waiver recommendations generated successfully",
                "week": week,
                "season": season,
                "recommendations_count": len(recommendations),
                "top_recommendations": recommendations[:5],
                "generated_at": datetime.utcnow().isoformat()
            }
        else:
            # Run in background for large-scale generation
            background_tasks.add_task(
                waiver_service.generate_weekly_recommendations,
                week,
                season
            )
            
            return {
                "success": True,
                "message": "Waiver recommendation generation started in background",
                "week": week,
                "season": season,
                "started_at": datetime.utcnow().isoformat()
            }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate recommendations: {str(e)}")


@router.get("/player/{player_id}/evaluation")
async def get_player_waiver_evaluation(
    player_id: int,
    week: int = Query(..., description="NFL week number"),
    season: int = Query(2025, description="NFL season"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get detailed waiver wire evaluation for a specific player"""
    try:
        from app.models.player import Player
        
        # Get player
        player = db.query(Player).filter(Player.id == player_id).first()
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")
        
        waiver_service = WaiverWireService(db)
        
        # Get player evaluation
        evaluation = await waiver_service._evaluate_player_for_waiver(player, week, season)
        
        if not evaluation:
            return {
                "player_id": player_id,
                "player_name": player.name,
                "message": "No waiver evaluation available for this player",
                "week": week,
                "season": season
            }
        
        # Get any existing recommendation
        from app.models.waiver_wire import WaiverWireRecommendation
        existing_rec = db.query(WaiverWireRecommendation).filter(
            and_(
                WaiverWireRecommendation.player_id == player_id,
                WaiverWireRecommendation.week == week,
                WaiverWireRecommendation.season == season
            )
        ).first()
        
        return {
            "player_evaluation": evaluation,
            "existing_recommendation": waiver_service._format_recommendation(existing_rec) if existing_rec else None,
            "week": week,
            "season": season,
            "evaluated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get player evaluation: {str(e)}")


@router.get("/insights/weekly-summary")
async def get_weekly_waiver_insights(
    week: int = Query(..., description="NFL week number"),
    season: int = Query(2025, description="NFL season"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get comprehensive weekly waiver wire insights and summary"""
    try:
        from app.models.waiver_wire import WaiverWireRecommendation, Priority
        from sqlalchemy import func, and_
        
        # Get recommendation counts by priority
        priority_counts = db.query(
            WaiverWireRecommendation.priority,
            func.count(WaiverWireRecommendation.id)
        ).filter(
            and_(
                WaiverWireRecommendation.week == week,
                WaiverWireRecommendation.season == season
            )
        ).group_by(WaiverWireRecommendation.priority).all()
        
        # Get top recommendations by position
        waiver_service = WaiverWireService(db)
        top_by_position = {}
        
        for position in ["QB", "RB", "WR", "TE"]:
            top_recs = await waiver_service.get_recommendations_by_position(
                position, week, season, 3
            )
            top_by_position[position] = top_recs
        
        # Format priority counts
        priority_summary = {}
        for priority, count in priority_counts:
            priority_summary[priority.value] = count
        
        return {
            "week": week,
            "season": season,
            "summary": {
                "total_recommendations": sum(priority_summary.values()),
                "priority_breakdown": priority_summary,
                "top_recommendations_by_position": top_by_position
            },
            "key_insights": [
                f"Found {priority_summary.get('urgent', 0)} urgent pickup opportunities",
                f"Generated {sum(priority_summary.values())} total recommendations across all positions",
                f"Top RB target: {top_by_position.get('RB', [{}])[0].get('player_name', 'None available')}" if top_by_position.get('RB') else "No RB recommendations"
            ],
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get weekly insights: {str(e)}")


@router.post("/alerts/subscribe")
async def subscribe_to_alerts(
    request: AlertSubscriptionRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Subscribe to waiver wire alerts based on criteria"""
    try:
        # This would integrate with a notification system
        # For now, return the subscription preferences
        
        return {
            "success": True,
            "message": "Alert subscription created successfully",
            "subscription": {
                "user_id": current_user.id,
                "position_filter": request.position,
                "ownership_range": {
                    "min": request.min_ownership,
                    "max": request.max_ownership
                },
                "priority_levels": request.priority_levels,
                "created_at": datetime.utcnow().isoformat()
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create alert subscription: {str(e)}")