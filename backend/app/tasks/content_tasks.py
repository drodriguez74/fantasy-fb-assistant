from celery import Celery
from app.core.celery_app import celery_app
from app.services.content_service import content_service
from app.services.scraper_service import scraper_service
import asyncio


@celery_app.task
def generate_weekly_waiver_content(week: int):
    """Background task to generate waiver wire content"""
    async def _generate():
        try:
            result = await content_service.generate_waiver_wire_post(week)
            if "error" not in result:
                # Save the post
                await content_service.save_blog_post(result, "waiver_wire")
            return result
        except Exception as e:
            return {"error": str(e)}
    
    return asyncio.run(_generate())


@celery_app.task
def generate_player_spotlight_content(player_name: str):
    """Background task to generate player spotlight"""
    async def _generate():
        try:
            result = await content_service.generate_player_spotlight(player_name)
            if "error" not in result:
                # Save the post
                await content_service.save_blog_post(result, "player_analysis")
            return result
        except Exception as e:
            return {"error": str(e)}
    
    return asyncio.run(_generate())


@celery_app.task
def scrape_content_sources():
    """Background task to scrape content from fantasy sources"""
    async def _scrape():
        try:
            waiver_content = await scraper_service.scrape_waiver_wire_content()
            trending_topics = await scraper_service.scrape_trending_topics()
            
            return {
                "waiver_content": waiver_content,
                "trending_topics": trending_topics,
                "scraped_at": "now"
            }
        except Exception as e:
            return {"error": str(e)}
    
    return asyncio.run(_scrape())


@celery_app.task
def generate_position_rankings(position: str, week: int):
    """Background task to generate position rankings"""
    async def _generate():
        try:
            result = await content_service.generate_weekly_rankings_post(position, week)
            if "error" not in result:
                # Save the post
                await content_service.save_blog_post(result, "rankings")
            return result
        except Exception as e:
            return {"error": str(e)}
    
    return asyncio.run(_generate())