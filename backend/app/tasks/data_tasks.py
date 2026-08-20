from celery import Celery
from app.core.celery_app import celery_app
from app.services.sleeper_service import sleeper_service
import asyncio


@celery_app.task
def sync_player_data():
    """Background task to sync player data from Sleeper"""
    async def _sync():
        try:
            players = await sleeper_service.get_all_players()
            nfl_state = await sleeper_service.get_nfl_state()
            
            return {
                "players_count": len(players) if isinstance(players, dict) else 0,
                "nfl_state": nfl_state,
                "synced_at": "now"
            }
        except Exception as e:
            return {"error": str(e)}
    
    return asyncio.run(_sync())


@celery_app.task
def update_trending_data():
    """Background task to update trending player data"""
    async def _update():
        try:
            trending_adds = await sleeper_service.get_trending_players("add", 24, 50)
            trending_drops = await sleeper_service.get_trending_players("drop", 24, 50)
            
            return {
                "trending_adds": trending_adds,
                "trending_drops": trending_drops,
                "updated_at": "now"
            }
        except Exception as e:
            return {"error": str(e)}
    
    return asyncio.run(_update())


@celery_app.task
def sync_projections(week: int, season: str = "2024"):
    """Background task to sync player projections"""
    async def _sync():
        try:
            projections = await sleeper_service.get_player_projections(week, season)
            
            return {
                "projections": projections,
                "week": week,
                "season": season,
                "synced_at": "now"
            }
        except Exception as e:
            return {"error": str(e)}
    
    return asyncio.run(_sync())