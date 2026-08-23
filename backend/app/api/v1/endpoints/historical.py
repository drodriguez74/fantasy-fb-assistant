from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from typing import List, Optional
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_active_user
from app.models.user import User
from app.services.historical_data_service import HistoricalDataService
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()


class HistoricalSyncRequest(BaseModel):
    seasons: Optional[List[int]] = None
    force_refresh: bool = False


class PlayerComparisonRequest(BaseModel):
    player_ids: List[int]
    seasons: int = 3


@router.post("/sync")
async def sync_historical_data(
    background_tasks: BackgroundTasks,
    request: HistoricalSyncRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Sync historical performance data from external sources"""
    try:
        historical_service = HistoricalDataService(db)
        
        # Run sync directly to see any errors (for debugging)
        if request.force_refresh:
            # Run synchronously for debugging
            result = await historical_service.sync_historical_data(request.seasons)
            return {
                "success": True,
                "message": "Historical data sync completed",
                "result": result,
                "seasons": request.seasons or "last 3 seasons",
                "completed_at": datetime.utcnow().isoformat()
            }
        else:
            # Run sync in background for large datasets
            background_tasks.add_task(
                historical_service.sync_historical_data,
                request.seasons
            )
            
            return {
                "success": True,
                "message": "Historical data sync started in background",
                "seasons": request.seasons or "last 3 seasons",
                "started_at": datetime.utcnow().isoformat()
            }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start historical sync: {str(e)}")


@router.get("/players/{player_id}/summary")
async def get_player_historical_summary(
    player_id: int,
    seasons: int = Query(3, description="Number of seasons to analyze"),
    db: Session = Depends(get_db)
):
    """Get comprehensive historical summary for a player"""
    try:
        historical_service = HistoricalDataService(db)
        summary = await historical_service.get_player_historical_summary(player_id, seasons)
        
        if "error" in summary:
            raise HTTPException(status_code=404, detail=summary["error"])
        
        return summary
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get player historical summary: {str(e)}")


@router.get("/players/{player_id}/trends")
async def get_player_trends(
    player_id: int,
    db: Session = Depends(get_db)
):
    """Get player performance trends"""
    try:
        from app.models.historical_performance import PlayerTrend
        from app.models.player import Player
        
        # Check if player exists
        player = db.query(Player).filter(Player.id == player_id).first()
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")
        
        # Get all trends for the player
        trends = db.query(PlayerTrend).filter(
            PlayerTrend.player_id == player_id
        ).order_by(PlayerTrend.last_updated.desc()).all()
        
        trends_data = []
        for trend in trends:
            trends_data.append({
                "trend_type": trend.trend_type,
                "trend_direction": trend.trend_direction,
                "trend_strength": trend.trend_strength,
                "performance_change": trend.performance_change,
                "sustainability_score": trend.sustainability_score,
                "confidence_level": trend.confidence_level,
                "sample_size": trend.sample_size,
                "start_date": trend.trend_start_date.isoformat() if trend.trend_start_date else None,
                "end_date": trend.trend_end_date.isoformat() if trend.trend_end_date else None,
                "last_updated": trend.last_updated.isoformat()
            })
        
        return {
            "player_id": player_id,
            "player_name": player.name,
            "trends": trends_data,
            "total_trends": len(trends_data)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get player trends: {str(e)}")


@router.get("/players/{player_id}/weekly-performance/{season}")
async def get_weekly_performance(
    player_id: int,
    season: int,
    db: Session = Depends(get_db)
):
    """Get weekly performance data for a player in a specific season"""
    try:
        from app.models.historical_performance import PlayerHistoricalPerformance
        from app.models.player import Player
        from sqlalchemy import and_
        
        # Check if player exists
        player = db.query(Player).filter(Player.id == player_id).first()
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")
        
        # Get weekly performances
        performances = db.query(PlayerHistoricalPerformance).filter(
            and_(
                PlayerHistoricalPerformance.player_id == player_id,
                PlayerHistoricalPerformance.season == season,
                PlayerHistoricalPerformance.week.isnot(None)
            )
        ).order_by(PlayerHistoricalPerformance.week).all()
        
        weekly_data = []
        for perf in performances:
            weekly_data.append({
                "week": perf.week,
                "fantasy_points_ppr": perf.fantasy_points_ppr,
                "fantasy_points_half_ppr": perf.fantasy_points_half_ppr,
                "fantasy_points_standard": perf.fantasy_points_standard,
                "opponent_team": perf.opponent_team,
                "game_location": perf.game_location.value if perf.game_location else None,
                "game_date": perf.game_date.isoformat() if perf.game_date else None,
                "snap_percentage": perf.snap_percentage,
                "target_share": perf.target_share,
                "passing_stats": perf.passing_stats,
                "rushing_stats": perf.rushing_stats,
                "receiving_stats": perf.receiving_stats,
                "injury_designation": perf.injury_designation
            })
        
        return {
            "player_id": player_id,
            "player_name": player.name,
            "season": season,
            "weekly_performances": weekly_data,
            "total_games": len(weekly_data)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get weekly performance: {str(e)}")


@router.get("/positions/{position}/analysis")
async def get_position_historical_analysis(
    position: str,
    seasons: int = Query(3, description="Number of seasons to analyze"),
    db: Session = Depends(get_db)
):
    """Get historical analysis for all players at a position"""
    try:
        historical_service = HistoricalDataService(db)
        analysis = await historical_service.get_position_historical_analysis(position.upper(), seasons)
        
        if "error" in analysis:
            raise HTTPException(status_code=400, detail=analysis["error"])
        
        return analysis
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get position analysis: {str(e)}")


@router.post("/players/compare")
async def compare_players_historically(
    request: PlayerComparisonRequest,
    db: Session = Depends(get_db)
):
    """Compare multiple players' historical performance"""
    try:
        if len(request.player_ids) < 2:
            raise HTTPException(status_code=400, detail="At least 2 players required for comparison")
        
        if len(request.player_ids) > 5:
            raise HTTPException(status_code=400, detail="Maximum 5 players can be compared")
        
        historical_service = HistoricalDataService(db)
        comparison = await historical_service.compare_players_historically(request.player_ids, request.seasons)
        
        if "error" in comparison:
            raise HTTPException(status_code=400, detail=comparison["error"])
        
        return comparison
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compare players: {str(e)}")


@router.get("/players/{player_id}/season-summaries")
async def get_player_season_summaries(
    player_id: int,
    db: Session = Depends(get_db)
):
    """Get all season summaries for a player"""
    try:
        from app.models.historical_performance import PlayerSeasonSummary
        from app.models.player import Player
        
        # Check if player exists
        player = db.query(Player).filter(Player.id == player_id).first()
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")
        
        # Get season summaries
        summaries = db.query(PlayerSeasonSummary).filter(
            PlayerSeasonSummary.player_id == player_id
        ).order_by(PlayerSeasonSummary.season.desc()).all()
        
        summaries_data = []
        for summary in summaries:
            summaries_data.append({
                "season": summary.season,
                "games_played": summary.games_played,
                "games_started": summary.games_started,
                "total_fantasy_points_ppr": summary.total_fantasy_points_ppr,
                "avg_fantasy_points_ppr": summary.avg_fantasy_points_ppr,
                "weekly_ceiling": summary.weekly_ceiling,
                "weekly_floor": summary.weekly_floor,
                "consistency_score": summary.consistency_score,
                "boom_weeks": summary.boom_weeks,
                "bust_weeks": summary.bust_weeks,
                "first_half_avg": summary.first_half_avg,
                "second_half_avg": summary.second_half_avg,
                "trend_direction": summary.trend_direction,
                "position_finish": summary.position_finish,
                "health_grade": summary.health_grade,
                "injury_weeks_missed": summary.injury_weeks_missed
            })
        
        return {
            "player_id": player_id,
            "player_name": player.name,
            "position": player.position.value,
            "season_summaries": summaries_data,
            "total_seasons": len(summaries_data)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get season summaries: {str(e)}")


@router.get("/matchups/{team_a}/{team_b}")
async def get_matchup_history(
    team_a: str,
    team_b: str,
    seasons: int = Query(3, description="Number of seasons to analyze"),
    db: Session = Depends(get_db)
):
    """Get historical matchup data between two teams"""
    try:
        from app.models.historical_performance import MatchupHistory
        from sqlalchemy import or_, and_
        from datetime import datetime
        
        current_year = datetime.now().year
        season_range = list(range(current_year - seasons + 1, current_year + 1))
        
        # Get matchup history
        matchups = db.query(MatchupHistory).filter(
            and_(
                or_(
                    and_(MatchupHistory.team_a == team_a.upper(), MatchupHistory.team_b == team_b.upper()),
                    and_(MatchupHistory.team_a == team_b.upper(), MatchupHistory.team_b == team_a.upper())
                ),
                MatchupHistory.season.in_(season_range)
            )
        ).order_by(MatchupHistory.season.desc(), MatchupHistory.week.desc()).all()
        
        matchup_data = []
        for matchup in matchups:
            matchup_data.append({
                "season": matchup.season,
                "week": matchup.week,
                "game_date": matchup.game_date.isoformat() if matchup.game_date else None,
                "team_a": matchup.team_a,
                "team_b": matchup.team_b,
                "final_score_a": matchup.final_score_a,
                "final_score_b": matchup.final_score_b,
                "total_points": matchup.total_points,
                "game_script": matchup.game_script,
                "weather": matchup.weather,
                "dome_game": matchup.dome_game,
                "fantasy_points_allowed": {
                    "qb_a": matchup.qb_fantasy_allowed_a,
                    "qb_b": matchup.qb_fantasy_allowed_b,
                    "rb_a": matchup.rb_fantasy_allowed_a,
                    "rb_b": matchup.rb_fantasy_allowed_b,
                    "wr_a": matchup.wr_fantasy_allowed_a,
                    "wr_b": matchup.wr_fantasy_allowed_b,
                    "te_a": matchup.te_fantasy_allowed_a,
                    "te_b": matchup.te_fantasy_allowed_b
                }
            })
        
        # Calculate averages
        total_games = len(matchup_data)
        avg_total_points = sum(m["total_points"] for m in matchup_data if m["total_points"]) / total_games if total_games > 0 else 0
        
        return {
            "team_a": team_a.upper(),
            "team_b": team_b.upper(),
            "seasons_analyzed": seasons,
            "total_matchups": total_games,
            "avg_total_points": avg_total_points,
            "matchup_history": matchup_data
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get matchup history: {str(e)}")


@router.get("/stats/overview")
async def get_historical_data_overview(
    db: Session = Depends(get_db)
):
    """Get overview of available historical data"""
    try:
        from app.models.historical_performance import (
            PlayerHistoricalPerformance, 
            PlayerSeasonSummary, 
            PlayerTrend, 
            MatchupHistory
        )
        from sqlalchemy import func, distinct
        from sqlalchemy.exc import OperationalError
        
        # Initialize with default values in case tables don't exist
        performance_count = 0
        summary_count = 0 
        trend_count = 0
        matchup_count = 0
        season_list = []
        players_with_data = 0
        latest_update = None
        
        try:
            # Count records by type with error handling for non-existent tables
            performance_count = db.query(func.count(PlayerHistoricalPerformance.id)).scalar() or 0
        except OperationalError:
            performance_count = 0
            
        try:
            summary_count = db.query(func.count(PlayerSeasonSummary.id)).scalar() or 0
        except OperationalError:
            summary_count = 0
            
        try:
            trend_count = db.query(func.count(PlayerTrend.id)).scalar() or 0
        except OperationalError:
            trend_count = 0
            
        try:
            matchup_count = db.query(func.count(MatchupHistory.id)).scalar() or 0
        except OperationalError:
            matchup_count = 0
        
        try:
            # Get season coverage
            seasons_with_data = db.query(distinct(PlayerHistoricalPerformance.season)).order_by(PlayerHistoricalPerformance.season.desc()).all()
            season_list = [s[0] for s in seasons_with_data if s[0]]
        except OperationalError:
            season_list = []
        
        try:
            # Get players with historical data
            players_with_data = db.query(func.count(distinct(PlayerHistoricalPerformance.player_id))).scalar() or 0
        except OperationalError:
            players_with_data = 0
        
        try:
            # Get most recent sync
            latest_update = db.query(func.max(PlayerHistoricalPerformance.last_updated)).scalar()
        except OperationalError:
            latest_update = None
        
        # Handle timezone-aware datetime comparison
        data_freshness = "stale"
        if latest_update:
            try:
                from datetime import timezone
                now = datetime.now(timezone.utc)
                if latest_update.tzinfo is None:
                    # Make latest_update timezone-aware
                    latest_update = latest_update.replace(tzinfo=timezone.utc)
                days_diff = (now - latest_update).days
                data_freshness = "current" if days_diff < 7 else "stale"
            except Exception:
                data_freshness = "unknown"
        
        return {
            "data_coverage": {
                "total_performance_records": performance_count,
                "season_summaries": summary_count,
                "trend_analyses": trend_count,
                "matchup_records": matchup_count,
                "players_with_data": players_with_data,
                "seasons_covered": season_list,
                "latest_update": latest_update.isoformat() if latest_update else None
            },
            "recommendations": {
                "sync_needed": performance_count == 0,
                "data_freshness": data_freshness
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get data overview: {str(e)}")


@router.get("/players/{player_id}/consistency-analysis")
async def get_player_consistency_analysis(
    player_id: int,
    seasons: int = Query(3, description="Number of seasons to analyze"),
    db: Session = Depends(get_db)
):
    """Get detailed consistency analysis for a player"""
    try:
        from app.models.historical_performance import PlayerHistoricalPerformance
        from app.models.player import Player
        from sqlalchemy import and_
        import statistics
        
        # Check if player exists
        player = db.query(Player).filter(Player.id == player_id).first()
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")
        
        current_year = datetime.now().year
        season_range = list(range(current_year - seasons + 1, current_year + 1))
        
        # Get all weekly performances
        performances = db.query(PlayerHistoricalPerformance).filter(
            and_(
                PlayerHistoricalPerformance.player_id == player_id,
                PlayerHistoricalPerformance.season.in_(season_range),
                PlayerHistoricalPerformance.week.isnot(None),
                PlayerHistoricalPerformance.fantasy_points_ppr.isnot(None)
            )
        ).order_by(PlayerHistoricalPerformance.season, PlayerHistoricalPerformance.week).all()
        
        if not performances:
            raise HTTPException(status_code=404, detail="No historical performance data found")
        
        # Calculate consistency metrics
        fantasy_points = [p.fantasy_points_ppr for p in performances]
        
        avg_points = statistics.mean(fantasy_points)
        median_points = statistics.median(fantasy_points)
        std_dev = statistics.stdev(fantasy_points) if len(fantasy_points) > 1 else 0
        
        # Coefficient of variation (lower = more consistent)
        cv = std_dev / avg_points if avg_points > 0 else 0
        
        # Calculate percentiles
        p25 = statistics.quantiles(fantasy_points, n=4)[0]
        p75 = statistics.quantiles(fantasy_points, n=4)[2]
        
        # Floor and ceiling games
        floor_games = len([fp for fp in fantasy_points if fp <= p25])
        ceiling_games = len([fp for fp in fantasy_points if fp >= p75])
        
        # Week-to-week consistency
        week_to_week_changes = []
        for i in range(1, len(fantasy_points)):
            change = abs(fantasy_points[i] - fantasy_points[i-1])
            week_to_week_changes.append(change)
        
        avg_weekly_change = statistics.mean(week_to_week_changes) if week_to_week_changes else 0
        
        # Consistency grade
        consistency_grade = "A"
        if cv > 0.6:
            consistency_grade = "F"
        elif cv > 0.5:
            consistency_grade = "D"
        elif cv > 0.4:
            consistency_grade = "C"
        elif cv > 0.3:
            consistency_grade = "B"
        
        return {
            "player_id": player_id,
            "player_name": player.name,
            "seasons_analyzed": seasons,
            "total_games": len(fantasy_points),
            "consistency_metrics": {
                "average_points": round(avg_points, 2),
                "median_points": round(median_points, 2),
                "standard_deviation": round(std_dev, 2),
                "coefficient_of_variation": round(cv, 3),
                "consistency_grade": consistency_grade,
                "weekly_floor": round(min(fantasy_points), 2),
                "weekly_ceiling": round(max(fantasy_points), 2),
                "25th_percentile": round(p25, 2),
                "75th_percentile": round(p75, 2)
            },
            "game_distribution": {
                "floor_games": floor_games,
                "ceiling_games": ceiling_games,
                "average_games": len(fantasy_points) - floor_games - ceiling_games,
                "avg_weekly_variance": round(avg_weekly_change, 2)
            },
            "weekly_points": [
                {
                    "season": p.season,
                    "week": p.week,
                    "points": p.fantasy_points_ppr,
                    "opponent": p.opponent_team
                }
                for p in performances
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get consistency analysis: {str(e)}")


@router.get("/trends/league-wide")
async def get_league_wide_trends(
    position: Optional[str] = Query(None, description="Filter by position"),
    trend_type: str = Query("career", description="Type of trend (career, season, 8_week)"),
    limit: int = Query(20, description="Number of results"),
    db: Session = Depends(get_db)
):
    """Get league-wide performance trends"""
    try:
        from app.models.historical_performance import PlayerTrend
        from app.models.player import Player
        from sqlalchemy import and_
        
        # Build query
        query = db.query(PlayerTrend, Player).join(Player).filter(
            PlayerTrend.trend_type == trend_type
        )
        
        if position:
            query = query.filter(Player.position == position.upper())
        
        # Get trending players
        trends = query.order_by(PlayerTrend.trend_strength.desc()).limit(limit).all()
        
        trend_data = []
        for trend, player in trends:
            trend_data.append({
                "player_id": player.id,
                "player_name": player.name,
                "position": player.position.value,
                "team": player.team,
                "trend_direction": trend.trend_direction,
                "trend_strength": trend.trend_strength,
                "performance_change": trend.performance_change,
                "confidence_level": trend.confidence_level,
                "sample_size": trend.sample_size,
                "last_updated": trend.last_updated.isoformat()
            })
        
        return {
            "trend_type": trend_type,
            "position_filter": position,
            "total_results": len(trend_data),
            "trending_players": trend_data
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get league-wide trends: {str(e)}")


# NOTE: This file used to also carry a set of "/advanced/*" routes
# (compare-players, strength-of-schedule/{player_id}, breakout-candidates,
# game-situation-analysis/{player_id}) backed by AdvancedHistoricalService
# and an inline reimplementation. They had zero frontend callers (verified via
# grep across frontend/src) and were fully duplicative:
#   - compare-players / strength-of-schedule / breakout-candidates: the real
#     statistical methods (ANOVA, Mann-Whitney U, Cohen's d) were merged into
#     AdvancedAnalysisService (backend/app/services/advanced_analysis_service.py),
#     the version actually wired to AdvancedAnalysisPage.tsx, so the live UI
#     now benefits from them via POST /advanced-analysis/{compare-players,
#     strength-of-schedule,breakout-candidates}.
#   - game-situation-analysis/{player_id}: superseded by the more rigorous,
#     honestly-labeled EnhancedGameSituationService, now wired into
#     AdvancedAnalysisPage.tsx's Game Situations tab via
#     POST /game-situations/enhanced-analysis.
# advanced_historical_service.py itself was deleted alongside these routes
# once this was confirmed to be its only remaining caller.