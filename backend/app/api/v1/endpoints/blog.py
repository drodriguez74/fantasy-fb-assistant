from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.services.content_service import content_service
from app.services.scraper_service import scraper_service
from app.services.sleeper_service import sleeper_service

router = APIRouter()


@router.get("/posts")
async def get_blog_posts():
    return {"message": "Blog posts - coming soon"}


@router.get("/waiver-wire/{week}")
async def generate_waiver_wire_post(
    week: int, 
    league_id: Optional[str] = Query(None, description="Sleeper league ID for personalized recommendations")
):
    """Generate AI-powered waiver wire post with multiple perspectives"""
    try:
        result = await content_service.generate_waiver_wire_post(week, league_id)
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate waiver wire post: {str(e)}")


@router.get("/player-spotlight/{player_name}")
async def generate_player_spotlight(player_name: str):
    """Generate multi-perspective player analysis"""
    try:
        result = await content_service.generate_player_spotlight(player_name)
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate player spotlight: {str(e)}")


@router.get("/rankings/{position}/week/{week}")
async def generate_rankings_post(position: str, week: int):
    """Generate position-specific rankings with multiple perspectives"""
    try:
        valid_positions = ["QB", "RB", "WR", "TE", "K", "DEF"]
        if position.upper() not in valid_positions:
            raise HTTPException(status_code=400, detail=f"Invalid position. Must be one of: {valid_positions}")
        
        result = await content_service.generate_weekly_rankings_post(position.upper(), week)
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate rankings post: {str(e)}")


@router.post("/save-post")
async def save_blog_post(post_data: dict, category: str = "waiver_wire"):
    """Save generated content as a blog post"""
    try:
        blog_post = await content_service.save_blog_post(post_data, category)
        
        if not blog_post:
            raise HTTPException(status_code=500, detail="Failed to save blog post")
        
        return {
            "id": blog_post.id,
            "title": blog_post.title,
            "slug": blog_post.slug,
            "created_at": blog_post.created_at
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save blog post: {str(e)}")


@router.get("/trending-topics")
async def get_trending_topics():
    """Get trending fantasy football topics"""
    try:
        topics = await scraper_service.scrape_trending_topics()
        return {"topics": topics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get trending topics: {str(e)}")


@router.get("/content-sources")
async def get_content_sources():
    """Get latest scraped content from fantasy sources"""
    try:
        waiver_content = await scraper_service.scrape_waiver_wire_content()
        return {"articles": waiver_content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get content sources: {str(e)}")