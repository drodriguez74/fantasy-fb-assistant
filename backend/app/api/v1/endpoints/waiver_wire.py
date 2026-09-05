"""
Waiver Wire API Endpoints

RESTful endpoints for waiver wire recommendations, analysis, and weekly insights.
"""

import json
import logging
from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.api.deps import get_db, get_current_active_user
from app.models.user import User
from app.models.player import Player
from app.services.waiver_wire_service import WaiverWireService
from app.services.notification_service import notify_trending_adds
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter()


async def _fetch_connected_roster_and_settings(
    db: Session, current_user: User, league_id: int
):
    """Best-effort real roster + league-settings fetch for a connected
    league, so /league-aware-recommendations/{league_id} can pass real
    personalization data into get_live_trending_recommendations instead of
    calling it unweighted.

    Reuses the exact platform roster-fetch calls already used elsewhere in
    this codebase (post_draft.py's /import-roster/{league_id} does the same
    ESPN/Yahoo/Sleeper branching) rather than inventing a new one. Returns
    (None, None) on any failure (no connected league with this id, no
    team_id configured, platform call error, etc.) -- callers should treat
    that as "fall back to unweighted" rather than raising, since this is a
    best-effort personalization layer, not a hard requirement of the
    endpoint.
    """
    try:
        user_service = UserService(db)
        user_league = user_service.get_user_league(current_user.id, league_id)
        if not user_league or not user_league.team_id:
            return None, None

        platform = user_league.platform.value.upper()
        roster_players: List[Dict[str, Any]] = []

        if platform == "ESPN":
            from app.services.espn_service_enhanced import espn_service_enhanced

            roster_data = await espn_service_enhanced.get_team_roster(
                league_id=user_league.league_id,
                team_id=int(user_league.team_id),
                season=user_league.season,
                swid=user_league.espn_swid,
                espn_s2=user_league.espn_s2
            )
            if "error" in roster_data:
                return None, None
            roster_players = [
                {"position": p.get("position", "UNKNOWN")}
                for p in roster_data.get("players", [])
            ]

        elif platform == "YAHOO":
            from app.services.yahoo_service import yahoo_service

            roster_data = await yahoo_service.get_team_roster(user_league.team_id)
            if "error" in roster_data:
                return None, None
            roster_players = [
                {"position": p.get("position", "UNKNOWN")}
                for p in roster_data.get("players", [])
            ]

        elif platform == "SLEEPER":
            from app.services.sleeper_service import SleeperService

            sleeper = SleeperService()
            rosters = await sleeper.get_league_rosters(user_league.league_id)
            if rosters and isinstance(rosters, list) and isinstance(rosters[0], dict) and "error" in rosters[0]:
                return None, None

            target_roster = next(
                (
                    r for r in rosters
                    if str(r.get("owner_id")) == str(user_league.team_id)
                    or str(r.get("roster_id")) == str(user_league.team_id)
                ),
                None
            )
            if not target_roster:
                return None, None

            # Best-effort position resolution against our own (sparse) local
            # Player table by sleeper_id -- same honest-best-effort pattern
            # used for bye-week lookups in WaiverWireService. A Sleeper
            # player id with no local match is simply skipped rather than
            # guessed at.
            for sleeper_player_id in target_roster.get("players") or []:
                local_match = db.query(Player).filter(
                    Player.sleeper_id == str(sleeper_player_id)
                ).first()
                if local_match and local_match.position:
                    roster_players.append({"position": local_match.position.value})
        else:
            return None, None

        if not roster_players:
            return None, None

        raw_starters = None
        if user_league.roster_positions:
            try:
                parsed = json.loads(user_league.roster_positions)
                raw_starters = parsed.get("starters")
            except (json.JSONDecodeError, AttributeError):
                raw_starters = None

        league_settings = {
            "starters": raw_starters or {},
            "scoring_format": user_league.scoring_format,
            "points_per_reception": user_league.points_per_reception,
        }

        return roster_players, league_settings

    except Exception as e:
        logger.warning(f"Could not fetch connected roster/settings for league {league_id}: {str(e)}")
        return None, None


@router.get("/league-aware-recommendations/{league_id}")
async def get_league_aware_waiver_recommendations(
    league_id: int,
    week: int = Query(..., description="NFL week number"),
    position: Optional[str] = Query(None, description="Filter by position (QB, RB, WR, TE)"),
    limit: int = Query(20, description="Maximum recommendations to return"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get waiver wire recommendations tailored for your specific league.

    Sourced from the same live Sleeper trending-add feed as GET
    /recommendations (see WaiverWireService.get_live_trending_recommendations
    -- the local Player/WaiverWireRecommendation tables this endpoint used
    to read from have no ingestion pipeline and are empty in practice), but
    additionally personalized with this user's real connected roster and
    league settings for `league_id` when that roster can actually be
    fetched (real per-league starter requirements -> roster-need boosting,
    real bye-week flags, honest scoring-format context). Falls back to the
    same unweighted live recommendations if the roster can't be fetched
    (no connected league with this id, no team_id configured yet, or the
    platform call fails) -- this personalization layer is best-effort, not
    a hard requirement of the endpoint.
    """
    try:
        from app.utils.league_data_loader import get_league_info
        league_info = get_league_info(league_id)

        waiver_service = WaiverWireService(db)

        user_roster, league_settings = await _fetch_connected_roster_and_settings(
            db, current_user, league_id
        )

        recommendations = await waiver_service.get_live_trending_recommendations(
            position=position,
            limit=limit,
            user_roster=user_roster,
            league_settings=league_settings,
        )

        notify_trending_adds(db, current_user.id, recommendations)

        return {
            "league_info": {
                "id": league_info["id"],
                "name": league_info["name"],
                "platform": league_info["platform"],
                "scoring_format": league_info["scoring_format"],
                "season": league_info["season"]
            },
            "week": week,
            "season": league_info["season"],
            "position_filter": position,
            "personalized": user_roster is not None,
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


@router.get("/recommendations")
async def get_waiver_recommendations(
    week: int = Query(..., description="NFL week number"),
    season: int = Query(2025, description="NFL season"),
    position: Optional[str] = Query(None, description="Filter by position (QB, RB, WR, TE)"),
    priority: Optional[str] = Query(None, description="Filter by priority (urgent, high, medium, low, watch)"),
    limit: int = Query(20, description="Maximum recommendations to return"),
    league_id: Optional[int] = Query(
        None,
        description=(
            "Optional connected UserLeague id. This endpoint has no other way "
            "to know which of the user's leagues/rosters to personalize "
            "against, so personalization is opt-in via this param -- when "
            "omitted this stays the plain unweighted live feed."
        ),
    ),
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

        user_roster, league_settings = (None, None)
        if league_id is not None:
            user_roster, league_settings = await _fetch_connected_roster_and_settings(
                db, current_user, league_id
            )

        recommendations = await waiver_service.get_live_trending_recommendations(
            position=position,
            priority=priority,
            limit=limit,
            user_roster=user_roster,
            league_settings=league_settings,
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
            "personalized": user_roster is not None,
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
    week: int = Query(..., description="NFL week number (informational only -- see note below)"),
    season: int = Query(2025, description="NFL season (informational only -- see note below)"),
    position: Optional[str] = Query(None, description="Filter by position"),
    trend_direction: str = Query("up", description="Trend direction (up, down, both)"),
    limit: int = Query(15, description="Maximum players to return"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get trending players on the waiver wire.

    Sourced from Sleeper's live trending add/drop feed rather than the
    WaiverWireTrend table -- nothing in this codebase has ever written to
    that table (it exists in the schema but has no ingestion pipeline), so
    it always returned empty. See WaiverWireService.get_live_trending_players
    for why real historical backfill isn't a viable small extension here
    (WaiverWireTrend.player_id FKs to the mostly-empty local Player table).

    This is a live snapshot of real 24h Sleeper add/drop activity -- the
    same real signal GET /recommendations uses for "add" only, extended
    here to also cover "drop" trends -- not a historical trend line.
    `week`/`season` are accepted for URL consistency with the rest of this
    router but don't scope the underlying Sleeper feed, which is always
    "right now."
    """
    try:
        waiver_service = WaiverWireService(db)

        trending_players = await waiver_service.get_live_trending_players(
            trend_direction=trend_direction, position=position, limit=limit
        )

        return {
            "week": week,
            "season": season,
            "trend_direction": trend_direction,
            "position_filter": position,
            "trending_players": trending_players,
            "total_found": len(trending_players),
            "generated_at": datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get trending players: {str(e)}")


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
        from sqlalchemy import and_
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


# NOTE: POST /alerts/subscribe (and GET /alerts, which queried the
# never-populated WaiverWireAlert table) have been removed. Both were
# decommissioned rather than built out further:
#
# - /alerts/subscribe was an explicit non-persisting stub (its own comment
#   said "this would integrate with a notification system") with zero
#   frontend callers -- confirmed via a repo-wide search of api.ts and every
#   page/component.
# - This app now has a real, working in-app notification center
#   (app.models.notification.Notification, app.services.notification_service,
#   GET /notifications/*, wired to the navbar bell) that already delivers
#   the actual underlying value ("tell me when a waiver-relevant player
#   starts trending") automatically, as a side effect of every
#   GET /waiver-wire/recommendations call -- see notify_trending_adds above.
#   A separate opt-in "subscription" step would be redundant with something
#   that already fires proactively, and building real subscription-criteria
#   persistence (position/ownership-range filters, an unsubscribe path,
#   etc.) is a distinct, larger feature this pass didn't build.
#
# The frontend's Alerts tab (WaiverWirePage.tsx) now reads directly from the
# real GET /notifications/ endpoint instead of this dead stub.